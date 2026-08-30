"""Replay - rehearse a change before you ship it."""

import logging as _logging


class _DropEmptyToolInputWarning(_logging.Filter):
    """Drop one noisy Strands warning.

    A tool whose arguments are all optional is legitimately invoked with an
    empty input, which Strands logs as a failed JSON parse before correctly
    defaulting to an empty dict. The call succeeds; only the message is wrong.
    """

    def filter(self, record: _logging.LogRecord) -> bool:
        return "failed to parse tool input json" not in record.getMessage()


_logging.getLogger("strands.event_loop.streaming").addFilter(
    _DropEmptyToolInputWarning()
)
