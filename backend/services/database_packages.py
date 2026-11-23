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
from types import ModuleType
from datetime import date, datetime, timezone
from fractions import Fraction
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from backend.utils.filesystem import replace_file

MAX_UPLOAD = 20 * 1024 * 1024
MAX_EXPANDED = 50 * 1024 * 1024
SUPPORTED_LIBRARIES = {"pandas", "openpyxl", "pyodbc", "numpy"}
IDENTIFIER = r"^[a-z][a-z0-9-]{0,63}$"
ENTRY = r"^[a-zA-Z_][a-zA-Z_0-9]*:[a-zA-Z_][a-zA-Z_0-9]*$"
MAX_NOTE = 2000


HEADING = re.compile(r"(#{1,6})(?:\s+(.*))?$")


def _changelog_name(files) -> str:
    # Package file names are unique regardless of case, so a changelog.md is the same file.
    return next((name for name in files if name.lower() == "changelog.md"), "CHANGELOG.md")


def _is_version(heading, version) -> bool:
    return re.fullmatch(re.escape(version) + r"\b.*", heading[2] or "") is not None


def changelog_note(payloads: dict, version: str) -> str:
    """The package's own CHANGELOG.md text under the `## <version>` heading, or ''.

    Used as the history message when the installer gives none (first-start seeding, or an
    import with "What changed?" left blank), and to prefill that field when an import is
    reviewed. History stays per installation; the CHANGELOG travels inside the ZIP and its
    exports. Wrapped lines are joined; paragraphs, list items and sub-headings keep their own line.
    """
    try:
        lines = payloads.get(_changelog_name(payloads), b"").decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        return ""
    level, blocks, joining = None, [], False
    for line in lines:
        text = line.strip()
        heading = HEADING.match(text)
        if level is None:
            if heading and _is_version(heading, version):
                level = len(heading[1])
            continue
        if heading and len(heading[1]) <= level:
            break
        if heading or not text:
            if heading and heading[2]:
                blocks.append(heading[2])
            joining = False
            continue
        text = text[1:] if text.startswith("\\#") else text
        if joining and not re.match(r"([-*+]|\d+[.)])\s", text):
            blocks[-1] += " " + text
        else:
            blocks.append(text)
            joining = True
    return "\n".join(blocks)[:MAX_NOTE]


def changelog_with_note(files: dict, name: str, version: str, note: str) -> dict:
    """`files` with `note` as the `## <version>` section at the top of CHANGELOG.md.

    Earlier sections are kept and an existing section for this version is replaced, so a
    version is never listed twice. Only RobotControl's own build of a ZIP (publishing an in-app
    edit) calls this: an installed ZIP is never rewritten, because schedules pin its sha256.
    """
    note = note.strip()
    if not note:
        return files
    filename = _changelog_name(files)
    try:
        lines = files[filename].decode("utf-8-sig").splitlines() if filename in files else [f"# {name} changes"]
    except UnicodeDecodeError:
        raise PackageError(f"{filename} is not UTF-8 text. Correct it in the package files, then publish again.") from None
    kept, dropping = [], None
    for line in lines:
        heading = HEADING.match(line.strip())
        if heading and (dropping is None or len(heading[1]) <= dropping):
            dropping = len(heading[1]) if _is_version(heading, version) else None
        if dropping is None:
            kept.append(line)
    top = next((i for i, line in enumerate(kept) if (h := HEADING.match(line.strip())) and len(h[1]) > 1), len(kept))
    # A note line that looks like a heading would end this section when the file is read back.
    body = ["\\" + line.strip() if HEADING.match(line.strip()) else line.rstrip() for line in note.splitlines()]
    combined = [*kept[:top], "", f"## {version}", "", *body, "", *kept[top:]]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(combined)).strip("\n") + "\n"
    return {**files, filename: text.encode("utf-8")}


class PackageError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# How a lookup's choices are listed; report_sources.lookup_rows maps each to fixed SQL.
LookupOrder = Literal['label', 'label_desc', 'value', 'value_desc']
LOOKUP_ORDERS = get_args(LookupOrder)


class LookupDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(pattern=IDENTIFIER)
    query: str = Field(min_length=1, max_length=12000)
    parameters: list[str] = Field(default_factory=list, max_length=20)
    value_type: Literal['text', 'integer', 'number'] = 'text'
    order: LookupOrder = 'label'

    @model_serializer(mode='wrap')
    def _omit_default_order(self, handler):
        # Applications before 0.1.5 refuse an `order` key, so a lookup that keeps the
        # default writes the same manifest as before and stays importable there.
        data = handler(self)
        if data.get('order') == 'label':
            del data['order']
        return data


class InputDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    label: str = Field(min_length=1, max_length=100)
    type: Literal["text", "integer", "number", "boolean", "choice", "date", "lookup"]
    required: bool = True
    choices: list[str] = Field(default_factory=list, max_length=100)
    lookup: LookupDefinition | None = None


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=IDENTIFIER)
    name: str = Field(min_length=1, max_length=100)
    # preparation: prepare(context, inputs) runs unattended before a scheduled run, in a
    # time-limited child process, against the package's operation connection.
    kind: Literal["operation", "report", "preparation"]
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
        if self.kind == "preparation" and (self.preview or self.confirmation_field):
            # Saving the schedule is the review; nobody is present to confirm at run time.
            raise ValueError("Preparation steps have no preview or confirmation field")
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
                     "number": lambda: type(value) in (int, float) and math.isfinite(value),
                     "boolean": lambda: type(value) is bool,
                     "date": lambda: True,
                     "choice": lambda: isinstance(value, str) and value in field.choices}[value_type]()
            if not valid:
                raise PackageError(f"Invalid {field.label}")
            clean[field.name] = value
        return clean


class ExperimentParameter(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_]{0,49}$')
    label: str = Field(min_length=1, max_length=100)
    type: Literal['number', 'integer', 'text', 'choice']
    default: Any
    min: Any = None
    max: Any = None
    allowed: list[Any] | None = Field(default=None, min_length=1, max_length=100)
    group: Literal['main', 'more']
    fixed: bool = False

    def validate_scalar(self, value):
        if self.type == 'integer':
            valid = type(value) is int
        elif self.type == 'number':
            valid = type(value) is int or (type(value) is float and math.isfinite(value))
        else:
            valid = isinstance(value, str) and bool(value.strip()) and len(value) <= 255
        if not valid:
            raise PackageError(f'{self.name}: invalid {self.type} value.')
        if self.min is not None and value < self.min:
            raise PackageError(f'{self.name} must be at least {self.min}.')
        if self.max is not None and value > self.max:
            raise PackageError(f'{self.name} must be at most {self.max}.')
        return value

    def validate_value(self, value):
        self.validate_scalar(value)
        if self.allowed is not None and value not in self.allowed:
            raise PackageError(f'{self.name}: value is not allowed.')
        if self.fixed and value != self.default:
            raise PackageError(f'{self.name} must remain at its default ({self.default}).')
        return value

    @model_validator(mode='after')
    def valid_parameter(self):
        if not self.label.strip():
            raise ValueError('Parameter label must not be blank')
        for name in ('min', 'max'):
            if name in self.model_fields_set:
                value = getattr(self, name)
                if (self.type not in ('number', 'integer') or type(value) not in (int, float)
                        or (type(value) is float and not math.isfinite(value))
                        or (self.type == 'integer' and type(value) is not int)):
                    raise ValueError(f'{self.name}: invalid {name} bound')
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f'{self.name}: minimum exceeds maximum')
        if 'allowed' in self.model_fields_set and self.allowed is None:
            raise ValueError(f'{self.name}: allowed must be a nonempty list')
        if self.type == 'choice' and self.allowed is None:
            raise ValueError(f'{self.name}: choice requires allowed values')
        if self.allowed is not None:
            for index, value in enumerate(self.allowed):
                self.validate_scalar(value)
                if value in self.allowed[:index]:
                    raise ValueError(f'{self.name}: allowed values must be distinct')
        self.validate_value(self.default)
        return self

    @model_serializer(mode='wrap')
    def omit_absent_constraints(self, handler):
        return {key: value for key, value in handler(self).items() if value is not None}


