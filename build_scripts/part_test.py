"""Print the RobotControl part-test plan. Run from the repository root."""
import argparse
import ast
from collections import defaultdict
from fnmatch import fnmatchcase
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
UV = "uv run --locked python"
SHUTDOWN = "backend/e2e/packaged_shutdown_check.py"
DATABASE_SMOKE = "backend/e2e/packaged_database_smoke.py"
FULL = "Full source check (shared or unmapped)"


def area(paths, *, e2e="", units="", browser="", vitest=""):
    checks = [f"backend/e2e/{name}_check.py" for name in e2e.split()]
    checks.extend(f"backend/tests/test_{name}.py" for name in units.split())
    checks.extend(f"frontend/e2e/{name}.spec.ts" for name in browser.split())
    checks.extend(f"frontend/src/{name}" for name in vitest.split())
    return paths.split(), checks


AREAS = {
    "Packaging": (
        "database_packages/* build_scripts/pyinstaller_build.py build_scripts/database_package.py "
        "build_scripts/embed_resources.py build_scripts/fetch_ffmpeg.py build_scripts/icon/* "
        "build_scripts/notices/* backend/services/embedded_resources.py backend/version.py "
        "pyproject.toml uv.lock .python-version frontend/package*.json".split(),
        ("backend/e2e/packaged_viewer_smoke.py", "backend/e2e/packaged_walkthrough.py", DATABASE_SMOKE, SHUTDOWN),
    ),
    "Overview and robot status": area(
        "frontend/src/pages/Dashboard.tsx frontend/src/components/overview/* frontend/src/components/RobotAttentionBanner.tsx "
        "frontend/src/hooks/useRobotStatus.ts frontend/src/components/ExperimentStatus.tsx backend/services/experiment_monitor.py",
        units="hamilton_states", e2e="service_unavailable", browser="system-pages phone-runs phone-navigation pyhsl appearance"),
    "Labware": area(
        "frontend/src/pages/LabwarePage.tsx frontend/src/components/labware/* frontend/src/services/labwareApi.ts "
        "backend/api/labware.py backend/services/labware_*.py",
        units="labware_api", browser="labware labware-layout-stability cytomat-spatial phone-navigation"),
    "Database viewer": area(
        "backend/api/database.py backend/services/workspace_database.py frontend/src/pages/DatabasePage.tsx "
        "frontend/src/components/DatabaseTable* frontend/src/components/StoredProcedures.tsx "
        "frontend/src/components/databaseExport.ts frontend/src/components/DatabaseSettings.tsx",
        units="database_service", e2e="database_workspace", browser="database database-workspace inspection-pagination database-restore",
        vitest="components/DatabaseTable.test.tsx"),
    "Backup and restore": area(
        "backend/api/backup.py backend/services/backup.py frontend/src/components/DatabaseRestore.tsx",
        e2e="backup_boundary backup_restore restore_guard service_unavailable", browser="database-restore database"),
    "Database tools": area(
        "backend/api/database_tools.py backend/services/database_tools.py backend/services/database_packages.py "
        "backend/services/report_*.py backend/services/tool_definition.py frontend/src/components/DatabaseTools.tsx "
        "frontend/src/components/DatabasePackages.tsx frontend/src/components/ToolAuthoring.tsx "
        "frontend/src/components/Report*.tsx frontend/src/pages/DatabasePage.tsx database_packages/examples/*",
        e2e="database_tools database_settings_upgrade bundled_tools draft_replace tool_authoring package_upgrade "
            "experiment_registration plate_export preparation_step scheduling_lab database_workspace",
        browser="database-tools database-workspace experiments scheduling-lab"),
    "Experiment registration": area(
        "database_packages/champions-experiment/* backend/api/experiments.py backend/services/experiments.py",
        e2e="experiment_registration service_unavailable package_upgrade", browser="experiments system-pages"),
    "Bundled tools": area("database_packages/culture-history/* database_packages/delete-experiment/*",
                         e2e="bundled_tools database_tools", browser="database-tools"),
    "Plate data export": area("database_packages/plate-data-export/*", e2e="plate_export"),
    "Experiment preparation": area("database_packages/evoyeast-experiment/*", e2e="scheduling_lab preparation_step experiment_registration package_upgrade",
                                   browser="scheduling-lab"),
    "Run execution": area(
        "backend/services/scheduling/experiment_executor.py backend/services/scheduling/pre_execution.py",
        units="hxrun_maintenance_executor scheduler_single_worker run_log_monitor",
        e2e="failed_occurrence package_upgrade preparation_step pyhsl_runner restore_guard scheduling_lab simulation_mode"),
    "Method library": area(
        "backend/services/scheduling/method_library.py backend/services/scheduling/experiment_discovery.py",
        units="method_import method_library method_path_change", browser="operations",
        vitest="components/scheduling/MethodLibraryPanel.test.tsx components/scheduling/FolderImportDialog.test.tsx "
               "components/scheduling/MethodPathDialog.test.tsx components/scheduling/MethodExplorer.test.tsx"),
    "Scheduling": area(
        "backend/api/scheduling.py backend/services/scheduling/scheduler_engine.py frontend/src/pages/SchedulingPage.tsx "
        "frontend/src/pages/HeldRunPage.tsx frontend/src/components/scheduling/* frontend/src/services/schedulingApi.ts "
        "frontend/src/hooks/useScheduling.ts frontend/src/types/scheduling.ts frontend/src/components/ScheduleActions.tsx "
        "frontend/src/components/ExecutionHistory.tsx",
        e2e="failed_occurrence restore_guard run_timing simulation_mode pyhsl_runner scheduling_lab preparation_step "
            "package_upgrade stored_data notification_delivery auth_observation_upgrade",
        units="scheduler_manual_recovery scheduler_single_worker scheduling_create_guard hxrun_maintenance_executor "
              "run_log_monitor method_import method_library method_path_change sqlite_safety process_monitor notifications",
        browser="operations scheduling-lab phone-runs experiments pyhsl appearance system-pages",
        vitest="components/scheduling/ImprovedScheduleForm.test.tsx components/scheduling/RecoverySafetyPanel.test.tsx "
               "components/scheduling/FolderImportDialog.test.tsx components/scheduling/MethodExplorer.test.tsx "
               "components/scheduling/MethodLibraryPanel.test.tsx components/scheduling/MethodPathDialog.test.tsx "
               "components/scheduling/NotificationEmailSettingsPanel.test.tsx"),
    "HxRun maintenance": area(
        "backend/services/hxrun_maintenance.py backend/api/maintenance.py frontend/src/pages/MaintenancePage.tsx "
        "frontend/src/services/hxrunMaintenanceApi.ts",
        e2e="hxrun_maintenance", units="hxrun_maintenance_api hxrun_maintenance_executor", browser="appearance system-pages"),
    "PyHSL": area(
        "backend/services/pyhsl_*.py backend/api/pyhsl.py backend/services/scheduling/pyhsl_runner.py "
        "frontend/src/pages/PyHslRunPage.tsx frontend/src/components/*PyHsl*.tsx frontend/src/hooks/usePyHslStatus.ts",
        e2e="pyhsl_client pyhsl_runner", browser="pyhsl phone-runs system-pages"),
    "Camera and recordings": area(
        "backend/api/camera.py backend/services/camera*.py backend/services/automatic_recording.py "
        "backend/services/live_streaming.py backend/services/streaming_*.py backend/services/h264_encoder.py "
        "backend/services/shared_frame_buffer.py backend/services/storage_manager.py backend/services/clip_transcoder.py "
        "frontend/src/pages/CameraPage.tsx frontend/src/components/Camera*.tsx frontend/src/components/camera/* "
        "frontend/src/components/LiveFrame.tsx frontend/src/hooks/useLiveViewSocket.ts frontend/src/hooks/useRecordingDownload.ts",
        e2e="camera_watchdog clip_transcode video_retention alert_clips startup_cleanup",
        units="camera camera_worker camera_control_api camera_download_api automatic_recording streaming_lifecycle "
              "frame_delivery h264_encoder attachment_lifetime", browser="camera operations system-pages",
        vitest="components/CameraControls.test.tsx"),
    "Notifications": area("backend/services/notification*.py backend/services/alert_email.py",
                          e2e="notification_delivery alert_clips pyhsl_client", units="attachment_lifetime notifications notification_responsiveness",
                          browser="scheduling-lab", vitest="components/scheduling/NotificationEmailSettingsPanel.test.tsx"),
    "Log readers": area("backend/services/log_readers.py backend/api/logfiles.py frontend/src/pages/LogFilePage.tsx "
                        "frontend/src/components/Log*.tsx frontend/src/services/logFileApi.ts",
                        e2e="log_preview", units="logfiles_api", browser="logs appearance"),
    "System status": area("backend/api/monitoring.py backend/services/health_sampler.py backend/services/resource_diagnostics.py "
                          "frontend/src/pages/MonitoringPage.tsx frontend/src/hooks/useMonitoring.ts",
                          units="health_sampler health_responsiveness resource_diagnostics", browser="system-pages"),
    "SQLite health": area("frontend/src/components/SQLiteHealthPanel.tsx backend/api/sqlite_health.py backend/services/sqlite_health.py",
                          units="sqlite_safety", browser="system-pages", vitest="components/SQLiteHealthPanel.test.tsx"),
    "Visual review": area("frontend/e2e/visual/*", browser="visual/review"),
    "Stored method paths": area("backend/services/scheduling/method_library.py", e2e="stored_data"),
    "Scheduling route responsiveness": area("backend/api/scheduling.py", units="notification_responsiveness"),
    "Table viewer sources": area("frontend/src/components/ReportInputs.tsx", browser="database"),
    "Run deck sizing": area("frontend/src/components/labware/useLabwareWorkspace.ts", browser="pyhsl"),
    "Scheduling queue status": area("frontend/src/hooks/useRobotStatus.ts", browser="operations"),
    "Held run trace": area("frontend/src/services/logFileApi.ts", browser="system-pages"),
}


