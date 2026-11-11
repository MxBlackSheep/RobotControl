"""
Experiment Execution Service

Executes scheduled experiments with Hamilton HxRun.exe integration.
Replicates VBS script functionality with explicit timeout handling.

Features:
- HxRun.exe command execution with proper argument handling
- Pinned database preparation before launch
- Timeout action selection (continue or cleanup method)
- Process monitoring and timeout handling
"""

import logging
import subprocess
import time
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from backend.models import ScheduledExperiment, JobExecution
from backend.services.scheduling.database_manager import get_scheduling_database_manager
from backend.services.scheduling.experiment_discovery import get_experiment_discovery_service
from backend.services.scheduling.pre_execution import PreExecutionPipeline
from backend.services.scheduling.run_log_monitor import NOT_REPORTED_COMPLETE, TERMINAL_STATES

logger = logging.getLogger(__name__)


@dataclass
class ExecutionConfig:
    """Configuration for experiment execution"""
    hxrun_path: str = r"C:\Program Files\HAMILTON\Bin\HxRun.exe"
    method_base_path: str = r"C:\Program Files\HAMILTON\Methods\LabProtocols\Experiments"


@dataclass
class ExecutionResult:
    """Result of experiment execution"""
    success: bool
    return_code: Optional[int]
    stdout: str
    stderr: str
    execution_time_seconds: float
    command_executed: str
    error_message: Optional[str] = None


def resolve_experiment_path(raw_path: str, config: Optional[ExecutionConfig] = None) -> Path:
    """
    Resolve a schedule's stored path to an absolute .med file location.
    """
    cfg = config or ExecutionConfig()
    candidate = Path(raw_path).expanduser()

    if candidate.suffix.lower() != ".med":
        candidate = candidate.with_suffix(".med")

    if candidate.is_absolute():
        try:
            return candidate.resolve(strict=False)
        except Exception:  # pragma: no cover - defensive
            return candidate

    base_path = Path(cfg.method_base_path).expanduser()
    try:
        resolved_base = base_path.resolve()
    except Exception:  # pragma: no cover - defensive
        resolved_base = base_path

    try:
        methods_root = resolved_base.parents[1]
    except IndexError:
        methods_root = resolved_base

    return (methods_root / candidate).resolve(strict=False)


def resolve_timeout_context(experiment: ScheduledExperiment, current_time: datetime) -> Dict[str, Any]:
    """Calculate the late-start action at dispatch and again immediately before launch."""
    timeout_config = experiment.timeout_config
    action = "continue"
    cleanup_experiment_name = None
    cleanup_experiment_path = None
    timeout_minutes: Optional[int] = None
    if timeout_config:
        action = timeout_config.action or "continue"
        if action not in {"continue", "run_cleanup_and_terminate"}:
            action = "continue"
        cleanup_experiment_name = timeout_config.cleanup_experiment_name
        cleanup_experiment_path = timeout_config.cleanup_experiment_path
        timeout_minutes = timeout_config.timeout_minutes

    timed_out = False
    lateness_minutes = 0
    if timeout_minutes and timeout_minutes > 0 and experiment.start_time:
        deadline = experiment.start_time + timedelta(minutes=timeout_minutes)
        timed_out = current_time > deadline
        if timed_out:
            lateness_minutes = max(0, int((current_time - deadline).total_seconds() / 60))

    return {
        "timed_out": timed_out,
        "action": action,
        "terminate_schedule": timed_out and action == "run_cleanup_and_terminate",
        "lateness_minutes": lateness_minutes if timed_out else 0,
        "cleanup_experiment_path": cleanup_experiment_path,
        "cleanup_experiment_name": cleanup_experiment_name,
    }


