#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""게시판 검색기 — 공통 유틸리티·상수·로깅 (Single Source of Truth)"""
from __future__ import annotations

import sys
import os
import json
import hashlib
import logging
import tempfile
import unicodedata
from pathlib import Path
from datetime import datetime


# ═══════════════════════════════════════════════════
#  BASE 경로 (PyInstaller / Nuitka / cx_Freeze / 개발 공통)
# ═══════════════════════════════════════════════════
def _resolve_base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


BASE = _resolve_base()


# ═══════════════════════════════════════════════════
#  로깅
# ═══════════════════════════════════════════════════
_LOG_DIR = BASE / "logs"
try:
    _LOG_DIR.mkdir(exist_ok=True)
except OSError:
    _LOG_DIR = Path(tempfile.gettempdir()) / "board_searcher_logs"
    _LOG_DIR.mkdir(exist_ok=True)


def setup_logger(name: str = "app") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        fh = logging.FileHandler(
            _LOG_DIR / f"{name}.log", encoding="utf-8", delay=True,
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(fh)
    return logger


log = setup_logger()


# ═══════════════════════════════════════════════════
#  상수
# ═══════════════════════════════════════════════════
APP_VERSION = "임금님귀 v1.2.3"
COPYRIGHT = "copyright by 챠리"
EMAIL = "challychoi@me.com"
UPDATE_WARN_DAYS = 30
APP_REGION = "kr-kr"
APP_FLAG = "🇰🇷"

DEFAULT_TOPICS = [
    "🔧 IT 하드웨어", "💻 IT 소프트웨어", "🤖 IT AI", "🪙 코인",
    "📈 주식", "🏠 부동산", "😄 유머", "🆕 신제품", "🏥 건강",
]
DEFAULT_KEYWORD_COUNT = 3
DEFAULT_HOURS = 36

SETTINGS_FILE = BASE / "app_settings.json"
SITES_CONFIG = BASE / "sites_config.json"


# ═══════════════════════════════════════════════════
#  이모지 유틸리티 — unicodedata 기반 정확한 판별
# ═══════════════════════════════════════════════════
def is_emoji(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    if cp >= 0x1F000:
        return True
    return unicodedata.category(ch) == "So"


def strip_leading_emoji(name: str) -> str:
    if not name:
        return name
    if is_emoji(name[0]):
        return name[1:].strip()
    return name


def get_topic_icon(name: str) -> str:
    if name and is_emoji(name[0]):
        return name[0]
    return "📌"


def get_display_name(name: str) -> str:
    return strip_leading_emoji(name) or name


# ═══════════════════════════════════════════════════
#  파일 I/O — 원자적 쓰기 + .bak 백업
# ═══════════════════════════════════════════════════
def atomic_write(path: Path, content: str, encoding: str = "utf-8"):
    path = Path(path)
    if path.exists():
        bak = path.with_suffix(path.suffix + ".bak")
        try:
            bak.write_bytes(path.read_bytes())
        except Exception as e:
            log.warning("Backup failed for %s: %s", path.name, e)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_json(path: Path) -> dict:
    if not path or not Path(path).exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.error("JSON load failed (%s): %s", Path(path).name, e)
        return {}


# ═══════════════════════════════════════════════════
#  날짜 기반 고정 시드 (hashlib — 프로세스 재시작해도 동일 색상)
# ═══════════════════════════════════════════════════
def date_seed(date_str: str | None = None) -> int:
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    return int(hashlib.md5(date_str.encode()).hexdigest()[:8], 16)


# ═══════════════════════════════════════════════════
#  단일 인스턴스 보호
# ═══════════════════════════════════════════════════
_lock_fd = None


def acquire_instance_lock() -> bool:
    global _lock_fd
    lock_path = BASE / ".instance.lock"
    try:
        _lock_fd = open(lock_path, "r+" if lock_path.exists() else "w+")
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(_lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fd.seek(0)
        _lock_fd.truncate()
        _lock_fd.write(str(os.getpid()) + "\n")
        _lock_fd.flush()
        return True
    except (IOError, OSError, ImportError) as e:
        log.warning("Instance lock failed: %s", e)
        if _lock_fd:
            try:
                _lock_fd.close()
            except Exception:
                pass
            _lock_fd = None
        return False
