#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
게시판 검색기 — 공통 유틸리티·상수·로깅 (Single Source of Truth)
═══════════════════════════════════════════════════════════════════
모든 모듈이 공유하는 상수, 경로, 유틸리티 함수를 한 곳에 정의합니다.
버전 정보, 기본 토픽, 파일 경로 등의 Single Source of Truth.

copyright by 챠리 (challychoi@me.com)
"""
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
APP_VERSION = "임금님귀 v1.3.0"
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
DEFAULT_REPORT_HEADER = (
    "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "✨ 토픽별 핫키워드 (토픽당 설정 개수만큼)\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━"
)

SETTINGS_FILE = BASE / "app_settings.json"
SITES_CONFIG = BASE / "sites_config.json"


# ═══════════════════════════════════════════════════
#  토픽 설정 → 검색용 config 변환 (DRY: run_report + format_for_messenger 공통)
# ═══════════════════════════════════════════════════
def build_topic_config(settings: dict) -> dict[str, int]:
    """
    settings 딕셔너리에서 활성화된 토픽과 키워드 수를
    {토픽명: 키워드수} 형태로 추출합니다. topic_order 순서 반영.

    main.py의 run_report()와 report_engine.py의 format_for_messenger()
    양쪽에서 동일한 로직을 중복하지 않도록 하는 Single Source 유틸리티.

    Args:
        settings: 앱 설정 딕셔너리

    Returns:
        dict[str, int]: {토픽명: 키워드수} 순서 보장 딕셔너리
    """
    topic_config: dict[str, int] = {}
    all_t = settings.get("topics", []) + settings.get("custom_topics", [])
    by_name: dict[str, int] = {}
    for t in all_t:
        if t.get("enabled", True):
            by_name[t["name"]] = max(
                1, min(10, int(t.get("keyword_count", DEFAULT_KEYWORD_COUNT))),
            )
    topic_order = settings.get("topic_order") or []
    if topic_order:
        for name in topic_order:
            if name in by_name:
                topic_config[name] = by_name.pop(name)
    for name, kw in by_name.items():
        topic_config[name] = kw
    if not topic_config:
        for name in DEFAULT_TOPICS:
            topic_config[name] = DEFAULT_KEYWORD_COUNT
    return topic_config


# ═══════════════════════════════════════════════════
#  이모지 유틸리티 — unicodedata 기반 정확한 판별
#  주의: 현재 name[0] 단일 코드포인트만 검사하므로
#  국기(🇰🇷) 같은 복합 이모지(Regional Indicator 2개)나
#  ZWJ 시퀀스 이모지는 올바르게 처리하지 못합니다.
#  DEFAULT_TOPICS는 모두 단일 코드포인트 이모지라 현재 정상 동작.
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
    """
    단일 인스턴스 보호를 위한 파일 락 획득.
    "a+" 모드로 통일하여 exists() 체크 없이 레이스 컨디션 방지.
    """
    global _lock_fd
    lock_path = BASE / ".instance.lock"
    try:
        _lock_fd = open(lock_path, "a+")
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