class ExperimentExecutor:
    """Service for executing scheduled experiments"""
    
    def __init__(self, run_log_monitor, launch_guard, config: Optional[ExecutionConfig] = None):
        """
        Initialize the experiment executor
        
        Args:
            config: Optional execution configuration
        """
        self.config = config or ExecutionConfig()
        self.db_manager = get_scheduling_database_manager()
        self.pre_execution = PreExecutionPipeline(self.db_manager)
        self.run_log_monitor = run_log_monitor
        self.launch_guard = launch_guard
        
        # Validate Hamilton installation
        if not os.path.exists(self.config.hxrun_path):
            logger.warning(f"Hamilton executable not found at {self.config.hxrun_path}")
        
    
    def execute_experiment(
        self,
        experiment: ScheduledExperiment,
        execution: JobExecution,
        timeout_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Execute a scheduled experiment

        Args:
            experiment: Experiment configuration to execute
            execution: Job execution record to update

        Returns:
            bool: True if execution succeeded, False otherwise
        """
        try:
            logger.info(f"Starting experiment execution: {experiment.experiment_name}")
            effective_timeout_context = self._refresh_timeout_context(
                experiment,
                timeout_context,
            )
            run_target = experiment
            run_pre_execution = True
            if effective_timeout_context.get("timed_out"):
                action = str(effective_timeout_context.get("action") or "continue")
                if action == "run_cleanup_and_terminate":
                    cleanup_path = effective_timeout_context.get("cleanup_experiment_path")
                    cleanup_name = effective_timeout_context.get("cleanup_experiment_name") or "Timeout Cleanup"
                    run_target = ScheduledExperiment(
                        schedule_id=experiment.schedule_id,
                        experiment_name=str(cleanup_name),
                        experiment_path=str(cleanup_path),
                        schedule_type="once",
                        interval_hours=None,
                        estimated_duration=experiment.estimated_duration,
                        log_inactivity_threshold_minutes=experiment.log_inactivity_threshold_minutes,
                        mode=experiment.mode,
                        created_by=execution.schedule_id or "scheduler",
                        is_active=True,
                        timeout_config=None,
                        prerequisites=[],
                        notification_contacts=experiment.notification_contacts,
                    )
                    run_pre_execution = False
                    logger.warning(
                        "Timeout action triggered for %s: running cleanup method %s",
                        experiment.experiment_name,
                        run_target.experiment_name,
                    )

            if run_pre_execution:
                try:
                    self.pre_execution.prepare(experiment, execution.execution_id)
                except Exception as exc:
                    logger.exception('Lab preparation failed for %s', experiment.schedule_id)
                    execution.error_message = str(exc)
                    return False

            result = self._execute_real_command(run_target, execution, time.time(), experiment,
                                                bool(effective_timeout_context.get('terminate_schedule')))

            if result.success:
                state = None
                try:
                    state = self.run_log_monitor.check(execution.execution_id)
                    for _ in range(15):
                        if state and state.run_state in TERMINAL_STATES:
                            break
                        time.sleep(2)
                        state = self.run_log_monitor.check(execution.execution_id)
                except Exception:
                    # The run has ended, so a failed read leaves its outcome unconfirmed.
                    logger.exception("Could not confirm the outcome of %s", experiment.experiment_name)
                    state = None
                if not state or state.run_state != "Complete":
                    result.success = False
                    if state and state.run_state in {"Aborted", "Error"}:
                        result.error_message = f"Hamilton reported run {state.run_guid} as {state.run_state}"
                    else:
                        result.error_message = NOT_REPORTED_COMPLETE

            execution.hamilton_command = result.command_executed

            if result.success:
                logger.info("Experiment completed successfully: %s", run_target.experiment_name)
                execution.error_message = None
                try:
                    discovery_service = get_experiment_discovery_service()
                    discovery_service.db.update_method_usage(run_target.experiment_path)
                    logger.debug("Updated usage stats for %s", run_target.experiment_path)
                except Exception as exc:  # pragma: no cover - best effort only
                    logger.warning("Failed to update usage stats: %s", exc)
            else:
                logger.error("Experiment failed: %s", run_target.experiment_name)
                execution.error_message = result.error_message

            return result.success

        except Exception as exc:
            logger.error("Error executing experiment %s: %s", experiment.experiment_name, exc)
            execution.error_message = f"Execution error: {exc}"
            return False

    def _refresh_timeout_context(
        self,
        experiment: ScheduledExperiment,
        timeout_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Recompute timeout state at launch time, including any queue/wait delays."""
        refreshed = resolve_timeout_context(experiment, datetime.now())
        if timeout_context is not None:
            timeout_context.clear()
            timeout_context.update(refreshed)
            return timeout_context
        return refreshed
    
    def _execute_real_command(self, experiment: ScheduledExperiment, 
                            execution: JobExecution, start_time: float, schedule: ScheduledExperiment,
                            terminate_schedule: bool) -> ExecutionResult:
        """Execute real Hamilton HxRun.exe command"""
        try:
            raw_path = experiment.experiment_path or experiment.experiment_name
            method_path = resolve_experiment_path(raw_path, self.config)

            if not method_path.exists():
                return ExecutionResult(
                    success=False,
                    return_code=-1,
                    stdout="",
                    stderr="",
                    execution_time_seconds=0,
                    command_executed="",
                    error_message=f"Method file not found: {method_path}"
                )

            experiment.experiment_path = str(method_path)

            # Construct command with quotes like VBS: "HxRun.exe" "method.med" -t
            cmd = [
                str(self.config.hxrun_path),
                str(method_path),
                "-t"  # Test mode flag from VBS script
            ]
            
            command_str = f'"{self.config.hxrun_path}" "{method_path}" -t'
            
            logger.info(f"Executing Hamilton command: {command_str}")
            
            # Execute process
            self.run_log_monitor.prepare(schedule, execution, method_path, terminate_schedule)
            with self.launch_guard(schedule, execution):
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
                )
            
            try:
                self.run_log_monitor.launched(execution.execution_id, process.pid)
            except Exception:
                # The process already exists. Continue owning/waiting for it;
                # the observer retries persistence during its next check.
                logger.exception("Could not persist the process launch observation")
            # Log inactivity alerts are advisory; runtime never kills HxRun.
            stdout, stderr = process.communicate()
            return_code = process.returncode
            logger.info("HxRun exited with return code %s", return_code)

            execution_time = time.time() - start_time
            success = return_code == 0
            
            if not success:
                error_msg = f"HxRun.exe failed with return code {return_code}"
                if stderr:
                    error_msg += f": {stderr}"
            else:
                error_msg = None
            
            return ExecutionResult(
                success=success,
                return_code=return_code,
                stdout=stdout,
                stderr=stderr,
                execution_time_seconds=execution_time,
                command_executed=command_str,
                error_message=error_msg
            )
            
        except FileNotFoundError:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr="",
                execution_time_seconds=execution_time,
                command_executed="",
                error_message=f"HxRun.exe not found at {self.config.hxrun_path}"
            )
        
        except Exception as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                return_code=-1,
                stdout="",
                stderr="",
                execution_time_seconds=execution_time,
                command_executed="",
                error_message=f"Process execution error: {str(e)}"
            )
