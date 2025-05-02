#!/usr/bin/env python
"""
logging_helper.py – one-call setup: file + stdout.

Usage:
    from utils.logging_helper import get_logger
    log = get_logger()                  # derives name from caller's file
    log.info("It works")
"""

from __future__ import annotations
import inspect, logging, sys, os
from pathlib import Path

DEF_FMT  = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DEF_DATE = "%Y-%m-%d %H:%M:%S"

def get_logger(level: int = logging.INFO,
               log_dir: str | Path = "logs") -> logging.Logger:
    """
    Create (or return existing) logger whose name is the caller's module
    (e.g. 'writer'). Writes to logs/<name>.log and echoes to stdout.
    """
    # ── derive name from caller ───────────────────────────────────────────
    caller = inspect.stack()[1]
    module = inspect.getmodule(caller[0])
    if module and module.__name__ != "__main__":
        name = module.__name__.split(".")[-1]
    else:
        # called as a script: use the file-stem (e.g., writer, audition)
        name = os.path.splitext(os.path.basename(caller.filename))[0]

    logger = logging.getLogger(name)
    if logger.handlers:                 # already initialised
        return logger

    logger.setLevel(level)

    Path(log_dir).mkdir(exist_ok=True)
    log_path = Path(log_dir) / f"{name}.log"

    # file handler
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter(DEF_FMT, DEF_DATE))
    fh.setLevel(level)

    # console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    ch.setLevel(level)

    logger.addHandler(fh)
    logger.addHandler(ch)
    logger.propagate = False
    return logger
