#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""게시판 검색기 — 실시간 웹 검색 + 리포트 포맷 엔진
DuckDuckGo 기반 실시간 검색 → 토픽별 핫키워드 리포트 생성
"""
from __future__ import annotations

import re
import time
import random
from urllib.parse import urlparse
from datetime import datetime

from common import (
    SITES_CONFIG, MD_FILE,
    DEFAULT_TOPICS, DEFAULT_KEYWORD_COUNT, DEFAULT_HOURS,
    load_json, log, strip_leading_emoji,
)

_HAS_DDGS = True
try:
    from duckduckgo_search import DDGS
except ImportError:
    _HAS_DDGS = False

LINE_WIDTH = 24
SUMMARY_WIDTH = 32

EMPTY_CAT_FALLBACK = {
    "🪙 코인": [
        ("비트코인·이더리움 시세", "주요 거래소·뉴스에서 시세·ETF 흐름 공통 보도"),
        ("가상자산 규제·세제", "SEC·금융위·국회 논의"),
    ],
    "🏥 건강": [
        ("AI 의료·건강검진", "디지털헬스·검진 혁신"),
        ("식품안전·영양", "식약처·유통이슈"),
    ],
}


# ═══════════════════════════════════════════════════
#  사이트 config 접근
# ═══════════════════════════════════════════════════
def _load_sites_config() -> dict:
    return load_json(SITES_CONFIG)


def _extract_domain(url: str) -> str | None:
    if not url or url in ("앱", "app"):
        return None
    u = url if url.startswith("http") else "https://" + url
    try:
        netloc = urlparse(u).netloc or u.split("/")[0]
        return netloc.replace("www.", "") if netloc else None
    except Exception:
        return None


# ═══════════════════════════════════════════════════
#  사이트·게시판 집계
# ═══════════════════════════════════════════════════
def get_site_board_counts() -> tuple[int, int]:
    cfg = _load_sites_config()
    if not cfg:
        return 0, 0
    domains: set[str] = set()
    total = 0
    for sites in cfg.get("categories", {}).values():
        if not isinstance(sites, list):
            continue
        for s in sites:
            d = _extract_domain(s.get("url", ""))
            if d:
                domains.add(d)
            total += 1
    return len(domains), total


def get_per_topic_counts(topic_names: list | None = None) -> dict:
    cfg = _load_sites_config()
    if not cfg:
        return {}
    categories = cfg.get("categories", {})
    targets = topic_names if topic_names else list(DEFAULT_TOPICS)
    result = {}
    for topic in targets:
        key = strip_leading_emoji(topic) or topic
        domains: set[str] = set()
        total = 0
        for cname, sites in categories.items():
            if not isinstance(sites, list):
                continue
            if key in cname or cname in key:
                for s in sites:
                    d = _extract_domain(s.get("url", ""))
                    if d:
                        domains.add(d)
                    total += 1
        result[topic] = (len(domains), total)
    return result


def count_unique_domains(rs_list: list) -> tuple[int, int]:
    doms: set[str] = set()
    boards = 0
    for cat in rs_list:
        for s in cat.get("sites") or []:
            boards += 1
            d = _extract_domain(s.get("url", ""))
            if d:
                doms.add(d)
    return len(doms), boards


def check_sample_urls(sample_size: int = 20, timeout: int = 3) -> int:
    cfg = _load_sites_config()
    if not cfg:
        return -1
    urls = []
    for sites in cfg.get("categories", {}).values():
        if not isinstance(sites, list):
            continue
        for s in sites:
            u = s.get("url", "")
            if u and u.startswith("http"):
                urls.append(u)
    if not urls:
        return -1
    sample = random.sample(urls, min(sample_size, len(urls)))
    try:
        import urllib.request
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _chk(url):
            try:
                req = urllib.request.Request(
                    url, method="HEAD",
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                urllib.request.urlopen(req, timeout=timeout)
                return True
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=10) as pool:
            futs = [pool.submit(_chk, u) for u in sample]
            ok = sum(1 for f in as_completed(futs) if f.result())
        return round(ok / len(sample) * 100)
    except Exception as e:
        log.warning("URL check failed: %s", e)
        return -1


# ═══════════════════════════════════════════════════
#  시간 → DuckDuckGo timelimit 변환
# ═══════════════════════════════════════════════════
def _hours_to_timelimit(hours: int) -> str:
    if hours <= 24:
        return "d"
    if hours <= 168:
        return "w"
    return "m"


def _timelimit_label(tl: str) -> str:
    return {"d": "24시간", "w": "1주일", "m": "1개월"}.get(tl, tl)


# ═══════════════════════════════════════════════════
#  실시간 웹 검색 — DuckDuckGo text + news
# ═══════════════════════════════════════════════════
def search_topics_online(
    topic_config: dict[str, int],
    hours: int = 36,
    progress_callback=None,
    stop_event=None,
) -> dict:
    """각 토픽에 대해 DuckDuckGo 실시간 검색을 수행하여 핫키워드를 수집한다."""
    if not _HAS_DDGS:
        log.error("duckduckgo_search 미설치 — pip install duckduckgo-search")
        return {"카테고리": {}}

    timelimit = _hours_to_timelimit(hours)
    total = len(topic_config)
    categories: dict[str, list] = {}

    for idx, (topic_name, kw_count) in enumerate(topic_config.items()):
        if stop_event and stop_event.is_set():
            break

        clean_name = strip_leading_emoji(topic_name) or topic_name
        target = max(kw_count * 3, 10)

        if progress_callback:
            progress_callback(idx, total, clean_name, "웹 검색 중...")

        seen: set[str] = set()
        items: list[dict] = []

        queries = [
            f"{clean_name} 커뮤니티 핫이슈 인기",
            f"{clean_name} 게시판 실시간 화제",
            f"{clean_name} 최신 이슈 논란",
        ]

        for q in queries:
            if len(items) >= target:
                break
            try:
                for r in DDGS(timeout=20).text(
                    q, max_results=target, timelimit=timelimit,
                ):
                    title = (r.get("title") or "").strip()
                    body = (r.get("body") or "").strip()
                    href = (r.get("href") or "").strip()
                    if not title or title.lower() in seen:
                        continue
                    seen.add(title.lower())
                    items.append({
                        "제목": title[:80],
                        "의견요약": body[:300] if body else "",
                        "참고url": href,
                        "참고라벨": "",
                    })
            except Exception as e:
                log.warning("텍스트 검색 실패 '%s': %s", q, e)

        if progress_callback:
            progress_callback(idx, total, clean_name, "뉴스 검색 중...")

        try:
            for r in DDGS(timeout=20).news(
                clean_name, max_results=target, timelimit=timelimit,
            ):
                title = (r.get("title") or "").strip()
                body = (r.get("body") or "").strip()
                url = (r.get("url") or "").strip()
                if not title or title.lower() in seen:
                    continue
                seen.add(title.lower())
                items.append({
                    "제목": title[:80],
                    "의견요약": body[:300] if body else "",
                    "참고url": url,
                    "참고라벨": r.get("source", ""),
                })
        except Exception as e:
            log.warning("뉴스 검색 실패 '%s': %s", clean_name, e)

        categories[topic_name] = items
        log.info("토픽 '%s': %d건 수집 (목표 %d)", clean_name, len(items), kw_count)

        if idx < total - 1:
            time.sleep(0.5)

    if progress_callback:
        progress_callback(total, total, "완료", "검색 완료")

    return {
        "수집시각": datetime.now().strftime("%Y년 %m월 %d일 %H:%M"),
        "기준": f"현재 시점 대비 {_timelimit_label(timelimit)} 이내",
        "검색어": [],
        "카테고리": categories,
        "베스트": [],
    }


# ═══════════════════════════════════════════════════
#  카테고리 매칭 (퍼지 — 커스텀 토픽도 매칭 가능)
# ═══════════════════════════════════════════════════
def _find_matching_category(name: str, categories: dict) -> list:
    if name in categories:
        return categories[name]
    key = strip_leading_emoji(name).lower()
    if not key:
        return []
    for k, v in categories.items():
        k_stripped = strip_leading_emoji(k).lower()
        if key in k_stripped or k_stripped in key:
            return v
    return []


# ═══════════════════════════════════════════════════
#  한국어 친화 줄바꿈
# ═══════════════════════════════════════════════════
_BREAKABLE = frozenset(" .,·:;!?。、…→−~")


def _wrap(text: str, indent: str = "", width: int = LINE_WIDTH) -> list:
    if not text:
        return []
    result = []
    while text:
        if len(text) <= width:
            result.append(indent + text)
            break
        best = -1
        limit = min(width, len(text))
        for i in range(limit, 0, -1):
            if text[i - 1] in _BREAKABLE:
                best = i
                break
        cut = best if best > width // 3 else limit
        result.append(indent + text[:cut].strip())
        text = text[cut:].strip()
    return result


# ═══════════════════════════════════════════════════
#  메신저용 리포트 포맷
# ═══════════════════════════════════════════════════
def format_for_messenger(
    data: dict, settings: dict | None = None,
) -> tuple[str, int]:
    lines: list[str] = []
    now = datetime.now()
    date_str = now.strftime("%Y년 %m월 %d일")
    site_count, board_count = get_site_board_counts()
    hours = settings.get("hours", DEFAULT_HOURS) if settings else DEFAULT_HOURS

    topic_config: dict[str, int] = {}
    if settings:
        all_t = settings.get("topics", []) + settings.get("custom_topics", [])
        by_name = {}
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
    else:
        for name in DEFAULT_TOPICS:
            topic_config[name] = DEFAULT_KEYWORD_COUNT

    n_topics = len(topic_config)
    lines.append("")
    lines.append("✦ 게시판 검색기")
    lines.append(f"  {date_str} · {now.strftime('%H:%M')} 기준")
    lines.append("")
    lines.append(f"※ {n_topics}개 토픽 · {hours}시간 기준 · 실시간 웹 검색")
    lines.append(f"  {site_count:,}개 사이트 · {board_count:,}개 게시판 DB 기반")
    lines.append("")
    lines.append("━" * LINE_WIDTH)
    lines.append("✨ 토픽별 핫키워드 (토픽당 설정 개수만큼)")
    lines.append("━" * LINE_WIDTH)

    categories = data.get("카테고리", {})
    for cat_name, kw_count in topic_config.items():
        topics = _find_matching_category(cat_name, categories)
        lines.append("")
        lines.append(f"• {cat_name}")
        if not topics:
            fallback = EMPTY_CAT_FALLBACK.get(cat_name, [])
            if fallback:
                lines.append("  (최근 실시간 데이터 없음 — 참고 정보)")
                for title, desc in fallback[:kw_count]:
                    lines.append(f"  · {title}")
                    for ln in _wrap(desc, width=SUMMARY_WIDTH):
                        lines.append(f"    {ln}")
                    lines.append("")
            else:
                lines.append("  · 해당 기간 회자 핫키워드 없음")
            continue
        for t in topics[:kw_count]:
            lines.append(f"  · {t['제목']}")
            for ln in _wrap(t["의견요약"], width=SUMMARY_WIDTH):
                lines.append(f"    {ln}")
            lines.append("")

    lines.append("")
    lines.append("━" * LINE_WIDTH)
    lines.append("ⓒ 챠리 · 오픈 프로젝트")
    lines.append("  누구나 자유롭게 사용할 수 있습니다.")
    lines.append(f"  ※ {hours}시간 후 갱신을 추천합니다.")
    lines.append("━" * LINE_WIDTH)

    shown = sum(
        1 for ln in lines
        if ln.strip().startswith("·") and "해당 기간" not in ln
    )
    return "\n".join(lines), shown
