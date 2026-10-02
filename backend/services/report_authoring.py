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
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from backend.services.database_packages import Manifest, PackageCatalogue, PackageError, changelog_with_note, inspect_archive, SUPPORTED_LIBRARIES
from backend.utils.filesystem import replace_file


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
    tool_id: str | None = Field(default=None, pattern=r'^[a-z][a-z0-9-]{0,63}$')
    entrypoint: str = Field(default='handler:run', pattern=r'^[a-zA-Z_][a-zA-Z_0-9]*:run$')
    kind: Literal['report', 'operation'] = 'report'
    preview: str | None = None
    confirmation_field: str | None = None
    definition_file: str | None = None
    files: dict[str, str] = Field(default_factory=dict, max_length=99)
    operation_source: str | None = None
    change_note: str = Field(default='', max_length=2000)

    def manifest(self):
        return Manifest.model_validate(dict(contract_version=2, id=self.package_id, name=self.name,
            version=self.version, libraries=self.libraries, tools=[dict(id=self.tool_id or self.package_id, name=self.name,
                kind=self.kind, entrypoint=self.entrypoint, sources=self.sources, inputs=self.inputs,
                preview=self.preview, confirmation_field=self.confirmation_field)]))

    def derive(self):
        if self.definition_file:
            from backend.services.tool_definition import definition
            filename, manifest = definition(self.files, self.definition_file)
            tool = manifest.tools[0]
            for key in ('name', 'kind', 'entrypoint', 'preview', 'confirmation_field', 'sources'):
                setattr(self, key, getattr(tool, key))
            self.inputs = [x.model_dump() for x in tool.inputs]
            self.libraries = manifest.libraries
            self.handler = self.files[filename]
        elif self.kind != 'report':
            raise PackageError('Add operations from Python containing a TOOL definition.')
        return self


