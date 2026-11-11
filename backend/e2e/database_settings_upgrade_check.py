"""Versionless package/source settings upgrade once with backup; truncated and
newer files remain byte-identical and are refused. No installed files are written.
"""
import json
from pathlib import Path
import tempfile
from backend.services.database_packages import PackageCatalogue, PackageError
from backend.services.report_sources import ReportSources

def run():
    with tempfile.TemporaryDirectory(prefix='rc-settings-upgrade-') as directory:
        root=Path(directory); packages=root/'packages'; packages.mkdir(); defaults=root/'defaults'; defaults.mkdir()
        index=packages/'installed.json'; index.write_text('{}')
        sources=root/'report-sources.json'; sources.write_text(json.dumps({'sources':{},'bindings':{}}))
        PackageCatalogue(packages,defaults); ReportSources(root)
        assert json.loads(index.read_text()) == {'version':2,'packages':{}}
        assert json.loads(sources.read_text())['version'] == 2
        assert index.with_name('installed.before_v1.json').read_text() == '{}'
        assert sources.with_name('report-sources.before_v1.json').exists()
        for path, load in [(index,lambda:PackageCatalogue(packages,defaults)),(sources,lambda:ReportSources(root))]:
            for content in ['{bad', '{"version":99}']:
                path.write_text(content)
                try: load()
                except PackageError: pass
                else: raise AssertionError('invalid settings accepted')
                assert path.read_text()==content
    print('PASS stored package and source settings')

if __name__ == '__main__': run()
