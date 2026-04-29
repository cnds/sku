from __future__ import annotations

import logging

from logging_utils import configure_logging


def test_configure_logging_uses_standard_logging_format() -> None:
    root_logger = logging.getLogger()
    previous_handlers = list(root_logger.handlers)
    previous_level = root_logger.level

    try:
        configure_logging("INFO")

        assert root_logger.level == logging.INFO
        assert root_logger.handlers
        formatter = root_logger.handlers[0].formatter
        assert formatter is not None
        assert formatter._fmt == "%(asctime)sZ %(levelname)s %(name)s %(message)s"
    finally:
        root_logger.handlers = previous_handlers
        root_logger.setLevel(previous_level)
