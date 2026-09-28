"""Read a tool's small Python declaration without importing uploaded code."""
import ast
import io
import re
import sys
import zipfile
from pathlib import PurePosixPath

from backend.services.database_packages import Manifest, PackageError, SUPPORTED_LIBRARIES


def definition(files, entry_file=None):
    if not files or len(files) > 99 or sum(len(v.encode('utf-8')) for v in files.values()) > 3 * 1024 * 1024:
        raise PackageError('Choose up to 99 source files, totalling at most 3 MiB.')
    found = []
    trees = {}
    names = set()
    for name, source in files.items():
        path = PurePosixPath(name)
        if (len(path.parts) != 1 or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]*', name)
                or path.suffix not in {'.py', '.json', '.md', '.txt'} or name.lower() in names
                or name.lower() == 'manifest.json'):
            raise PackageError('Choose Python and supporting .json/.md/.txt files without folders or a manifest.')
        names.add(name.lower())
        if path.suffix != '.py':
            continue
        try:
            tree = ast.parse(source, filename=name)
        except SyntaxError as exc:
            raise PackageError(f'{name}, line {exc.lineno}: {exc.msg}') from None
        trees[name] = tree
        for node in tree.body:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
            if (entry_file is None or name == entry_file) and any(isinstance(t, ast.Name) and t.id == 'TOOL' for t in targets):
                try:
                    found.append((name, ast.literal_eval(node.value)))
                except (ValueError, TypeError):
                    raise PackageError('TOOL must contain literal settings, not function calls or expressions.') from None
    if len(found) != 1:
        raise PackageError('Include one TOOL definition with your Python. Download an example, keep its definition and run(context, inputs), and adapt your calculations. Nothing has been run.')
    filename, config = found[0]
    allowed = {'name', 'kind', 'inputs', 'connections', 'confirm'}
    if not isinstance(config, dict) or set(config) - allowed:
        raise PackageError('TOOL supports name, kind, inputs, connections and confirm.')
    if config.get('kind') not in {'report', 'operation'}:
        raise PackageError('Set TOOL kind to report or operation.')
    if not isinstance(config.get('name'), str) or not config['name'].strip():
        raise PackageError('Give the tool a name.')
    raw_inputs = config.get('inputs', {})
    if not isinstance(raw_inputs, dict):
        raise PackageError('TOOL inputs must map input names to their settings.')
    fields = []
    for name, value in raw_inputs.items():
        settings = {'type': value} if isinstance(value, str) else dict(value) if isinstance(value, dict) else None
        if settings is None or set(settings) - {'label', 'type', 'required', 'choices', 'query', 'source', 'depends_on'}:
            raise PackageError(f'{name}: use type, label, required, choices, query, source or depends_on.')
        field = dict(name=name, label=settings.get('label', name.replace('_', ' ').capitalize()),
                     type=settings.get('type', 'text'), required=settings.get('required', True), choices=settings.get('choices', []))
        if 'query' in settings:
            field.update(type='lookup', lookup=dict(source=settings.get('source', 'primary'), query=settings['query'],
                         parameters=settings.get('depends_on', []), value_type=settings.get('type', 'text')))
        elif 'source' in settings or 'depends_on' in settings:
            raise PackageError(f'{name}: source and depends_on require a query.')
        fields.append(field)
    sources = config.get('connections', ['primary'] if config['kind'] == 'report' else sorted({f['lookup']['source'] for f in fields if 'lookup' in f}))
    module = filename[:-3]
    functions = {n.name: n for n in trees[filename].body if isinstance(n, ast.FunctionDef)}
    for name in (['run', 'preview'] if config['kind'] == 'operation' else ['run']):
        fn = functions.get(name)
        if (not fn or [a.arg for a in fn.args.posonlyargs + fn.args.args] != ['context', 'inputs']
                or any(x is None for x in fn.args.kw_defaults)):
            raise PackageError(f'Define {name}(context, inputs) in {filename}.')
    libraries = set()
    local = {name[:-3] for name in trees}
    for name, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                if node.level != 1 or node.module not in local:
                    raise PackageError(f'{name}: include the helper file for the relative import.')
                continue
            imports = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ''] if isinstance(node, ast.ImportFrom) else []
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {'ExcelWriter', 'to_excel'}:
                imports += [kw.value.value for kw in node.keywords if kw.arg == 'engine' and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str)]
            for imported in imports:
                top = imported.split('.')[0]
                if top in local:
                    raise PackageError(f'{name}: import local helpers using from .{top} import ...')
                if top in SUPPORTED_LIBRARIES:
                    libraries.add(top)
                elif top not in sys.stdlib_module_names and top != '__future__':
                    raise PackageError(f'Library {top} is not bundled. Adapt the script or upgrade RobotControl.')
    tool = dict(name=config['name'].strip(), kind=config['kind'], inputs=fields, sources=sources,
                entrypoint=f'{module}:run', preview=f'{module}:preview' if config['kind'] == 'operation' else None,
                confirmation_field=config.get('confirm'))
    # Reuse the installed-package contract for input types, dependencies and limits.
    manifest = Manifest.model_validate(dict(contract_version=2, id='new-tool', name=tool['name'], version='1.0.0',
                                           libraries=sorted(libraries), tools=[dict(id='new-tool', **tool)]))
    return filename, manifest


def with_definition(source, tool):
    """Upgrade an existing conventional handler for editing; keep its logic intact."""
    config = dict(name=tool.name, kind=tool.kind, connections=tool.sources, inputs={})
    if tool.kind == 'operation':
        config['confirm'] = tool.confirmation_field
    for field in tool.inputs:
        value = dict(label=field.label, type=field.type)
        if not field.required:
            value['required'] = False
        if field.choices:
            value['choices'] = field.choices
        if field.lookup:
            value.update(type=field.lookup.value_type, query=field.lookup.query,
                         source=field.lookup.source, depends_on=field.lookup.parameters)
        elif field.type == 'experiment':
            value.update(type='integer', query='SELECT ExperimentID AS value, UserDefinedID AS label FROM dbo.Experiments', source='primary')
            if 'primary' not in config['connections']:
                config['connections'] = [*config['connections'], 'primary']
        config['inputs'][field.name] = value
    import pprint
    # Append so module docstrings and __future__ imports retain their positions.
    return source.rstrip() + '\n\nTOOL = ' + pprint.pformat(config, sort_dicts=False, width=100) + '\n'


def source_archive(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(name, text.encode('utf-8'))
    return output.getvalue()
