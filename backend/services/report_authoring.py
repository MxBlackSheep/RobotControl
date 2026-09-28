"""Saved report drafts and package assembly; saving never executes Python."""
import ast
import io
import json
import re
import sys
import threading
import uuid
import zipfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from backend.services.database_packages import Manifest, PackageCatalogue, PackageError, inspect_archive, SUPPORTED_LIBRARIES


def inspect_python(source):
    """Inspect source only, including imports inside functions. Never import it."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise PackageError(f'Python syntax error on line {exc.lineno}: {exc.msg}') from None
    imports = set()
    undetermined = set()
    adaptation = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(x.name.split('.')[0] for x in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                undetermined.add('Local module imports need their supporting files.')
            else:
                imports.add((node.module or '').split('.')[0])
        elif isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            if name.endswith(('import_module', '__import__', 'exec', 'eval')):
                undetermined.add('Dynamic code or imports need manual review.')
            if name.endswith('.connect'):
                adaptation.add('Replace direct database connections with the selected report connections.')
            if name.endswith(('ExcelWriter', 'to_excel')):
                for kw in node.keywords:
                    if kw.arg == 'engine' and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        imports.add(kw.value.value)
        elif isinstance(node, ast.Attribute) and node.attr == 'argv':
            adaptation.add('Replace command-line arguments with report inputs.')
    run = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run'), None)
    compatible = bool(run and [a.arg for a in run.args.posonlyargs + run.args.args] == ['context', 'inputs']
                      and all(x is not None for x in run.args.kw_defaults))
    # A matching signature is a starting point, not proof of correct calculations.
    if not compatible:
        adaptation.add('Add run(context, inputs), write Excel in context.output_dir and return its filename.')
    return dict(available=sorted(imports & SUPPORTED_LIBRARIES),
                unavailable=sorted(imports - SUPPORTED_LIBRARIES - sys.stdlib_module_names - {'__future__'}),
                undetermined=sorted(undetermined), compatible=compatible, adaptation=sorted(adaptation))


class ReportDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(default='New report', min_length=1, max_length=100)
    package_id: str = Field(default='my-report', pattern=r'^[a-z][a-z0-9-]{0,63}$')
    version: str = Field(default='1.0.0', pattern=r'^\d+\.\d+\.\d+$')
    libraries: list[str] = Field(default_factory=lambda: ['openpyxl'], max_length=20)
    original: str = Field(default='', max_length=1024*1024)
    handler: str = Field(default='', max_length=1024*1024)
    sources: list[str] = Field(default_factory=lambda: ['primary'], max_length=8)
    mappings: dict[str, str] = Field(default_factory=dict, max_length=8)
    inputs: list[dict] = Field(default_factory=list, max_length=20)
    step: int = Field(default=0, ge=0, le=3)

    def manifest(self):
        return Manifest.model_validate(dict(contract_version=2, id=self.package_id, name=self.name,
            version=self.version, libraries=self.libraries, tools=[dict(id=self.package_id, name=self.name,
                kind='report', entrypoint='handler:run', sources=self.sources, inputs=self.inputs)]))


class ReportAuthoring:
    def __init__(self, root, service):
        self.root = Path(root) / 'report-drafts'
        self.root.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.service = service
        (self.root / 'empty').mkdir(exist_ok=True)
        self.trials = PackageCatalogue(self.root / 'trials', self.root / 'empty')

    def _path(self, key):
        if not re.fullmatch('[0-9a-f]{32}', key):
            raise PackageError('Draft not found', 404)
        return self.root / (key + '.json')

    def get(self, key, owner):
        with self.lock:
            path = self._path(key)
            if not path.exists():
                raise PackageError('Draft not found', 404)
            data = json.loads(path.read_text('utf-8'))
            if data['owner'] != owner:
                raise PackageError('Draft not found', 404)
            return {k: v for k, v in data.items() if k != 'owner'}

    def list(self, owner):
        with self.lock:
            return [dict(id=d['id'], name=d['draft']['name'], revision=d['revision'])
                    for path in self.root.glob('*.json')
                    if (d := json.loads(path.read_text('utf-8')))['owner'] == owner]

    def save(self, draft, owner, key=None, revision=0):
        with self.lock:
            if key:
                current = self.get(key, owner)
                if current['revision'] != revision:
                    raise PackageError('This draft changed in another tab. Reopen it before saving.', 409)
            else:
                if len(list(self.root.glob('*.json'))) >= 100:
                    raise PackageError('The 100-draft limit is reached. Remove an unused draft.', 409)
                key = uuid.uuid4().hex
            for name in ('original', 'handler'):
                source = getattr(draft, name)
                if source:
                    try:
                        ast.parse(source)
                    except SyntaxError as exc:
                        raise PackageError(f'{name}: Python syntax error on line {exc.lineno}: {exc.msg}') from exc
            record = dict(id=key, owner=owner, revision=revision+1, draft=draft.model_dump())
            path = self._path(key)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(record), encoding='utf-8')
            temporary.replace(path)
            return self.get(key, owner)

    def remove(self, key, owner):
        with self.lock:
            self.get(key, owner)
            try:
                self.trials.remove('draft-' + key)
            except PackageError as exc:
                if exc.status != 404:
                    raise
            self._path(key).unlink()

    def draft(self, key, owner):
        return ReportDraft.model_validate(self.get(key, owner)['draft'])

    def starter(self, key, owner):
        draft = self.draft(key, owner)
        draft.manifest()
        details = json.dumps({'inputs': draft.inputs, 'source_aliases': draft.sources}, indent=2)
        return ('# Adapt your original calculations; do not copy connection credentials.\n'
                '# Replace ADAPT_BEFORE_BUILD once the report is implemented.\n'
                + '\n'.join('# ' + line for line in details.splitlines()) + '\n\n'
                'def run(context, inputs):\n'
                '    # context.connections["primary"] supplies an approved connection.\n'
                '    # Read inputs by name, e.g. inputs["plate_id"].\n'
                '    # Write Excel under context.output_dir; return its filename.\n'
                '    raise NotImplementedError("ADAPT_BEFORE_BUILD")\n')

    def archive(self, draft):
        manifest = draft.manifest()
        if not draft.handler or 'ADAPT_BEFORE_BUILD' in draft.handler:
            raise PackageError('Upload the completed handler.py before trying or installing this report.')
        tree = ast.parse(draft.handler)
        for node in ast.walk(tree):
            names = [x.name for x in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
            for name in names:
                top = name.split('.')[0]
                if top not in sys.stdlib_module_names and top not in manifest.libraries:
                    raise PackageError(f"Import '{top}' is not declared. Choose a bundled library or adapt the script.")
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', manifest.model_dump_json(indent=2))
            archive.writestr('handler.py', draft.handler)
        content = output.getvalue()
        inspect_archive(content)
        return content

    def editing_files(self, key, owner):
        draft = self.draft(key, owner)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('original.py', draft.original)
            archive.writestr('handler.py', draft.handler or self.starter(key, owner))
            archive.writestr('inputs.json', json.dumps({'inputs': draft.inputs, 'sources': draft.sources}, indent=2))
            archive.writestr('EDITING.md', '# Adapt this report\n\n'
                'Keep the original calculation and selection rules. Edit handler.py yourself or with a coding agent.\n'
                'Provide run(context, inputs). Use context.connections[name] for the configured database; '
                'input names and connection names are in inputs.json. Use parameterized queries.\n'
                'Write Excel under context.output_dir and return its filename. Do not include connection passwords.\n'
                'Upload the adapted script in RobotControl, try it with known data, and check the downloaded workbook '
                'before installing. This editing ZIP is not an installable package.\n')
        return output.getvalue()

    def trial(self, key, owner):
        draft = self.draft(key, owner)
        # Each saved revision gets a private execution snapshot. Import occurs only
        # after the administrator explicitly chooses Try or loads trial choices.
        trial = draft.model_copy(update={'package_id': 'draft-' + key})
        content = self.archive(trial)
        review = self.trials.inspect(content)
        if review['sha256'] != review['current_sha256']:
            self.trials.install(content)
        return trial
