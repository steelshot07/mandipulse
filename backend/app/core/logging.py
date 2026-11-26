"""Logging setup. Use ``get_logger(__name__)`` everywhere instead of ``print()``."""

import logging

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger once for the process."""
    # force=True: AWS Lambda pre-installs a root handler, which would make basicConfig a no-op.
    logging.basicConfig(level=level.upper(), format=_FORMAT, force=True)
    # httpx logs full request URLs at INFO; data.gov.in URLs carry the API key.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger."""
    return logging.getLogger(name)
