#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""게시판 검색기 — 리포트 파싱·포맷·사이트 집계 (상용 v0.9)
동적 카테고리 파싱 + 커스텀 토픽 지원 + 정확한 도메인 카운팅
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
#  진행률 — ~40회 UI 갱신, 총 0.4초 지연 (UX 시각 피드백)
# ═══════════════════════════════════════════════════
def iter_sites_progress(progress_callback=None, stop_event=None):
    if not progress_callback:
        return
    cfg = _load_sites_config()
    if not cfg:
        return
    items: list[tuple[str, str, str]] = []
    for cat_name, sites in cfg.get("categories", {}).items():
        if not isinstance(sites, list):
            continue
        for s in sites:
            items.append((cat_name, s.get("name", ""), s.get("url", "")))
    if not items:
        return
    total = len(items)
    domains: set[str] = set()
    step = max(1, total // 40)
    for idx, (cat_name, site_name, url) in enumerate(items):
        if stop_event and stop_event.is_set():
            return
        d = _extract_domain(url)
        if d:
            domains.add(d)
        if idx % step == 0 or idx == total - 1:
            progress_callback(
                len(domains), idx + 1, len(domains), total,
                cat_name, site_name,
            )
            if idx < total - 1:
                time.sleep(0.01)


# ═══════════════════════════════════════════════════
#  마크다운 파싱 — 동적 카테고리 (커스텀 토픽 자동 지원)
# ═══════════════════════════════════════════════════
def parse_markdown(content: str) -> dict:
    data: dict = {
        "수집시각": "", "기준": "",
        "검색어": [], "카테고리": {}, "베스트": [],
    }
    m = re.search(r'\*\*수집 시각:\*\*\s*(.+?)(?:\n|$)', content)
    if m:
        data["수집시각"] = m.group(1).strip()
    m = re.search(r'\*\*기준:\*\*\s*(.+?)(?:\n|$)', content)
    if m:
        data["기준"] = m.group(1).strip()

    search_rows = re.findall(
        r'\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|', content,
    )
    data["검색어"] = [
        (r[0], r[1].strip(), r[2].strip())
        for r in search_rows
        if r[0].isdigit() and int(r[0]) <= 20
    ][:10]

    sections = re.split(r'\n(?=## )', content)
    skip_keywords = ("베스트", "급상승", "검색어", "📊")
    for sec in sections:
        m_head = re.match(r'## (.+?)(?:\n|$)', sec)
        if not m_head:
            continue
        heading = m_head.group(1).strip()
        if any(kw in heading for kw in skip_keywords):
            continue
        if "주요 회자된 주제 없음" in sec:
            data["카테고리"][heading] = []
            continue
        topics = []
        blocks = re.findall(
            r'###\s*\d+\.\s*([^\n]+)\s*\n'
            r'\*\*회자 배경:\*\*[^\n]*\n+'
            r'\*\*의견 요약:\*\*\s*([^\n]+)'
            r'(?:\s*\n+\*\*내용 이해용 참고\*\*\s*\n((?:-\s*[^\n]*\n?)*))?',
            sec,
        )
        for block in blocks:
            title, summary = block[0].strip(), block[1].strip()
            ref_block = block[2] if len(block) > 2 else ""
            refs = re.findall(r'-\s*\[([^\]]+)\]\s*([^\n]+)', ref_block or "")
            urls = []
            for label, ref_str in refs:
                ref_str = (
                    ref_str.strip().split("(")[0].strip()
                    if "(" in ref_str
                    else ref_str.strip()
                )
                if ref_str.startswith("http") or any(
                    x in ref_str for x in (".com", ".co.kr", ".kr", ".net")
                ):
                    if not ref_str.startswith("http"):
                        ref_str = "https://" + ref_str
                    urls.append((label, ref_str))
            topics.append({
                "제목": title,
                "의견요약": summary,
                "참고url": urls[0][1] if urls else "",
                "참고라벨": urls[0][0] if urls else "",
            })
        if topics:
            data["카테고리"][heading] = topics

    best_section = re.search(
        r'## 📋 커뮤니티별 베스트[\s\S]*?\n\|[-\s|]+\|\n([\s\S]*?)(?=\n---|\n## |\Z)',
        content,
    )
    if best_section:
        rows = re.findall(
            r'\|\s*\*\*([^*]+)\*\*\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|',
            best_section.group(1),
        )
        data["베스트"] = [
            (r[0].strip(), r[1].strip(), r[2].strip()) for r in rows
        ]
    return data


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

    lines.append("")
    lines.append("✦ 게시판 검색기")
    lines.append(f"  {date_str} · {now.strftime('%H:%M')} 기준")
    lines.append("")
    lines.append(f"※ {site_count:,}개 사이트 · {board_count:,}개 게시판")
    lines.append(f"  설정된 토픽 기준 · {hours}시간 회자 · 핫키워드 중요도 순")
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
