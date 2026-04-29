from __future__ import annotations

import logging
import time


def configure_logging(level: str) -> None:
    logging.Formatter.converter = time.gmtime
    logging.basicConfig(
        datefmt="%Y-%m-%dT%H:%M:%S",
        force=True,
        format="%(asctime)sZ %(levelname)s %(name)s %(message)s",
        level=_resolve_level(level),
    )


def _resolve_level(level: str) -> int:
    resolved = logging.getLevelName(level.upper())
    if isinstance(resolved, int):
        return resolved
    return logging.INFO