class ReportAuthoring:
    def __init__(self, root, service):
        self.root = Path(root) / 'report-drafts'
        self.root.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.service = service
        self.session = uuid.uuid4().hex
        self.activation = self.root / 'activation.pending'
        self.recover_activation()
        (self.root / 'empty').mkdir(exist_ok=True)
        self.trials = PackageCatalogue(self.root / 'trials', self.root / 'empty')

    def begin_activation(self, package_id, content):
        import hashlib
        state = self.service.sources.state
        record = dict(package_id=package_id, sha256=hashlib.sha256(content).hexdigest(),
                      mappings=state['bindings'].get(package_id), operation=state['operation_bindings'].get(package_id))
        self._write(self.activation, record)

    def finish_activation(self):
        self.activation.unlink(missing_ok=True)

    def recover_activation(self):
        if not self.activation.exists():
            return
        import copy
        record = json.loads(self.activation.read_text('utf-8'))
        installed = self.service.catalogue.index.get(record['package_id'], {})
        if installed.get('sha256') != record['sha256']:
            state = copy.deepcopy(self.service.sources.state)
            for group, value in [('bindings', record['mappings']), ('operation_bindings', record['operation'])]:
                if value is None:
                    state[group].pop(record['package_id'], None)
                else:
                    state[group][record['package_id']] = value
            self.service.sources._save(state)
        self.finish_activation()

    @staticmethod
    def _write(path, record):
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(record), encoding='utf-8')
        replace_file(temporary, path)

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
            return [dict(id=d['id'], name=d['draft']['name'], revision=d['revision'], code_defined=bool(d['draft'].get('definition_file')))
                    for path in self.root.glob('*.json')
                    if (d := json.loads(path.read_text('utf-8')))['owner'] == owner
                    and not self.service.catalogue.published_draft(d['id'], owner)]

    def save(self, draft, owner, key=None, revision=0):
        with self.lock:
            draft = draft.model_copy(deep=True).derive()
            if key:
                if self.service.catalogue.published_draft(key, owner):
                    raise PackageError('This draft was published. Edit the installed tool to make another change.', 409)
                current = self.get(key, owner)
                if current['revision'] != revision:
                    raise PackageError('This draft changed in another tab. Reopen it before saving.', 409)
                if current['draft'].get('definition_file') and not draft.definition_file:
                    raise PackageError('Keep this tool definition with its Python.')
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
            if revision and current.get('verification') and (
                    {k:v for k,v in current['draft'].items() if k != 'change_note'} ==
                    {k:v for k,v in record['draft'].items() if k != 'change_note'}):
                record['verification'] = {**current['verification'], 'revision':revision+1}
            if revision and current.get('base'):
                record['base'] = current['base']
            self._write(self._path(key), record)
            return self.get(key, owner)

    def import_files(self, files, owner, key=None, revision=0, mode='all'):
        from backend.services.tool_definition import definition
        with self.lock, self.service.catalogue.lock:
            current = self.get(key, owner) if key else None
            entry_file = current['draft'].get('definition_file') if current else None
            if mode != 'all':
                if not current or not entry_file:
                    raise PackageError('Add the tool Python first.')
                existing = dict(current['draft']['files'])
                if mode == 'python':
                    if len(files) != 1 or not next(iter(files)).endswith('.py'):
                        raise PackageError('Choose one defining Python file. Use Replace all files for a complete source set.')
                    existing.pop(entry_file, None)
                    entry_file = next(iter(files))
                else:
                    for name, source in files.items():
                        if name == entry_file:
                            raise PackageError('Use Replace Python to change the tool definition.')
                        if name.endswith('.py'):
                            try:
                                tree = ast.parse(source)
                            except SyntaxError as exc:
                                raise PackageError(f'{name}, line {exc.lineno}: {exc.msg}') from None
                            for node in tree.body:
                                targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
                                if any(isinstance(t, ast.Name) and t.id == 'TOOL' for t in targets):
                                    raise PackageError('Supporting files cannot define another TOOL. Use Replace Python for the tool itself.')
                files = {**existing, **files}
            filename, manifest = definition(files, entry_file if entry_file in files else None)
            if current:
                draft = ReportDraft.model_validate(current['draft'])
                draft.files = files
                draft.definition_file = filename
            else:
                # Name is only the initial identity; renaming a saved draft never changes it.
                identity = re.sub('[^a-z0-9]+', '-', manifest.name.lower()).strip('-')[:50]
                if not identity or not identity[0].isalpha():
                    identity = 'tool-' + (identity or uuid.uuid4().hex[:8])
                if identity in self.service.catalogue.index:
                    raise PackageError('A package with this name is installed. Use Edit on that tool to update it.', 409)
                draft = ReportDraft(package_id=identity, definition_file=filename, files=files)
            draft.derive()
            self.archive(draft, key, owner)
            return self.save(draft, owner, key, revision)

    def remove(self, key, owner):
        with self.lock:
            self.get(key, owner)
            try:
                self.trials.remove('draft-' + key)
            except PackageError as exc:
                if exc.status != 404:
                    raise
            self._path(key).unlink()
            self._path(key).with_suffix('.zip').unlink(missing_ok=True)

    def edit_installed(self, tool_id, owner, kind='report', code_defined=False):
        with self.lock, self.service.catalogue.lock, self.service.sources.lock:
            package_id, entry, tool = self.service.catalogue.resolve(tool_id, kind)
            if not tool.entrypoint.endswith(':run'):
                raise PackageError('This report uses a custom entry function. Download its package to edit it.')
            content, _ = self.service.catalogue.export(package_id)
            manifest, files = inspect_archive(content)
            major, minor, patch = map(int, manifest.version.split('.'))
            if code_defined and tool.preview and tool.preview != tool.entrypoint.replace(':run', ':preview'):
                raise PackageError('This operation has custom preview wiring. Download its package to edit it.')
            if manifest.contract_version == 1 and kind == 'report':
                tool = tool.model_copy(update={'sources':['primary']})
            draft = ReportDraft(name=tool.name, package_id=package_id, tool_id=tool.id, entrypoint=tool.entrypoint,
                version=f'{major}.{minor}.{patch+1}', libraries=manifest.libraries,
                handler=files[tool.entrypoint.split(':')[0]+'.py'].decode('utf-8-sig'),
                sources=tool.sources if manifest.contract_version == 2 else ['primary'],
                mappings=self.service.sources.bindings(package_id), inputs=[x.model_dump() for x in tool.inputs], step=2,
                kind=kind, preview=tool.preview, confirmation_field=tool.confirmation_field,
                operation_source=self.service.sources.state['operation_bindings'].get(package_id))
            if code_defined:
                from backend.services.tool_definition import with_definition
                draft.definition_file = tool.entrypoint.split(':')[0]+'.py'
                draft.files = {name:value.decode('utf-8-sig') for name,value in files.items() if name != 'manifest.json'}
                tree = ast.parse(draft.handler)
                has_definition = any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'TOOL' for t in n.targets)
                                     or isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == 'TOOL' for n in tree.body)
                if not has_definition:
                    draft.files[draft.definition_file] = with_definition(draft.handler, tool)
            record = self.save(draft, owner)
            record['owner'] = owner
            record['base'] = dict(sha256=entry['sha256'], package_id=package_id, tool_id=tool.id, entrypoint=tool.entrypoint,
                mappings=self.service.sources.bindings(package_id), operation_source=draft.operation_source, kind=kind)
            path = self._path(record['id'])
            path.with_suffix('.zip').write_bytes(content)
            self._write(path, record)
            return self.get(record['id'], owner)

    def check_base(self, key, owner):
        record = self.get(key, owner)
        base = record.get('base')
        if not base and record['draft'].get('definition_file') and record['draft']['package_id'] in self.service.catalogue.index:
            raise PackageError('A tool with this identity was installed after this draft was created. Start an edit from the installed tool.', 409)
        if base:
            entry = self.service.catalogue.index.get(base['package_id'])
            if (not entry or entry['sha256'] != base['sha256'] or self.service.sources.bindings(base['package_id']) != base['mappings']
                    or 'operation_source' in base and self.service.sources.state['operation_bindings'].get(base['package_id']) != base['operation_source']):
                raise PackageError('The installed package or its connections changed. Start a new edit from the installed version.', 409)
        return base

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

    def archive(self, draft, key=None, owner=None, trial=False, note=None):
        """The package ZIP for a draft. `note` is given only when publishing: it becomes the
        new version's CHANGELOG section, so the release note travels with Download package."""
        draft = draft.model_copy(deep=True).derive()
        manifest = draft.manifest()
        files = {}
        base = self.get(key, owner).get('base') if key else None
        if base:
            if (draft.package_id, draft.tool_id) != (base['package_id'], base['tool_id']):
                raise PackageError('An update must retain the installed package and tool identifiers.')
            if draft.kind != base.get('kind', 'report'):
                raise PackageError('An update cannot change a report into an operation or vice versa.')
            original, files = inspect_archive(self._path(key).with_suffix('.zip').read_bytes())
            combined = original.model_dump()
            for item in combined['tools']:
                if original.contract_version == 1 and item['kind'] == 'report':
                    item['sources'] = ['primary']
            combined.update(contract_version=2, version=draft.version, libraries=sorted(set(original.libraries + draft.libraries)))
            combined['tools'] = [manifest.tools[0].model_dump() if t['id'] == draft.tool_id else t for t in combined['tools']]
            manifest = Manifest.model_validate(combined)
        if trial:
            manifest = manifest.model_copy(deep=True)
            manifest.id = 'draft-' + key
            manifest.tools = [next(t for t in manifest.tools if t.id == (draft.tool_id or draft.package_id))]
            manifest.tools[0].id = manifest.id
        retained = files
        if draft.definition_file:
            files = {name:text.encode('utf-8') for name,text in draft.files.items()}
        if note is not None:
            # Replace all files may omit CHANGELOG.md; the published version keeps its history.
            if not any(name.lower() == 'changelog.md' for name in files):
                files = {**files, **{name:value for name,value in retained.items() if name.lower() == 'changelog.md'}}
            files = changelog_with_note(files, manifest.name, manifest.version, note)
        if not draft.handler or 'ADAPT_BEFORE_BUILD' in draft.handler:
            raise PackageError('Upload the completed handler.py before trying or installing this report.')
        tree = ast.parse(draft.handler)
        for node in ast.walk(tree):
            names = [x.name for x in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
            for name in names:
                if isinstance(node, ast.ImportFrom) and node.level and draft.definition_file:
                    continue
                top = name.split('.')[0]
                if top not in sys.stdlib_module_names and top not in manifest.libraries and top+'.py' not in files:
                    raise PackageError(f"Import '{top}' is not declared. Choose a bundled library or adapt the script.")
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            files['manifest.json'] = manifest.model_dump_json(indent=2).encode('utf-8')
            files[draft.entrypoint.split(':')[0]+'.py'] = draft.handler.encode('utf-8')
            for name, content in files.items():
                archive.writestr(name, content)
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
        # Each saved revision gets a private execution snapshot. Import occurs
        # only in the report process after explicitly choosing Try.
        trial = draft.model_copy(update={'package_id': 'draft-' + key, 'tool_id':'draft-' + key})
        content = self.archive(draft, key, owner, trial=True)
        review = self.trials.inspect(content)
        if review['sha256'] != review['current_sha256']:
            self.trials.install(content)
        return trial

    def connection_fingerprint(self, draft):
        from backend.services.database_tools import digest
        with self.service.sources.lock:
            sources = self.service.sources.snapshot(draft.package_id, draft.sources, draft.mappings)
            target = self.service.sources.get(draft.operation_source, 'operation') if draft.kind == 'operation' else None
            return digest(dict(sources=sources, target=target))

    def record_trial(self, key, owner, revision, job=None):
        record = self.get(key, owner)
        if record['revision'] != revision:
            raise PackageError('Draft changed. Try it again.', 409)
        record.update(owner=owner, verification=dict(revision=revision, job=job,
                      session=self.session,
                      connections=self.connection_fingerprint(self.draft(key, owner))))
        self._write(self._path(key), record)

    def clear_trial(self, key, owner):
        record = self.get(key, owner)
        record.pop('verification', None)
        record['owner'] = owner
        self._write(self._path(key), record)

    def require_trial(self, key, owner):
        record = self.get(key, owner)
        verification = record.get('verification', {})
        if (verification.get('session') != self.session or verification.get('revision') != record['revision'] or
                verification.get('connections') != self.connection_fingerprint(self.draft(key, owner))):
            raise PackageError('Code or connections changed, or no successful trial exists. Try it again before enabling.', 409)
        if verification.get('job'):
            if self.service.report(verification['job'], owner)['status'] != 'ready':
                raise PackageError('Generate and check a successful report before enabling.', 409)
