"""One disposable process per trusted report or preparation step; not an OS security sandbox."""
from pathlib import Path
from types import SimpleNamespace
import threading
import traceback

from backend.services.database_packages import PackageCatalogue, ToolDefinition
from backend.services.report_sources import ReportSources, lookup_rows


def _runtime(package_root):
    # No catalogue startup, seeding, scheduler or source configuration is loaded in
    # the child. It receives only the selected connection identities.
    sources = object.__new__(ReportSources)
    catalogue = object.__new__(PackageCatalogue)
    catalogue.root = Path(package_root)
    catalogue.lock = threading.RLock()
    catalogue.modules = {}
    return sources, catalogue


def _check_choices(tool, inputs, connections):
    for field in tool.inputs:
        if field.lookup and field.name in inputs:
            options = lookup_rows(connections[field.lookup.source], field, inputs, selected=inputs[field.name])['options']
            if not any(x['value'] == inputs[field.name] for x in options):
                raise ValueError(f'{field.label} is no longer available. Choose it again.')


def run_report(channel, package_root, entry, definition, inputs, snapshot, folder):
    try:
        sources, catalogue = _runtime(package_root)
        tool = ToolDefinition.model_validate(definition)
        with sources.connections(snapshot) as connections:
            _check_choices(tool, inputs, connections)
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


HOST_COMMITS = 'The host commits a preparation step: do not commit, roll back or change autocommit.'


class _HostOwned:
    """The connection or cursor a preparation step writes through. The host alone commits,
    so a step that raises has committed nothing through this API (the recovery note relies
    on it). Not a sandbox: trusted code could still open its own connection."""

    def __init__(self, target, cursor=False):
        object.__setattr__(self, '_target', target)
        object.__setattr__(self, '_cursor', cursor)

    def commit(self):
        raise ValueError(HOST_COMMITS)

    def rollback(self):
        raise ValueError(HOST_COMMITS)

    def cursor(self):
        return _HostOwned(self._target.cursor(), cursor=True)

    def execute(self, *args, **kwargs):
        result = self._target.execute(*args, **kwargs)
        # pyodbc returns the cursor; keep it wrapped so cursor.commit() is refused too.
        return _HostOwned(result, cursor=True) if result is not None and hasattr(result, 'commit') else result

    def __getattr__(self, name):
        if name == 'connection':
            raise ValueError(HOST_COMMITS)
        return getattr(self._target, name)

    def __setattr__(self, name, value):
        raise ValueError(HOST_COMMITS)

    def __iter__(self):
        return iter(self._target)

    def __enter__(self):
        # pyodbc's `with connection:` commits or closes it; the connection belongs to the host.
        if not self._cursor:
            raise ValueError(HOST_COMMITS)
        return self

    def __exit__(self, *exc):
        self._target.close()


def run_preparation(channel, package_root, entry, definition, inputs, snapshot, target, run):
    """Run prepare(context, inputs) in one transaction on the operation connection.

    Messages: {'committing': True} just before COMMIT, then {'committed': True, 'message'}.
    An error before 'committing' means nothing was written. The parent treats 'committing'
    without 'committed' (crash, timeout) as an unknown outcome.
    """
    step_error = None
    try:
        sources, catalogue = _runtime(package_root)
        tool = ToolDefinition.model_validate(definition)
        with sources.connections(snapshot) as connections, sources.open(target) as conn:
            conn.timeout = 60
            cursor = conn.cursor()
            cursor.execute("SET XACT_ABORT ON; SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            cursor.close()
            try:
                _check_choices(tool, inputs, connections)
                context = SimpleNamespace(connection=_HostOwned(conn), connections=connections, run=SimpleNamespace(**run))
                result = catalogue.function(entry, tool.entrypoint)(context, inputs)
                if result is not None and not isinstance(result, dict):
                    raise ValueError('Return a dictionary such as {"message": "..."} from prepare.')
                message = str((result or {}).get('message') or 'Preparation completed.')[:500]
            except BaseException as exc:
                # sources.open reports any driver error in its block as a connection problem;
                # the receipt needs the step's own error (e.g. a stored procedure's RAISERROR).
                step_error = exc
                conn.rollback()
                raise
            channel.send({'committing': True})
            conn.commit()
        channel.send({'committed': True, 'message': message})
    except BaseException as exc:
        traceback.print_exc()
        channel.send({'error': str(step_error or exc)[:4000] or 'Preparation process failed.'})
    finally:
        channel.close()
