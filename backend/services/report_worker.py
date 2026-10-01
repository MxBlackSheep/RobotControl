"""One disposable process per trusted report; not an OS security sandbox."""
from pathlib import Path
from types import SimpleNamespace
import threading
import traceback

from backend.services.database_packages import PackageCatalogue, ToolDefinition
from backend.services.report_sources import ReportSources, lookup_rows


def run_report(channel, package_root, entry, definition, inputs, snapshot, folder):
    try:
        # No catalogue startup, seeding, scheduler or source configuration is
        # loaded in the child. It receives only the selected reading identities.
        sources = object.__new__(ReportSources)
        catalogue = object.__new__(PackageCatalogue)
        catalogue.root = Path(package_root)
        catalogue.lock = threading.RLock()
        catalogue.modules = {}
        tool = ToolDefinition.model_validate(definition)
        with sources.connections(snapshot) as connections:
            for field in tool.inputs:
                if field.lookup and field.name in inputs:
                    options = lookup_rows(connections[field.lookup.source], field, inputs, selected=inputs[field.name])['options']
                    if not any(x['value'] == inputs[field.name] for x in options):
                        raise ValueError(f'{field.label} is no longer available. Choose it again.')
            for conn in connections.values():
                conn.timeout = 120
            context = SimpleNamespace(connection=connections.get('primary', next(iter(connections.values()), None)),
                                      connections=connections, output_dir=Path(folder))
            output = catalogue.function(entry, tool.entrypoint)(context, inputs)
        if not isinstance(output, str) or len(output) > 255:
            raise ValueError('Return the Excel filename from the report.')
        channel.send({'output': output})
    except BaseException as exc:
        traceback.print_exc()
        # The parent shows a ValueError as the message and anything else as Details,
        # matching how the report behaved before it ran in its own process.
        channel.send({'error': str(exc)[:4000] or 'Report process failed.', 'expected': isinstance(exc, ValueError)})
    finally:
        channel.close()
