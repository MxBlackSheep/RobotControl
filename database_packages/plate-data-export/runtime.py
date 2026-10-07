"""Timestamped file logging and process-boundary error handling.

RobotControl package: only ``discard_log`` is vendored. ``RunLogger`` (log files) and
``run_logged`` (VENUS exit codes) are left out; RobotControl reports errors itself.
"""


def discard_log(message):
    """Default log sink for reusable functions."""
