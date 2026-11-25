"""Logging setup. Use ``get_logger(__name__)`` everywhere instead of ``print()``."""

import logging

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger once for the process."""
    logging.basicConfig(level=level.upper(), format=_FORMAT)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger."""
    return logging.getLogger(name)