def git_paths(*args):
    output = subprocess.check_output(["git", *args], cwd=ROOT)
    return {path.decode("utf-8") for path in output.split(b"\0") if path}


def changed_paths(base):
    ancestor = subprocess.check_output(["git", "merge-base", base, "HEAD"], cwd=ROOT, text=True).strip()
    diff = ["diff", "--name-only", "--no-renames", "-z"]
    return (git_paths(*diff, ancestor, "HEAD") | git_paths(*diff, "--cached")
            | git_paths(*diff) | git_paths("ls-files", "--others", "--exclude-standard", "-z"))


def imported_modules(check):
    for node in ast.walk(ast.parse(check.read_bytes(), filename=str(check))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            parent = node.module or ""
            if node.level == 1:
                parent = ("backend.e2e." + parent).rstrip(".")
            yield parent
            yield from (f"{parent}.{alias.name}" for alias in node.names)


def reasons_for(path):
    if Path(path).suffix.lower() in {".md", ".rst"}:
        return ["Documentation"]
    if path.startswith(("backend/e2e/packaged_", "frontend/e2e/packaged-")):
        return ["Packaging"]
    if (ROOT / path).is_file() and any(fnmatchcase(path, pattern) for pattern in (
        "backend/tests/test_*.py", "backend/e2e/*_check.py", "frontend/e2e/*.spec.ts",
        "frontend/src/*.test.ts", "frontend/src/*.test.tsx",
    )):
        return ["Changed check"]
    matches = [name for name, (patterns, _) in AREAS.items()
               if any(fnmatchcase(path, pattern) for pattern in patterns)]
    if not matches or matches == ["Packaging"]:
        matches.append(FULL)
    return matches


def plan(paths):
    reasons = defaultdict(set)
    picked = set()
    changed_modules = {path[:-3].replace("/", "."): path for path in paths if fnmatchcase(path, "backend/e2e/*.py")}
    if changed_modules:
        checks = set((ROOT / "backend/e2e").glob("*_check.py")) | {ROOT / p for p in AREAS["Packaging"][1]}
        for check in checks:
            for module in changed_modules.keys() & set(imported_modules(check)):
                reasons["Direct importer"].add(changed_modules[module])
                picked.add(check.relative_to(ROOT).as_posix())
    for path in sorted(paths):
        for reason in reasons_for(path):
            if reason != FULL or path not in reasons.get("Direct importer", ()):
                reasons[reason].add(path)

    picked.update(reasons.get("Changed check", ()))
    for name, (_, checks) in AREAS.items():
        for check in checks:
            if not (ROOT / check).is_file():
                raise SystemExit(f"{name}: mapped check is missing: {check}")
        if name in reasons and name != "Packaging":
            picked.update(checks)
    full = FULL in reasons
    package_checks = picked.intersection(AREAS["Packaging"][1])
    picked -= package_checks
    if "Packaging" in reasons:
        package_checks.update(set(AREAS["Packaging"][1]) - {SHUTDOWN})
        package_checks.update({SHUTDOWN}.intersection(paths))
    for reason, changed in reasons.items():
        print(f"{reason}: {', '.join(sorted(changed))}")
    if not (picked or full or package_checks):
        print("Documentation only; no checks selected." if paths else "No changed paths.")
        return

    def files(prefix):
        return sorted(path for path in picked if path.startswith(prefix))

    checks = files("backend/e2e/")
    if full:
        checks = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "backend/e2e").glob("*_check.py")
                        if p != ROOT / SHUTDOWN)
    units = files("backend/tests/")
    specs = files("frontend/e2e/")
    visual = "frontend/e2e/visual/review.spec.ts"
    behavior = [path.removeprefix("frontend/") for path in specs if path != visual]
    vitest = [path.removeprefix("frontend/") for path in files("frontend/src/")]
    print("\nPowerShell 7 (repository root)")
    if checks or units or full or package_checks:
        print("$env:PYTHONPATH = (Get-Location).Path")
    if full or "backend/tests/test_h264_encoder.py" in units or "backend/e2e/clip_transcode_check.py" in checks:
        print(f"{UV} build_scripts/fetch_ffmpeg.py")
    if full or units:
        print("uv run --locked pytest " + ("backend/tests" if full else " ".join(units)))
    for check in checks:
        args = " ../Shou_LHR_PythonPackage ../Shou_Lab" if check.endswith("/experiment_registration_check.py") else ""
        print(f"{UV} {check}{args}")
    if full or vitest:
        print("npm --prefix frontend test" + (" -- " + " ".join(vitest) if not full else ""))
    if full or specs or package_checks:
        print("npm --prefix frontend run build")
    if full or specs:
        print("Push-Location frontend")
        if full or behavior:
            print("npx playwright test" + (" " + " ".join(behavior) if not full else ""))
        if full or visual in specs:
            print("npx playwright test --config playwright.visual.config.ts")
        print("Pop-Location")
    if full:
        for script in ("status-stall-probe.py", "native-zoom.cjs", "labware-native-zoom.cjs"):
            print(f"# Manual check omitted: frontend/e2e/{script}")
    if package_checks:
        print("$candidate = 'dist/part-test-' + [guid]::NewGuid()")
        print(f"{UV} build_scripts/embed_resources.py")
        print('uv run --locked --group build python build_scripts/pyinstaller_build.py --output-dir $candidate')
        for check in sorted(package_checks - {SHUTDOWN}):
            print(f'{UV} {check} "$candidate/RobotControl"')
        if DATABASE_SMOKE in package_checks:
            print(f'{UV} {DATABASE_SMOKE} "$candidate/RobotControl" --authoring '
                  '--evidence test-output/part-test-authoring')
        if SHUTDOWN in package_checks:
            print("# Owner-run in a Windows console with a camera")
            print(f'{UV} {SHUTDOWN} "$candidate/RobotControl"')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("paths", nargs="*", help="repository-relative changed files")
    args = parser.parse_args()
    plan({Path(path).as_posix() for path in args.paths} if args.paths else changed_paths(args.base))
