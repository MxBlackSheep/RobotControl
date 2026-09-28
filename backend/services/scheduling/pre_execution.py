"""Prepare laboratory data before launch, retaining a durable attempt receipt."""
from dataclasses import dataclass, field
import logging
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PreExecutionRun:
    success: bool
    steps: list = field(default_factory=list)
    failure_reason: Optional[str] = None
    cleanup_required: bool = False


class PreExecutionPipeline:
    def __init__(self, db_manager):
        self._db_manager = db_manager

    def run(self, experiment, execution_id):
        try:
            self._db_manager.lab.prepare(experiment, execution_id, experiment.prerequisites or [])
            return PreExecutionRun(success=True)
        except Exception as exc:
            logger.exception('Lab preparation failed for %s', experiment.schedule_id)
            return PreExecutionRun(success=False, failure_reason=str(exc))

    def cleanup(self, results):
        # Existing EvoYeast selection remains active after a run. Do not invent
        # a shared post-run reset: the previous marker cleanup performed no SQL.
        pass
