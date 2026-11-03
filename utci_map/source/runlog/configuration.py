"""Configure the utci_map program logger to write to a per-run log file and the terminal."""

import logging
from pathlib import Path

from utci_map.source.config import LOGGER_NAME

FILE_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
CONSOLE_FORMAT = "%(levelname)s: %(message)s"


def configure_logging(log_path: Path) -> logging.Logger:
    """
    Send INFO and above from every utci_map module to log_path and to the terminal.

    Create the log directory if needed and return the program logger. Module loggers
    named utci_map.* reach these handlers through propagation.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(FILE_FORMAT))

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    # Keep messages out of the root logger, which other libraries may configure.
    logger.propagate = False

    return logger
