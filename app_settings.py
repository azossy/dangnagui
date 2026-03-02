#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
게시판 검색기 — 설정 관리 모듈 (app_settings.py)
═══════════════════════════════════════════════════
원자적 쓰기 + .bak 백업 + 스레드 안전 + 중복 토픽 방지

■ v1.3.0 주요 변경사항:
  1. 암호화 파일 DB (db_crypto) 연동
  2. 3계층 사이트 탐색 통합 갱신 로직 (site_discovery)
  3. 사이트 갱신 시 암호화 DB 자동 저장
  4. 시드 DB → 암호화 DB 마이그레이션

copyright by 챠리 (challychoi@me.com)
"""
from __future__ import annotations

import json
import threading
from common import (
    SETTINGS_FILE, SITES_CONFIG,
    DEFAULT_TOPICS, DEFAULT_KEYWORD_COUNT, DEFAULT_HOURS,
    DEFAULT_REPORT_HEADER,
    atomic_write, load_json, log, strip_leading_emoji,
)

# ═══════════════════════════════════════════════════
#  암호화 DB 모듈 로딩 (v1.3.0)
# ═══════════════════════════════════════════════════
_HAS_DB_CRYPTO = True
try:
    from db_crypto import (
        load_encrypted_db, save_encrypted_db,
        SITES_SEED_FILE, get_db_summary,
    )
except ImportError:
    _HAS_DB_CRYPTO = False

# ═══════════════════════════════════════════════════
#  사이트 탐색 모듈 로딩 (v1.3.0)
# ═══════════════════════════════════════════════════
_HAS_DISCOVERY = True
try:
    from site_discovery import run_full_discovery, get_all_domains_from_db
except ImportError:
    _HAS_DISCOVERY = False

_file_lock = threading.Lock()


# ═══════════════════════════════════════════════════
#  기본 설정
# ═══════════════════════════════════════════════════
def get_default_settings() -> dict:
    """애플리케이션 기본 설정값을 반환합니다."""
    return {
        "topics": [
            {"name": n, "enabled": True, "keyword_count": DEFAULT_KEYWORD_COUNT}
            for n in DEFAULT_TOPICS
        ],
        "custom_topics": [],
        "hours": DEFAULT_HOURS,
        "topic_order": [],
        "last_track_date": "",
        "valid_rate": -1,
        "report_header": DEFAULT_REPORT_HEADER,
    }


# ═══════════════════════════════════════════════════
#  정규화 (입력 데이터 검증 및 안전한 형태로 변환)
# ═══════════════════════════════════════════════════
def _normalize_topic(t: dict) -> dict | None:
    """토픽 딕셔너리를 정규화합니다. 유효하지 않으면 None 반환."""
    if not isinstance(t, dict) or not t.get("name"):
        return None
    try:
        entry: dict = {
            "name": str(t["name"]),
            "enabled": bool(t.get("enabled", True)),
            "keyword_count": max(1, min(10, int(t.get("keyword_count", DEFAULT_KEYWORD_COUNT)))),
        }
        # related_sites는 레거시 호환용으로 유지
        rs = t.get("related_sites")
        if isinstance(rs, list):
            entry["related_sites"] = rs
        return entry
    except (TypeError, ValueError):
        return None


def _normalize_settings(data: dict) -> dict:
    """설정 딕셔너리 전체를 정규화합니다."""
    topics = [e for t in data.get("topics", []) if (e := _normalize_topic(t))]
    custom = [e for t in data.get("custom_topics", []) if (e := _normalize_topic(t))]
    try:
        hours = max(30, min(100, int(data.get("hours", DEFAULT_HOURS))))
    except (TypeError, ValueError):
        hours = DEFAULT_HOURS
    try:
        vr = int(data.get("valid_rate", -1))
    except (TypeError, ValueError):
        vr = -1
    return {
        "topics": topics,
        "custom_topics": custom,
        "hours": hours,
        "topic_order": list(data.get("topic_order") or []),
        "last_track_date": str(data.get("last_track_date") or ""),
        "valid_rate": vr,
        "report_header": str(data.get("report_header") or DEFAULT_REPORT_HEADER),
    }


# ═══════════════════════════════════════════════════
#  설정 로드 / 저장
# ═══════════════════════════════════════════════════
def load_settings() -> dict:
    """
    앱 설정을 로드합니다.
    파일이 없으면 기본 설정을 반환합니다.
    """
    base = get_default_settings()
    if not SETTINGS_FILE.exists():
        return base
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        norm = _normalize_settings(data)
        # 기본 토픽 중 누락된 것 보충
        if not norm["topics"] and not norm["custom_topics"]:
            norm["topics"] = list(base["topics"])
        else:
            all_names = (
                {t["name"] for t in norm["topics"]}
                | {t["name"] for t in norm["custom_topics"]}
            )
            for dt in base["topics"]:
                if dt["name"] not in all_names:
                    norm["topics"].append(dt)
        return norm
    except Exception as e:
        log.error("Settings load failed: %s", e)
        return base


def save_settings(settings: dict) -> bool:
    """
    앱 설정을 원자적으로 저장합니다.
    동시 접근 보호를 위해 파일 락을 사용합니다.
    """
    try:
        norm = _normalize_settings(settings)
        content = json.dumps(norm, ensure_ascii=False, indent=2)
        with _file_lock:
            atomic_write(SETTINGS_FILE, content)
            # 레거시 sites_config.json 동기화 (있으면)
            if SITES_CONFIG.exists():
                try:
                    cfg = json.loads(SITES_CONFIG.read_text(encoding="utf-8"))
                    if cfg.get("validity_hours") != norm["hours"]:
                        cfg["validity_hours"] = norm["hours"]
                        atomic_write(
                            SITES_CONFIG,
                            json.dumps(cfg, ensure_ascii=False, indent=2),
                        )
                except Exception as e:
                    log.warning("sites_config hours update failed: %s", e)
        return True
    except Exception as e:
        log.error("Settings save failed: %s", e)
        return False


# ═══════════════════════════════════════════════════
#  ◆ v1.3.0: 3계층 통합 사이트 갱신 ◆
#  Layer 1(시드DB) → Layer 2(API/파싱) → Layer 3(DDG)
#  결과를 암호화 파일 DB에 저장
# ═══════════════════════════════════════════════════
def run_site_discovery(
    settings: dict,
    progress_callback=None,
    stop_event=None,
) -> dict:
    """
    3계층 사이트 자동 탐색을 실행하고 결과를 암호화 DB에 저장합니다.

    ■ 실행 순서:
      1. 시드 DB 또는 기존 암호화 DB를 기본 데이터로 사용
      2. site_discovery.run_full_discovery()로 3계층 탐색 실행
      3. 결과를 암호화 파일 DB에 저장
      4. 설정에 갱신 일시 기록

    Args:
        settings: 현재 앱 설정
        progress_callback: 진행률 콜백 (current, total, message)
        stop_event: 중단 이벤트

    Returns:
        dict: 탐색 결과 요약 {"total_sites": int, "total_boards": int, ...}
    """
    if not _HAS_DISCOVERY:
        log.error("site_discovery 모듈을 로드할 수 없습니다")
        return {"error": "site_discovery 모듈 미발견"}

    # ── Step 1: 기존 DB 로드 (시드DB 포함) ──
    if _HAS_DB_CRYPTO:
        seed_data = load_encrypted_db()
    else:
        seed_data = {}

    # 시드 데이터가 비어있으면 시드 파일 직접 로드
    if not seed_data.get("sites"):
        if _HAS_DB_CRYPTO and SITES_SEED_FILE.exists():
            try:
                seed_data = json.loads(SITES_SEED_FILE.read_text(encoding="utf-8"))
                log.info("시드 DB에서 초기 데이터 로드")
            except Exception as e:
                log.error("시드 DB 로드 실패: %s", e)
                seed_data = {"sites": [], "topic_site_mapping": {}, "news_sites": []}

    # ── Step 2: 토픽 목록 수집 ──
    all_topics = settings.get("topics", []) + settings.get("custom_topics", [])
    topic_names = [
        strip_leading_emoji(t["name"]) or t["name"]
        for t in all_topics
        if t.get("name")
    ]

    # ── Step 3: 3계층 탐색 실행 ──
    result_db = run_full_discovery(
        seed_data=seed_data,
        topic_names=topic_names,
        progress_callback=progress_callback,
        stop_event=stop_event,
    )

    # ── Step 4: 암호화 DB에 저장 ──
    if _HAS_DB_CRYPTO:
        ok = save_encrypted_db(result_db)
        if ok:
            log.info("암호화 DB 저장 완료")
        else:
            log.error("암호화 DB 저장 실패")

    # ── Step 5: 결과 요약 반환 ──
    meta = result_db.get("meta", {})
    return {
        "total_sites": meta.get("total_sites", 0),
        "total_boards": meta.get("total_boards", 0),
        "dc_gallery_count": meta.get("dc_gallery_count", 0),
        "naver_cafe_count": meta.get("naver_cafe_count", 0),
        "discovered_count": meta.get("discovered_count", 0),
    }


# ═══════════════════════════════════════════════════
#  웹 검색으로 관련 사이트 탐색 (DuckDuckGo + timeout)
#  레거시 호환 + 단일 토픽 탐색용
# ═══════════════════════════════════════════════════
def find_related_sites_via_web_search(topic_name: str) -> list:
    """
    DuckDuckGo로 단일 토픽의 관련 사이트를 검색합니다.
    (레거시 호환, 개별 토픽 추가 시 사용)
    """
    key = (topic_name or "").strip()
    if not key:
        return []
    seen: set[str] = set()
    sites: list[dict] = []
    try:
        from urllib.parse import urlparse
        from duckduckgo_search import DDGS

        queries = [
            f"{key} 커뮤니티 사이트", f"{key} 게시판", f"{key} 포럼",
            f"{key} 카페", f"{key} 블로그",
        ]
        for q in queries:
            try:
                for r in DDGS(timeout=15).text(q, max_results=200):
                    href = (r.get("href") or r.get("url") or "").strip()
                    title = (r.get("title") or "").strip() or href
                    if not href or "javascript:" in href:
                        continue
                    if not href.startswith("http"):
                        href = "https://" + href
                    try:
                        p = urlparse(href)
                        norm = f"{p.netloc or ''}{p.path or ''}".rstrip("/")
                        if norm and norm not in seen:
                            seen.add(norm)
                            sites.append({"name": title[:80], "url": href})
                    except Exception:
                        pass
            except Exception as e:
                log.warning("Web search query failed '%s': %s", q, e)
                continue
    except ImportError:
        log.info("duckduckgo_search not installed")
    except Exception as e:
        log.error("Web search error: %s", e)
    return [{"category": "웹검색 결과", "sites": sites}] if sites else []


def find_related_sites_for_topic(topic_name: str) -> list:
    """레거시 sites_config.json에서 토픽 관련 사이트를 찾습니다."""
    cfg = load_json(SITES_CONFIG)
    if not cfg:
        return []
    key = (topic_name or "").strip()
    if not key:
        return []
    kl = key.lower()
    result = []
    for cname, sites in cfg.get("categories", {}).items():
        if not isinstance(sites, list):
            continue
        if key in cname or kl in cname.lower():
            result.append({
                "category": cname,
                "sites": [
                    {"name": s.get("name", ""), "url": s.get("url", "")}
                    for s in sites if isinstance(s, dict)
                ],
            })
        else:
            matched = [
                {"name": s.get("name", ""), "url": s.get("url", "")}
                for s in sites
                if isinstance(s, dict)
                and (key in (s.get("name") or "") or kl in (s.get("name") or "").lower())
            ]
            if matched:
                result.append({"category": cname, "sites": matched})
    return result


def get_related_sites_for_default_topic(display_name: str) -> list:
    """기본 토픽에 대한 관련 사이트를 레거시 config에서 찾습니다."""
    cfg = load_json(SITES_CONFIG)
    if not cfg:
        return []
    s = (display_name or "").strip()
    if not s:
        return []
    cat_key = strip_leading_emoji(s) or s
    for cname, sites in cfg.get("categories", {}).items():
        if cname == cat_key or cat_key in cname:
            if isinstance(sites, list):
                return [{
                    "category": cname,
                    "sites": [
                        {"name": x.get("name", ""), "url": x.get("url", "")}
                        for x in sites if isinstance(x, dict)
                    ],
                }]
    return []
