#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""게시판 검색기 — 설정 관리 모듈 (상용 v0.9)
원자적 쓰기 + .bak 백업 + 스레드 안전 + 중복 토픽 방지
"""
from __future__ import annotations

import json
import threading
from common import (
    SETTINGS_FILE, SITES_CONFIG,
    DEFAULT_TOPICS, DEFAULT_KEYWORD_COUNT, DEFAULT_HOURS,
    atomic_write, load_json, log, strip_leading_emoji,
)

_file_lock = threading.Lock()


# ═══════════════════════════════════════════════════
#  기본 설정
# ═══════════════════════════════════════════════════
def get_default_settings() -> dict:
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
    }


# ═══════════════════════════════════════════════════
#  정규화
# ═══════════════════════════════════════════════════
def _normalize_topic(t: dict) -> dict | None:
    if not isinstance(t, dict) or not t.get("name"):
        return None
    try:
        entry: dict = {
            "name": str(t["name"]),
            "enabled": bool(t.get("enabled", True)),
            "keyword_count": max(1, min(10, int(t.get("keyword_count", DEFAULT_KEYWORD_COUNT)))),
        }
        rs = t.get("related_sites")
        if isinstance(rs, list):
            entry["related_sites"] = rs
        return entry
    except (TypeError, ValueError):
        return None


def _normalize_settings(data: dict) -> dict:
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
    }


# ═══════════════════════════════════════════════════
#  로드 / 저장
# ═══════════════════════════════════════════════════
def load_settings() -> dict:
    base = get_default_settings()
    if not SETTINGS_FILE.exists():
        return base
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        norm = _normalize_settings(data)
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
    try:
        norm = _normalize_settings(settings)
        content = json.dumps(norm, ensure_ascii=False, indent=2)
        with _file_lock:
            atomic_write(SETTINGS_FILE, content)
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
#  웹 검색으로 관련 사이트 탐색 (DuckDuckGo + timeout)
# ═══════════════════════════════════════════════════
def find_related_sites_via_web_search(
    topic_name: str, max_results: int = 100,
) -> list:
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
            if len(sites) >= max_results:
                break
            try:
                for r in DDGS(timeout=15).text(q, max_results=30):
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
                            if len(sites) >= max_results:
                                break
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
