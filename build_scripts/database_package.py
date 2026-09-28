"""Create an editable adapter around an existing script; build an installable ZIP."""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import shutil
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.services.database_packages import Manifest, PackageError, inspect_archive


def ask(label, default=''):
    answer = input(f'{label}' + (f' [{default}]' if default else '') + ': ').strip()
    return answer or default


def field_definition(value):
    parts = value.split(':', 3)
    if len(parts) < 3:
        raise ValueError('Use name:type:Label, for example experiment_id:experiment:Experiment')
    name, kind, label = parts[:3]
    field = dict(name=name, type=kind, label=label, required=True)
    if kind == 'choice':
        field['choices'] = parts[3].split(',') if len(parts) == 4 else []
    return field


def create(args):
    source, folder = args.script.resolve(), args.folder.resolve()
    if not source.is_file() or source.suffix.lower() != '.py':
        raise ValueError('Choose an existing .py script.')
    if folder.exists():
        raise ValueError('Choose a new folder; existing work will not be overwritten.')
    interactive = args.name is None
    name = args.name or ask('Name shown in RobotControl')
    package_id = args.id or ask('Stable package ID, e.g. culture-history')
    kind = args.kind or ask('Type: report or operation', 'report')
    version = args.version or (ask('Version', '1.0.0') if interactive else '1.0.0')
    libraries = args.libraries
    if libraries is None:
        libraries = ask('Libraries, separated by commas', 'pandas,openpyxl' if kind == 'report' else '') if interactive else ''
    fields = args.input
    if fields is None:
        fields = []
        if interactive:
            print('Add inputs as name:type:Label. Types: experiment, text, integer, number, boolean, choice.')
            print('For choices: state:choice:State:Clean,Dirty. Enter a blank line when finished.')
            while value := ask('Input'):
                fields.append(value)
        else:
            fields = ['experiment_id:experiment:Experiment']
    tool = dict(id=package_id, name=name, kind=kind, entrypoint='handler:run',
                inputs=[field_definition(field) for field in fields])
    if kind == 'operation':
        tool.update(preview='handler:preview', confirmation_field=args.confirmation or ask('Input to type for confirmation', 'experiment_id'))
    manifest = Manifest.model_validate(dict(contract_version=1, id=package_id, name=name, version=version,
        libraries=[value.strip() for value in libraries.split(',') if value.strip()], tools=[tool]))
    names = ', '.join(f'inputs[{field.name!r}]' for field in manifest.tools[0].inputs) or '(no inputs)'
    handler = f'''"""Adapt reference/{source.name}; keep its calculations and selection rules."""

# ADAPT_BEFORE_BUILD: remove this marker only after completing the adapter.
def run(context, inputs):
    # Database: context.connection (already opened by RobotControl).
    # Form inputs: {names}
'''
    if kind == 'report':
        handler += '''    # Write the workbook under context.output_dir, then return its filename.
    # Example: frame.to_excel(context.output_dir / "report.xlsx", index=False)
    # Return "report.xlsx"; do not use a fixed output path or open a new connection.
    raise NotImplementedError("Adapt the original script before building this package.")
'''
    else:
        handler += '''    # Use parameterized calls. RobotControl owns commit/rollback.
    # Return {"message": "Operation completed."} after making the intended change.
    raise NotImplementedError("Adapt the original script before building this package.")


def preview(context, inputs):
    # Read-only: identify the target and consequences before confirmation.
    # Return {"summary": "What will change", "details": {"ID": target_id}}
    raise NotImplementedError("Implement the read-only preview before building.")
'''
    folder.mkdir(parents=True)
    (folder/'reference').mkdir()
    shutil.copy2(source, folder/'reference'/source.name)
    (folder/'handler.py').write_text(handler, encoding='utf-8')
    (folder/'manifest.json').write_text(json.dumps(manifest.model_dump(), indent=2), encoding='utf-8')
    (folder/'AGENTS.md').write_text('''# Adapt this database package

The original script in reference/ is evidence, not executable package code. Do not
modify it. Implement handler.py using the form inputs in manifest.json. Preserve
the original calculation rules, record selection, column order and formatting.
Replace fixed connections with context.connection, CLI arguments with inputs,
and fixed report paths with context.output_dir. Use the Python logging module.
Do not run standalone main(), install libraries, or embed credentials.

Reports use read-only queries and return the .xlsx filename. Operations need a
read-only preview and parameterized writes; the host owns commit and rollback.
Do not add external side effects. Explain any ambiguous data/selection rule to the
author before changing it. Keep imports free of side effects. Required libraries
must already be bundled in RobotControl. Do not import files from reference/.

List relevant failure cases before changing behavior. Verify with disposable data
through RobotControl's upload/run/download workflow; do not test destructive code
against production. Remove ADAPT_BEFORE_BUILD only when the adapter is complete.
Building a ZIP does not establish calculation accuracy or code safety.
''', encoding='utf-8')
    print(f'Created {folder}\nOriginal preserved in reference/{source.name}. Edit handler.py; AGENTS.md describes the adaptation.')
    print(f'Next: uv run --locked python build_scripts/database_package.py build "{folder}"')


def build(args):
    folder = args.folder.resolve()
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8-sig'))
    if args.version:
        manifest['version'] = args.version
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest, indent=2))
        for file in sorted(folder.iterdir()):
            if file.is_file() and file.suffix in {'.py', '.txt', '.md'} and file.name != 'AGENTS.md':
                source = file.read_bytes()
                if file.suffix == '.py' and b'ADAPT_BEFORE_BUILD' in source:
                    raise ValueError(f'Finish adapting {file.name} and remove ADAPT_BEFORE_BUILD before building.')
                archive.writestr(file.name, source)
    content = buffer.getvalue()
    validated, _ = inspect_archive(content)
    output = args.output or folder.parent/f'{validated.id}-{validated.version}.zip'
    if output.exists() and not args.force:
        raise ValueError(f'{output} already exists. Use a new version or --force to replace it.')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    if args.version:
        (folder/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Built {output.resolve()}\nStructure and Python syntax checked; no package code was executed.')
    print('Next: Database > Manage packages > Add package (or Update). Review and test with disposable data.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    new = commands.add_parser('create', help='Preserve an existing script and create an adapter to edit')
    new.add_argument('folder', type=Path)
    new.add_argument('--script', type=Path, required=True)
    for option in ('name', 'id', 'kind', 'version', 'libraries', 'confirmation'):
        new.add_argument('--'+option)
    new.add_argument('--input', action='append', help='name:type:Label[:choice1,choice2]; repeat for multiple fields')
    ready = commands.add_parser('build', help='Validate and build a package without executing its code')
    ready.add_argument('folder', type=Path)
    ready.add_argument('--version', help='Set a new version in the package and source manifest')
    ready.add_argument('--output', type=Path)
    ready.add_argument('--force', action='store_true')
    args = parser.parse_args()
    try:
        (create if args.command == 'create' else build)(args)
    except (ValueError, OSError, PackageError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
