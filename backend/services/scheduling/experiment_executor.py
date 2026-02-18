"""
Experiment Execution Service

Executes scheduled experiments with Hamilton HxRun.exe integration.
Replicates VBS script functionality with explicit timeout handling.

Features:
- HxRun.exe command execution with proper argument handling
- Database prerequisite configuration (ScheduledToRun flags)
- Timeout action selection (continue or cleanup method)
- Process monitoring and timeout handling
- Mock mode support for development environments
"""

import logging
import subprocess
import time
import threading
import os
import signal
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path
from backend.models import ScheduledExperiment, JobExecution
from backend.services.scheduling.database_manager import get_scheduling_database_manager
from backend.services.scheduling.experiment_discovery import get_experiment_discovery_service
from backend.services.scheduling.pre_execution import PreExecutionPipeline

logger = logging.getLogger(__name__)


@dataclass
class ExecutionConfig:
    """Configuration for experiment execution"""
    hxrun_path: str = r"C:\Program Files\HAMILTON\Bin\HxRun.exe"
    method_base_path: str = r"C:\Program Files\HAMILTON\Methods\LabProtocols\Experiments"
    execution_timeout_minutes: int = 120  # Maximum execution time


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


class ExperimentExecutor:
    """Service for executing scheduled experiments"""
    
    def __init__(self, config: Optional[ExecutionConfig] = None):
        """
        Initialize the experiment executor
        
        Args:
            config: Optional execution configuration
        """
        self.config = config or ExecutionConfig()
        self.db_manager = get_scheduling_database_manager()
        self.pre_execution = PreExecutionPipeline(self.db_manager)
        self._active_executions: Dict[str, subprocess.Popen] = {}
        self._execution_lock = threading.RLock()
        
        # Validate Hamilton installation
        if not os.path.exists(self.config.hxrun_path):
            logger.warning(f"Hamilton executable not found at {self.config.hxrun_path}")
        
        logger.info("Experiment executor initialized")
    
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
        pre_run = None
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
                    if not cleanup_path:
                        execution.error_message = (
                            "Timeout action requires cleanup_experiment_path but none was configured"
                        )
                        logger.error(
                            "Timeout cleanup path missing for %s",
                            experiment.experiment_name,
                        )
                        return False
                    cleanup_name = effective_timeout_context.get("cleanup_experiment_name") or "Timeout Cleanup"
                    run_target = ScheduledExperiment(
                        schedule_id=experiment.schedule_id,
                        experiment_name=str(cleanup_name),
                        experiment_path=str(cleanup_path),
                        schedule_type="once",
                        interval_hours=None,
                        estimated_duration=experiment.estimated_duration,
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
                pre_run = self.pre_execution.run(experiment)
                if not pre_run.success:
                    execution.error_message = pre_run.failure_reason or "Pre-execution pipeline failed"
                    logger.error("Pre-execution failed for %s: %s", experiment.experiment_name, execution.error_message)
                    return False

            result = self._execute_hamilton_command(run_target, execution)

            if result.success:
                abort_note = self.db_manager.should_block_due_to_abort(experiment)
                if abort_note:
                    logger.warning("Hamilton reported last run as aborted for %s: %s", experiment.experiment_name, abort_note)
                    result.success = False
                    result.error_message = abort_note

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

        finally:
            if pre_run and pre_run.cleanup_required:
                self.pre_execution.cleanup(pre_run.steps)

    def stop_experiment(self, schedule_id: str) -> bool:
        """
        Stop a running experiment
        
        Args:
            schedule_id: ID of the experiment to stop
            
        Returns:
            bool: True if stopped successfully
        """
        try:
            with self._execution_lock:
                if schedule_id not in self._active_executions:
                    logger.warning(f"No active execution found for schedule: {schedule_id}")
                    return False
                
                process = self._active_executions[schedule_id]
                
                # Terminate HxRun.exe process
                if os.name == 'nt':  # Windows
                    try:
                        process.send_signal(signal.CTRL_BREAK_EVENT)
                    except ProcessLookupError:
                        logger.warning(f"Process {schedule_id} already terminated")
                    except Exception as e:
                        logger.warning(f"Failed to send CTRL_BREAK to {schedule_id}: {e}")
                        process.terminate()
                else:
                    process.terminate()
                
                # Wait for process to terminate
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                
                # Remove from active executions
                del self._active_executions[schedule_id]
                
                logger.info(f"Experiment stopped: {schedule_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error stopping experiment {schedule_id}: {e}")
            return False
    
    def get_active_executions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about active executions
        
        Returns:
            Dictionary mapping schedule_id to execution info
        """
        active_info = {}
        
        with self._execution_lock:
            for schedule_id, process in self._active_executions.items():
                active_info[schedule_id] = {
                    "pid": process.pid,
                    "poll": process.poll(),
                    "returncode": process.returncode
                }
        
        return active_info

    def _refresh_timeout_context(
        self,
        experiment: ScheduledExperiment,
        timeout_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Recompute timeout state at launch time, including any queue/wait delays."""
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
            now = datetime.now()
            timed_out = now > deadline
            if timed_out:
                lateness_minutes = max(0, int((now - deadline).total_seconds() / 60))

        refreshed = {
            "timed_out": timed_out,
            "action": action,
            "terminate_schedule": timed_out and action == "run_cleanup_and_terminate",
            "lateness_minutes": lateness_minutes if timed_out else 0,
            "cleanup_experiment_path": cleanup_experiment_path,
            "cleanup_experiment_name": cleanup_experiment_name,
        }
        if timeout_context is not None:
            timeout_context.clear()
            timeout_context.update(refreshed)
            return timeout_context
        return refreshed
    
    def _execute_hamilton_command(self, experiment: ScheduledExperiment, 
                                execution: JobExecution) -> ExecutionResult:
        """
        Execute the Hamilton HxRun.exe command
        
        Args:
            experiment: Experiment to execute
            execution: Execution record
            
        Returns:
            ExecutionResult with execution details
        """
        start_time = time.time()
        
        try:
            return self._execute_real_command(experiment, execution, start_time)
                
        except Exception as e:
            execution_time = time.time() - start_time
            return ExecutionResult(
                success=False,
                return_code=None,
                stdout="",
                stderr="",
                execution_time_seconds=execution_time,
                command_executed="",
                error_message=f"Command execution error: {str(e)}"
            )
    
    
    def _execute_real_command(self, experiment: ScheduledExperiment, 
                            execution: JobExecution, start_time: float) -> ExecutionResult:
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
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            )
            
            # Track active execution
            with self._execution_lock:
                self._active_executions[experiment.schedule_id] = process
            
            try:
                # Wait for completion with timeout
                timeout_seconds = self.config.execution_timeout_minutes * 60
                stdout, stderr = process.communicate(timeout=timeout_seconds)
                return_code = process.returncode
                
            except subprocess.TimeoutExpired:
                logger.warning(f"Execution timeout for {experiment.experiment_name}, terminating process")
                process.kill()
                stdout, stderr = process.communicate()
                return_code = -1
                
            finally:
                # Remove from active executions
                with self._execution_lock:
                    self._active_executions.pop(experiment.schedule_id, None)
            
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
    


# Singleton instance management
_experiment_executor_instance = None
_experiment_executor_lock = threading.Lock()


def get_experiment_executor() -> ExperimentExecutor:
    """
    Get the singleton ExperimentExecutor instance
    
    Returns:
        ExperimentExecutor: The experiment executor instance
    """
    global _experiment_executor_instance
    
    with _experiment_executor_lock:
        if _experiment_executor_instance is None:
            _experiment_executor_instance = ExperimentExecutor()
            
    return _experiment_executor_instance
