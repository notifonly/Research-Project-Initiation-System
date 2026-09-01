from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from loguru import logger

from shared.core.config import settings

if TYPE_CHECKING:
    pass


def setup_logging(project_name: str | None = None) -> None:
    logger.remove()
    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "{message}"
    )
    logger.add(sys.stderr, format=fmt, level="INFO", enqueue=True)

    settings.ensure_dirs()
    log_file = settings.logs_dir / f"{'all' if project_name is None else project_name}.log"
    logger.add(
        log_file,
        format=fmt,
        level="DEBUG",
        rotation="50 MB",
        retention="10 days",
        enqueue=True,
    )

    if project_name:
        proj_file = settings.logs_dir / f"{project_name}.log"
        logger.add(
            proj_file,
            format=fmt,
            level="DEBUG",
            rotation="50 MB",
            retention="10 days",
            enqueue=True,
            filter=lambda record, pn=project_name: record["extra"].get("project") == pn,
        )


def get_logger(project_name: str | None = None):
    if project_name:
        return logger.bind(project=project_name)
    return logger
