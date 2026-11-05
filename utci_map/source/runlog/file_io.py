"""Log file reads and writes with their size and duration, warning when they cross config limits."""

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from utci_map.source.contracts import LARGE_IO_WARNING_BYTES, SLOW_IO_WARNING_SECONDS

BYTES_PER_KB = 1024


@contextmanager
def logged_file_io(logger: logging.Logger, action: str, path: Path) -> Iterator[None]:
    """
    Time the I/O inside the block, then log it with the file's size.

    E.g. `with logged_file_io(logger, "Wrote", path): write(path)` logs
    "Wrote output/map/iceland/utci_summary.tif (1.2 MB in 0.3 s)".
    Nothing is logged if the block raises; the error is logged by the program.
    """
    start = time.perf_counter()

    yield

    seconds = time.perf_counter() - start
    size_bytes = path.stat().st_size
    description = f"{action} {path}"

    logger.info("%s (%s in %.1f s)", description, format_size(size_bytes), seconds)
    warn_if_large(logger, description, size_bytes)
    warn_if_slow(logger, description, seconds)


def warn_if_large(logger: logging.Logger, description: str, size_bytes: int) -> None:
    """Log a WARNING when an I/O volume exceeds LARGE_IO_WARNING_BYTES."""
    if size_bytes > LARGE_IO_WARNING_BYTES:
        logger.warning(
            "%s: %s is over the %s limit",
            description,
            format_size(size_bytes),
            format_size(LARGE_IO_WARNING_BYTES),
        )


def warn_if_slow(logger: logging.Logger, description: str, seconds: float) -> None:
    """Log a WARNING when an I/O operation takes longer than SLOW_IO_WARNING_SECONDS."""
    if seconds > SLOW_IO_WARNING_SECONDS:
        logger.warning(
            "%s: took %.1f s, over the %.0f s limit", description, seconds, SLOW_IO_WARNING_SECONDS
        )


def format_size(size_bytes: int) -> str:
    """Format a byte count, e.g. 512 -> '512 B', 1536 -> '1.5 KB', 3_500_000 -> '3.3 MB'."""
    if size_bytes < BYTES_PER_KB:
        return f"{size_bytes} B"

    size = size_bytes / BYTES_PER_KB
    for unit in ("KB", "MB"):
        if size < BYTES_PER_KB:
            return f"{size:.1f} {unit}"
        size /= BYTES_PER_KB

    return f"{size:.1f} GB"
