"""
Pre-execution pipeline for experiment scheduling.

Provides a registry-based mechanism to run reusable pre-execution steps
before Hamilton experiments are dispatched. Steps can register cleanup
handlers so post-run teardown happens automatically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple, Any

from backend.models import ScheduledExperiment
from backend.services.scheduling.database_manager import SchedulingDatabaseManager

logger = logging.getLogger(__name__)


@dataclass
class PreExecutionResult:
    """Result for a single pre-execution step."""
    name: str
    success: bool
    message: str = ""
    cleanup: Optional[Callable[[], None]] = None


@dataclass
class PreExecutionRun:
    """Container summarising a full pre-execution run."""
    success: bool
    steps: List[PreExecutionResult]
    failure_reason: Optional[str] = None
    cleanup_required: bool = False


StepHandler = Callable[[ScheduledExperiment, SchedulingDatabaseManager, Dict[str, Any]], PreExecutionResult]


def _normalize_step_name(raw: str) -> str:
    """Normalise step identifiers so aliases resolve to the same handler."""
    return "".join(ch for ch in raw.lower() if ch.isalnum())


class PreExecutionPipeline:
    """Runs registered pre-execution steps for an experiment."""

    def __init__(self, db_manager: SchedulingDatabaseManager):
        self._db_manager = db_manager
        self._registry: Dict[str, StepHandler] = {}
        self._register_builtin_steps()

    def run(
        self,
        experiment: ScheduledExperiment,
        step_names: Optional[List[str]] = None,
    ) -> PreExecutionRun:
        """Execute configured steps for the experiment."""
        requested_steps = step_names if step_names is not None else (experiment.prerequisites or [])
        if not requested_steps:
            return PreExecutionRun(success=True, steps=[], cleanup_required=False)

        results: List[PreExecutionResult] = []

        for raw_step in requested_steps:
            name, options = self._parse_step(raw_step)
            handler = self._registry.get(name)

            if handler is None:
                reason = f"Unknown pre-execution step '{raw_step}'"
                logger.error(reason)
                self._cleanup(results)
                return PreExecutionRun(success=False, steps=results, failure_reason=reason)

            try:
                result = handler(experiment, self._db_manager, options)
            except Exception as exc:  # pragma: no cover - defensive guard
                reason = f"Pre-execution step '{raw_step}' raised error: {exc}"
                logger.exception(reason)
                self._cleanup(results)
                return PreExecutionRun(success=False, steps=results, failure_reason=reason)

            results.append(result)
            if not result.success:
                reason = result.message or f"Pre-execution step '{raw_step}' failed"
                logger.error(reason)
                self._cleanup(results)
                return PreExecutionRun(success=False, steps=results, failure_reason=reason)

        return PreExecutionRun(success=True, steps=results, cleanup_required=True)

    def cleanup(self, results: List[PreExecutionResult]) -> None:
        """Run cleanup handlers for completed steps."""
        self._cleanup(results)

    def register_step(self, name: str, handler: StepHandler) -> None:
        """Register a new pre-execution step handler."""
        normalised = _normalize_step_name(name)
        self._registry[normalised] = handler

    def _register_builtin_steps(self) -> None:
        self.register_step("ScheduledToRun", self._scheduled_to_run_step)
        self.register_step("ResetHamiltonTables", self._reset_hamilton_tables_step)
        self.register_step("EvoYeastExperiment", self._evoyeast_experiment_step)

    def _parse_step(self, raw: str) -> Tuple[str, Dict[str, Any]]:
        options: Dict[str, Any] = {}
        token = raw or ""

        if ":" in token:
            name_part, arg_part = token.split(":", 1)
            name = name_part
            table_values = [item.strip() for item in arg_part.split(",") if item.strip()]
            if table_values:
                options["tables"] = table_values
        else:
            name = token

        return _normalize_step_name(name), options

    def _cleanup(self, results: List[PreExecutionResult]) -> None:
        for result in reversed(results):
            if result.cleanup is None:
                continue
            try:
                result.cleanup()
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning("Pre-execution cleanup for %s failed: %s", result.name, exc)

    def _scheduled_to_run_step(
        self,
        experiment: ScheduledExperiment,
        db_manager: SchedulingDatabaseManager,
        _: Dict[str, Any],
    ) -> PreExecutionResult:
        if not db_manager.reset_all_scheduled_to_run_flags():
            return PreExecutionResult(
                name="ScheduledToRun",
                success=False,
                message="Failed to reset ScheduledToRun flags",
            )

        if not db_manager.set_scheduled_to_run_flag(experiment.experiment_name, True):
            return PreExecutionResult(
                name="ScheduledToRun",
                success=False,
                message="Failed to set ScheduledToRun flag",
            )

        def cleanup() -> None:
            db_manager.set_scheduled_to_run_flag(experiment.experiment_name, False)

        return PreExecutionResult(
            name="ScheduledToRun",
            success=True,
            message="ScheduledToRun flag configured",
            cleanup=cleanup,
        )

    def _evoyeast_experiment_step(
        self,
        experiment: ScheduledExperiment,
        db_manager: SchedulingDatabaseManager,
        options: Dict[str, Any],
    ) -> PreExecutionResult:
        entries = options.get("tables") or []
        if not entries:
            return PreExecutionResult(
                name="EvoYeastExperiment",
                success=True,
                message="No EvoYeast experiment action configured",
            )

        raw_value = entries[0]
        experiment_id, action = self._parse_evo_yeast_payload(raw_value)

        if not experiment_id:
            return PreExecutionResult(
                name="EvoYeastExperiment",
                success=False,
                message="Missing ExperimentID for EvoYeast pre-execution step",
            )

        if action == "none":
            logger.debug("EvoYeast experiment step configured with no-op action for %s", experiment_id)
            return PreExecutionResult(
                name="EvoYeastExperiment",
                success=True,
                message="EvoYeast experiment link set to no-op",
            )

        if action == "set":
            success = db_manager.set_exclusive_evoyeast_experiment(experiment_id)
            if not success:
                return PreExecutionResult(
                    name="EvoYeastExperiment",
                    success=False,
                    message=f"Failed to mark ExperimentID {experiment_id} as ScheduledToRun",
                )
            return PreExecutionResult(
                name="EvoYeastExperiment",
                success=True,
                message=f"ExperimentID {experiment_id} selected for execution",
            )

        return PreExecutionResult(
            name="EvoYeastExperiment",
            success=False,
            message=f"Unsupported EvoYeast action '{action}'",
        )

    def _parse_evo_yeast_payload(self, token: str) -> Tuple[str, str]:
        """Split the encoded EvoYeast prerequisite payload into id/action."""
        token = (token or "").strip()
        if not token:
            return "", "none"

        if "|" in token:
            experiment_id, action = token.split("|", 1)
        else:
            experiment_id, action = token, "set"

        experiment_id = experiment_id.strip()
        action_normalised = action.strip().lower()

        if action_normalised in {"set", "activate", "exclusive"}:
            action_normalised = "set"
        elif action_normalised in {"none", "noop", "skip"}:
            action_normalised = "none"

        return experiment_id, action_normalised

    def _reset_hamilton_tables_step(
        self,
        experiment: ScheduledExperiment,
        db_manager: SchedulingDatabaseManager,
        options: Dict[str, Any],
    ) -> PreExecutionResult:
        tables = options.get("tables")
        if not db_manager.reset_hamilton_tables(experiment.experiment_name, tables):
            details = ", ".join(tables) if tables else "default set"
            return PreExecutionResult(
                name="ResetHamiltonTables",
                success=False,
                message=f"Failed to reset Hamilton tables ({details})",
            )

        return PreExecutionResult(
            name="ResetHamiltonTables",
            success=True,
            message="Hamilton tables reset",
        )