class ExperimentAssignment(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    value: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=50)
    symbol: str = Field(min_length=1, max_length=1)

    @model_validator(mode='after')
    def nonblank(self):
        if not all(value.strip() for value in (self.value, self.label, self.symbol)):
            raise ValueError('Assignment values, labels and symbols must not be blank')
        return self


class WholeCountRule(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['whole_count']
    parameter: str
    assignment: str


class ExperimentLayout(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['plate96']
    assignments: list[ExperimentAssignment] = Field(min_length=1, max_length=96)
    default: list[list[str]] = Field(max_length=96)
    required: list[str] = Field(max_length=96)
    rules: list[WholeCountRule] = Field(default_factory=list)

    def validate_wells(self, layout):
        if not isinstance(layout, list) or len(layout) > 96:
            raise PackageError('Provide a plate layout with at most 96 wells.')
        assignments = {item.value for item in self.assignments}
        seen, clean = set(), []
        for pair in layout:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise PackageError('Invalid well assignment.')
            well, assignment = pair
            if not isinstance(well, str) or not re.fullmatch(r'[A-H](?:[1-9]|1[0-2])', well) or well in seen:
                raise PackageError('Invalid or duplicate well.')
            if not isinstance(assignment, str) or assignment not in assignments:
                raise PackageError('Invalid well assignment. Omit empty wells.')
            seen.add(well)
            clean.append((well, assignment))
        present = {assignment for _, assignment in clean}
        for assignment in self.required:
            if assignment not in present:
                label = next(item.label for item in self.assignments if item.value == assignment)
                raise PackageError(f'Mark at least one {label.lower()} well.')
        return sorted(clean, key=lambda pair: (int(pair[0][1:]), pair[0][0]))

    @model_validator(mode='after')
    def valid_layout(self):
        values = [item.value for item in self.assignments]
        symbols = [item.symbol for item in self.assignments]
        if len(set(values)) != len(values) or len(set(symbols)) != len(symbols):
            raise ValueError('Assignment values and symbols must be unique')
        if len(set(self.required)) != len(self.required) or set(self.required) - set(values):
            raise ValueError('Required assignments must be a distinct subset of assignments')
        self.validate_wells(self.default)
        return self


class ExperimentDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    id: str = Field(pattern=IDENTIFIER)
    name: str = Field(min_length=1, max_length=100)
    kind: Literal['experiment']
    parameters: list[ExperimentParameter] = Field(min_length=1, max_length=20)
    layout: ExperimentLayout | None = None

    @model_validator(mode='before')
    @classmethod
    def no_null_layout(cls, data):
        if isinstance(data, dict) and 'layout' in data and data['layout'] is None:
            raise ValueError('Omit layout for an experiment without a plate')
        return data

    @model_serializer(mode='wrap')
    def omit_absent_layout(self, handler):
        data = handler(self)
        if self.layout is None:
            data.pop('layout', None)
        return data

    @model_validator(mode='after')
    def valid_definition(self):
        if not self.name.strip():
            raise ValueError('Experiment name must not be blank')
        if len({parameter.name.casefold() for parameter in self.parameters}) != len(self.parameters):
            raise ValueError('Parameter names must be unique ignoring case')
        if self.layout:
            numeric = {p.name for p in self.parameters if p.type in ('number', 'integer')}
            assignments = {item.value for item in self.layout.assignments}
            for rule in self.layout.rules:
                if rule.parameter not in numeric or rule.assignment not in assignments:
                    raise ValueError('Whole-count rule requires a declared numeric parameter and assignment')
            self.validate_layout(self.layout.default, {p.name: p.default for p in self.parameters})
        return self

    def validate_values(self, parameters):
        if not isinstance(parameters, dict) or set(parameters) != {p.name for p in self.parameters}:
            raise PackageError('Experiment parameter names do not match.')
        return {p.name: p.validate_value(parameters[p.name]) for p in self.parameters}

    def validate_layout(self, layout, parameters):
        if self.layout is None:
            if layout not in (None, []):
                raise PackageError('This experiment type has no plate layout.')
            return []
        clean = self.layout.validate_wells(layout)
        for rule in self.layout.rules:
            count = sum(assignment == rule.assignment for _, assignment in clean)
            value = parameters[rule.parameter]
            # Decimal text -> integer numerator/denominator; no floating multiplication or tolerance.
            fraction = Fraction(str(value))
            if (count * fraction.numerator) % fraction.denominator:
                label = next(item.label.lower() for item in self.layout.assignments if item.value == rule.assignment)
                raise PackageError(f'{count} {label} wells × {value} must give a whole number of wells.')
        return clean


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal[1, 2, 3]
    id: str = Field(pattern=IDENTIFIER)
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$", max_length=40)
    libraries: list[str] = Field(default_factory=list, max_length=20)
    tools: list[Annotated[ToolDefinition | ExperimentDefinition, Field(discriminator='kind')]] = Field(min_length=1, max_length=20)

    @model_validator(mode='before')
    @classmethod
    def retired_inputs(cls, data):
        # Installed/archive manifests used the retired picker for an integer ID.
        # Normalize at the boundary so old packages still execute with the same input.
        import copy
        data = copy.deepcopy(data)
        if isinstance(data, dict):
            for tool in data.get('tools', []):
                for field in tool.get('inputs', []):
                    if field.get('type') == 'experiment':
                        field['type'] = 'integer'
        return data

    @model_validator(mode='after')
    def contract(self):
        if self.id == 'experiments':
            raise ValueError('Package ID experiments is reserved for the shared writing connection')
        if any(t.kind == 'experiment' for t in self.tools) and self.contract_version != 3:
            raise ValueError('Experiment types require contract version 3')
        if all(t.kind == 'experiment' for t in self.tools) and self.libraries:
            raise ValueError('Experiment-only packages cannot declare libraries')
        if self.contract_version == 1 and any(t.sources or t.kind == 'preparation' or any(f.type in {'lookup', 'date'} for f in t.inputs) for t in self.tools):
            raise ValueError('Sources, dates, database choices and preparation steps require contract version 2')
        if self.contract_version == 1:
            for tool in self.tools:
                if tool.kind == 'report':
                    tool.sources = ['primary']
            self.contract_version = 2
        return self


def _upgrade_installed(index):
    packages = dict(index)
    for entry in packages.values():
        entry['manifest'] = Manifest.model_validate(entry['manifest']).model_dump(mode='json')
    index.clear()
    index['packages'] = packages


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
            if all(tool.kind == 'experiment' for tool in manifest.tools) and any(file.filename.lower().endswith('.py') for file in files):
                raise PackageError('Experiment-only packages cannot contain Python')
            for file in files:
                payload = archive.read(file)
                if file.filename.endswith(".py"):
                    compile(payload, file.filename, "exec")
                payloads[file.filename] = payload
        for tool in manifest.tools:
            if tool.kind == 'experiment':
                continue
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
        # Set by DatabaseTools: names of active schedules whose preparation step uses a
        # package. Seeding at first start runs before it is set (no schedules use those yet).
        self.in_use = None
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
            from backend.services.stored_data import upgrade_json, UpgradeStopped
            try:
                upgrade_json(self.index_path, {2: _upgrade_installed})
                self.index = json.loads(self.index_path.read_text(encoding="utf-8"))['packages']
            except (UpgradeStopped, KeyError, TypeError) as exc:
                raise PackageError(str(exc), 409) from exc
        # Only generated directories belonging to this catalogue are cleaned.
        active = {entry["directory"] for entry in self.index.values()}
        for folder in root.iterdir():
            if folder.is_dir() and re.fullmatch(r"[0-9a-f]{32}", folder.name) and folder.name not in active:
                shutil.rmtree(folder)

    def _save(self, index):
        temporary = self.index_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"version": 2, "packages": index}, indent=2), encoding="utf-8")
        replace_file(temporary, self.index_path)

    def packages(self):
        with self.lock:
            return [dict(entry["manifest"], sha256=entry["sha256"], running=self.running.get(key, 0))
                    for key, entry in self.index.items()]

    def tools(self, kind):
        return [dict(tool, package_id=package["id"], package_version=package["version"],
                     **({'sha256': package['sha256']} if kind == 'experiment' else {}))
                for package in self.packages() for tool in package["tools"] if tool["kind"] == kind]

    def history(self, package_id):
        with self.lock:
            entry = self.index.get(package_id)
            if not entry:
                raise PackageError('Package is not installed', 404)
            return [{k:v for k,v in item.items() if k != 'draft'} for item in reversed(entry.get('history', []))]

    def published_draft(self, key, owner):
        # Publication and its receipt share the atomic installed-index write.
        for entry in self.index.values():
            for item in entry.get('history', []):
                if item.get('draft', {}).get('id') == key and item.get('actor') == owner:
                    return entry, item
        return None

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
                    model = ExperimentDefinition if kind == 'experiment' else ToolDefinition
                    return package_id, entry, model.model_validate(value)
        raise PackageError("Experiment type is no longer installed." if kind == 'experiment'
                           else "This action or report is not installed", 404)

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
                namespace = f"rc_database_{key[0]}"
                if namespace not in sys.modules:
                    package = ModuleType(namespace)
                    package.__path__ = [str(path.parent)]
                    sys.modules[namespace] = package
                spec = importlib.util.spec_from_file_location(f"{namespace}.{module_name}", path)
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
        manifest, payloads = inspect_archive(content)
        with self.lock:
            self._check_conflicts(manifest)
            current = self.index.get(manifest.id)
            return dict(package=manifest.model_dump(), sha256=hashlib.sha256(content).hexdigest(),
                        current_version=current['manifest']['version'] if current else None,
                        current_sha256=current['sha256'] if current else '',
                        running=self.running.get(manifest.id, 0), changelog=changelog_note(payloads, manifest.version))

    def _check_conflicts(self, manifest):
        existing_ids = {tool['id'] for key, value in self.index.items() if key != manifest.id
                        for tool in value['manifest']['tools']}
        if existing_ids & {tool.id for tool in manifest.tools}:
            raise PackageError("An installed package already provides this tool identifier", 409)

    def install(self, content, expected_current=None, expected_package=None, *, actor=None, note='', draft=None):
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
                self.refuse_if_scheduled(manifest.id)
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
                previous = {name: (self.root / old['directory'] / name).read_bytes()
                            for name in payloads if old and (self.root / old['directory'] / name).is_file()}
                old_names = {p.name for p in (self.root / old['directory']).iterdir()
                             if p.is_file() and p.suffix in {'.py','.json','.txt','.md'}} if old else set()
                names = set(payloads)
                event = dict(version=manifest.version, previous_version=old['manifest']['version'] if old else None,
                             at=datetime.now(timezone.utc).isoformat(), actor=actor, sha256=entry['sha256'],
                             note=note.strip() or changelog_note(payloads, manifest.version),
                             files=dict(added=sorted(names-old_names), removed=sorted(old_names-names),
                                        changed=sorted(n for n in names & old_names if previous.get(n) != payloads[n])))
                if draft:
                    event['draft'] = draft
                entry['history'] = [*(old.get('history', []) if old else []), event]
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
        namespace = f"rc_database_{entry['directory']}"
        for name in list(sys.modules):
            if name == namespace or name.startswith(namespace + '.'):
                sys.modules.pop(name, None)
        shutil.rmtree(self.root / entry["directory"], ignore_errors=True)

    def refuse_if_scheduled(self, package_id):
        """An armed schedule must run the package version it was saved with."""
        if self.in_use is None:
            return
        try:
            names = self.in_use(package_id)
        except Exception as exc:
            raise PackageError("Could not confirm that no active schedule uses this package. Try again.", 503) from exc
        if names:
            raise PackageError("Active schedules run this package before their runs: " + ", ".join(sorted(names)[:5])
                               + ". Disable them, change the package, then review and save them again.", 409)

    def remove(self, package_id):
        with self.lock:
            if package_id not in self.index:
                raise PackageError("Package is not installed", 404)
            if self.running.get(package_id, 0):
                raise PackageError("This package is running. Try again when it finishes.", 409)
            self.refuse_if_scheduled(package_id)
            old = self.index[package_id]
            updated = {key: value for key, value in self.index.items() if key != package_id}
            self._save(updated)
            self.index = updated
            self._discard(old)
