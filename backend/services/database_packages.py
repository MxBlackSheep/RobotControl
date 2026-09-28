"""Trusted database extensions. Installation validates packaging, not Python safety."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import math
import re
import shutil
import sys
import threading
import uuid
import zipfile
from datetime import date
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_UPLOAD = 20 * 1024 * 1024
MAX_EXPANDED = 50 * 1024 * 1024
SUPPORTED_LIBRARIES = {"pandas", "openpyxl", "pyodbc", "numpy"}
IDENTIFIER = r"^[a-z][a-z0-9-]{0,63}$"
ENTRY = r"^[a-zA-Z_][a-zA-Z_0-9]*:[a-zA-Z_][a-zA-Z_0-9]*$"


class PackageError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class LookupDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(pattern=IDENTIFIER)
    query: str = Field(min_length=1, max_length=12000)
    parameters: list[str] = Field(default_factory=list, max_length=20)
    value_type: Literal['text', 'integer', 'number'] = 'text'


class InputDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    label: str = Field(min_length=1, max_length=100)
    type: Literal["text", "integer", "number", "boolean", "choice", "experiment", "date", "lookup"]
    required: bool = True
    choices: list[str] = Field(default_factory=list, max_length=100)
    lookup: LookupDefinition | None = None


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=IDENTIFIER)
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["operation", "report"]
    entrypoint: str = Field(pattern=ENTRY)
    preview: str | None = Field(default=None, pattern=ENTRY)
    confirmation_field: str | None = None
    inputs: list[InputDefinition] = Field(default_factory=list, max_length=20)
    sources: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def valid_inputs(self):
        names = [field.name for field in self.inputs]
        if len(set(names)) != len(names):
            raise ValueError("Input names must be unique")
        if any(field.type == "choice" and not field.choices for field in self.inputs):
            raise ValueError("Choice fields need choices")
        if len(set(self.sources)) != len(self.sources) or any(not re.fullmatch(IDENTIFIER, x) for x in self.sources):
            raise ValueError('Source aliases must be unique lowercase identifiers')
        dependencies = {}
        for field in self.inputs:
            if (field.type == 'lookup') != (field.lookup is not None):
                raise ValueError('Database choices require a lookup definition')
            deps = field.lookup.parameters if field.lookup else []
            if field.lookup and field.lookup.source not in self.sources:
                raise ValueError(f'{field.label}: unknown source alias')
            if any(x not in names for x in deps):
                raise ValueError(f'{field.label}: unknown input dependency')
            dependencies[field.name] = deps
        visited = set()
        def visit(name, trail):
            if name in trail:
                raise ValueError('Input dependencies contain a cycle')
            if name in visited:
                return
            for parent in dependencies[name]:
                visit(parent, trail | {name})
            visited.add(name)
        for name in names:
            visit(name, set())
        if self.kind == "operation" and (not self.preview or not any(field.name == self.confirmation_field and field.required for field in self.inputs)):
            raise ValueError("Operations require a preview and confirmation field")
        return self

    def validate_values(self, values, partial=False):
        if set(values) - {field.name for field in self.inputs}:
            raise PackageError("Unexpected input field")
        clean = {}
        for field in self.inputs:
            value = values.get(field.name)
            if value is None or value == "":
                if field.required and not partial:
                    raise PackageError(f"{field.label} is required")
                continue
            value_type = field.lookup.value_type if field.lookup else field.type
            if value_type == 'date':
                try:
                    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                        raise ValueError()
                except (ValueError, TypeError):
                    raise PackageError(f'Invalid {field.label}')
            valid = {"text": lambda: isinstance(value, str) and len(value) <= 2000,
                     "integer": lambda: type(value) is int,
                     "experiment": lambda: type(value) is int and value > 0,
                     "number": lambda: type(value) in (int, float) and math.isfinite(value),
                     "boolean": lambda: type(value) is bool,
                     "date": lambda: True,
                     "choice": lambda: isinstance(value, str) and value in field.choices}[value_type]()
            if not valid:
                raise PackageError(f"Invalid {field.label}")
            clean[field.name] = value
        return clean


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal[1, 2]
    id: str = Field(pattern=IDENTIFIER)
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$", max_length=40)
    libraries: list[str] = Field(default_factory=list, max_length=20)
    tools: list[ToolDefinition] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def contract(self):
        if self.contract_version == 1 and any(t.sources or any(f.type in {'lookup', 'date'} for f in t.inputs) for t in self.tools):
            raise ValueError('Sources, dates and database choices require contract version 2')
        return self


def inspect_archive(content):
    """Read/compile trusted package files without importing or executing them."""
    if len(content) > MAX_UPLOAD:
        raise PackageError("Package exceeds the 20 MiB upload limit", 413)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            files = archive.infolist()
            if len(files) > 100 or sum(file.file_size for file in files) > MAX_EXPANDED:
                raise PackageError("Package exceeds 100 files or 50 MiB expanded size", 413)
            seen = set()
            for file in files:
                name = file.filename
                path = PurePosixPath(name)
                if (file.is_dir() or len(path.parts) != 1 or path.is_absolute() or
                    not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", name) or
                    name.endswith(('.', ' ')) or path.suffix.lower() not in {".py", ".json", ".md", ".txt"} or
                    name.lower() in seen or (file.external_attr >> 16) & 0o170000 == 0o120000 or
                    name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *[f'COM{i}' for i in range(10)], *[f'LPT{i}' for i in range(10)]}):
                    raise PackageError("Package contains an unsafe path, duplicate file or unsupported file type")
                seen.add(name.lower())
            manifest = Manifest.model_validate_json(archive.read("manifest.json"))
            if len({tool.id for tool in manifest.tools}) != len(manifest.tools):
                raise PackageError("Tool identifiers must be unique")
            for library in manifest.libraries:
                if library not in SUPPORTED_LIBRARIES or importlib.util.find_spec(library) is None:
                    raise PackageError(f"Library {library} is not bundled. An application upgrade is required.")
            payloads = {}
            for file in files:
                payload = archive.read(file)
                if file.filename.endswith(".py"):
                    compile(payload, file.filename, "exec")
                payloads[file.filename] = payload
        for tool in manifest.tools:
            for entrypoint in (tool.entrypoint, tool.preview):
                if not entrypoint:
                    continue
                module, function = entrypoint.split(':')
                source = payloads.get(module + '.py')
                if source is None:
                    raise PackageError(f"Missing Python file: {module}.py")
                tree = ast.parse(source, filename=module + '.py')
                if not any(isinstance(node, ast.FunctionDef) and node.name == function for node in tree.body):
                    raise PackageError(f"Define {function}(context, inputs) in {module}.py")
        return manifest, payloads
    except PackageError:
        raise
    except Exception as exc:
        raise PackageError(f"Package could not be read: {exc}") from exc


class PackageCatalogue:
    def __init__(self, root: Path, defaults: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.running = {}
        self.modules = {}
        self.index_path = root / "installed.json"
        # A missing index is first installation; an empty index means deliberately removed.
        if not self.index_path.exists():
            self.index = {}
            self._save(self.index)
            try:
                for folder in sorted(defaults.iterdir()):
                    if (folder / "manifest.json").exists():
                        buffer = io.BytesIO()
                        with zipfile.ZipFile(buffer, "w") as archive:
                            for file in folder.iterdir():
                                if file.suffix in {".py", ".json", ".txt", ".md"}:
                                    archive.writestr(file.name, file.read_bytes())
                        self.install(buffer.getvalue())
            except Exception:
                # Retry first installation on the next access; do not persist a partial seed.
                self.index_path.unlink(missing_ok=True)
                raise
        else:
            self.index = json.loads(self.index_path.read_text(encoding="utf-8"))
        # Only generated directories belonging to this catalogue are cleaned.
        active = {entry["directory"] for entry in self.index.values()}
        for folder in root.iterdir():
            if folder.is_dir() and re.fullmatch(r"[0-9a-f]{32}", folder.name) and folder.name not in active:
                shutil.rmtree(folder)

    def _save(self, index):
        temporary = self.index_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(index, indent=2), encoding="utf-8")
        temporary.replace(self.index_path)

    def packages(self):
        with self.lock:
            return [dict(entry["manifest"], sha256=entry["sha256"], running=self.running.get(key, 0))
                    for key, entry in self.index.items()]

    def tools(self, kind):
        return [dict(tool, package_id=package["id"], package_version=package["version"])
                for package in self.packages() for tool in package["tools"] if tool["kind"] == kind]

    def export(self, package_id):
        with self.lock:
            entry = self.index.get(package_id)
            if not entry:
                raise PackageError('Package is not installed', 404)
            directory = self.root / entry['directory']
            original = directory / '.package.zip'
            if original.exists():
                content = original.read_bytes()
                if hashlib.sha256(content).hexdigest() != entry['sha256']:
                    raise PackageError('The retained package ZIP has changed. Reinstall a reviewed copy before exporting.', 409)
            else:
                # Older installations retained flat authored files, not the ZIP.
                output = io.BytesIO()
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for file in sorted(directory.iterdir()):
                        if file.is_file() and not file.is_symlink() and file.suffix in {'.py', '.json', '.md', '.txt'}:
                            archive.writestr(file.name, file.read_bytes())
                content = output.getvalue()
            manifest, _ = inspect_archive(content)
            return content, f'{manifest.id}-{manifest.version}.zip'

    def resolve(self, tool_id, kind):
        for package_id, entry in self.index.items():
            for value in entry["manifest"]["tools"]:
                if value["id"] == tool_id and value["kind"] == kind:
                    return package_id, entry, ToolDefinition.model_validate(value)
        raise PackageError("This action or report is not installed", 404)

    @contextmanager
    def reserve(self, tool_id, kind):
        with self.lock:
            package_id, entry, tool = self.resolve(tool_id, kind)
            self.running[package_id] = self.running.get(package_id, 0) + 1
        try:
            yield entry, tool
        finally:
            with self.lock:
                self.running[package_id] -= 1

    def function(self, entry, name):
        module_name, function_name = name.split(":")
        key = (entry["directory"], module_name)
        with self.lock:
            if key not in self.modules:
                path = self.root / entry["directory"] / f"{module_name}.py"
                spec = importlib.util.spec_from_file_location(f"rc_database_{key[0]}_{module_name}", path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                try:
                    spec.loader.exec_module(module)
                except Exception:
                    sys.modules.pop(spec.name, None)
                    raise
                self.modules[key] = module
            function = getattr(self.modules[key], function_name, None)
            if not callable(function):
                raise PackageError("Package entry point is not callable")
            return function

    def inspect(self, content):
        manifest, _ = inspect_archive(content)
        with self.lock:
            self._check_conflicts(manifest)
            current = self.index.get(manifest.id)
            return dict(package=manifest.model_dump(), sha256=hashlib.sha256(content).hexdigest(),
                        current_version=current['manifest']['version'] if current else None,
                        current_sha256=current['sha256'] if current else '',
                        running=self.running.get(manifest.id, 0))

    def _check_conflicts(self, manifest):
        existing_ids = {tool['id'] for key, value in self.index.items() if key != manifest.id
                        for tool in value['manifest']['tools']}
        if existing_ids & {tool.id for tool in manifest.tools}:
            raise PackageError("An installed package already provides this tool identifier", 409)

    def install(self, content, expected_current=None, expected_package=None):
        manifest, payloads = inspect_archive(content)
        directory = self.root / uuid.uuid4().hex
        activated = False
        try:
            directory.mkdir()
            for name, payload in payloads.items():
                (directory / name).write_bytes(payload)
            (directory / '.package.zip').write_bytes(content)
            entry = {"manifest": manifest.model_dump(), "directory": directory.name,
                     "sha256": hashlib.sha256(content).hexdigest()}
            with self.lock:
                if self.running.get(manifest.id, 0):
                    raise PackageError("This package is running. Try again when it finishes.", 409)
                self._check_conflicts(manifest)
                current = self.index.get(manifest.id)
                if expected_package is not None and expected_package != manifest.id:
                    raise PackageError("Choose an update for the selected package.", 409)
                if expected_current is not None and expected_current != (current['sha256'] if current else ''):
                    raise PackageError("Installed package changed. Review the update again.", 409)
                # Inspection already validates syntax and entry-point names.
                # Import only when explicitly running/previewing a tool; report
                # imports belong in the report process, never the robot service.
                old = self.index.get(manifest.id)
                updated = {**self.index, manifest.id: entry}
                self._save(updated)
                self.index = updated
                activated = True
                if old:
                    self._discard(old)
            return manifest.model_dump()
        except PackageError:
            raise
        except Exception as exc:
            raise PackageError(f"Package could not be installed: {exc}") from exc
        finally:
            if not activated:
                self._discard({"directory": directory.name})

    def _discard(self, entry):
        for key in list(self.modules):
            if key[0] == entry["directory"]:
                module = self.modules.pop(key)
                sys.modules.pop(module.__name__, None)
        shutil.rmtree(self.root / entry["directory"], ignore_errors=True)

    def remove(self, package_id):
        with self.lock:
            if package_id not in self.index:
                raise PackageError("Package is not installed", 404)
            if self.running.get(package_id, 0):
                raise PackageError("This package is running. Try again when it finishes.", 409)
            old = self.index[package_id]
            updated = {key: value for key, value in self.index.items() if key != package_id}
            self._save(updated)
            self.index = updated
            self._discard(old)
