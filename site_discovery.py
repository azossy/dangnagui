#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
게시판 검색기 — 3계층 사이트 자동 탐색 모듈 (site_discovery.py)
═══════════════════════════════════════════════════════════════════
국내 1,000+ 사이트 / 60,000+ 게시판을 자동으로 수집·확장합니다.

■ Layer 1: 내장 시드 DB (korean_sites_seed.json)
  → 즉시 로드, 네트워크 불필요
  → 200+ 큐레이션 사이트 + 80+ 뉴스 사이트

■ Layer 2: API/파싱 자동 탐색
  → 디시인사이드 JSON API (52,000+ 갤러리 일괄 수집)
  → 사이트별 게시판 목록 HTML 파싱 (BeautifulSoup4)

■ Layer 3: DuckDuckGo 동적 확장
  → 토픽별 새로운 사이트/게시판 발견
  → 네이버 카페 토픽별 검색

■ 라이선스:
  - requests (Apache 2.0), beautifulsoup4 (MIT), duckduckgo-search (MIT)
  - 어떤 GPL 코드도 사용하지 않음

copyright by 챠리 (challychoi@me.com)
"""
from __future__ import annotations

import time
import json
import re
from typing import Callable, Optional
from urllib.parse import urlparse

from common import log

# ═══════════════════════════════════════════════════
#  선택적 의존성 로딩
#  설치되지 않은 라이브러리가 있어도 부분 동작 가능
# ═══════════════════════════════════════════════════
_HAS_REQUESTS = True
try:
    import requests
except ImportError:
    _HAS_REQUESTS = False
    log.info("requests 미설치 — Layer 2 사이트 파싱 비활성")

_HAS_BS4 = True
try:
    from bs4 import BeautifulSoup
except ImportError:
    _HAS_BS4 = False
    log.info("beautifulsoup4 미설치 — HTML 파싱 비활성")

_HAS_DDGS = True
try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        _HAS_DDGS = False
        log.info("ddgs 미설치 — Layer 3 DDG 탐색 비활성")

# ═══════════════════════════════════════════════════
#  공통 상수
# ═══════════════════════════════════════════════════
# HTTP 요청 시 사용할 User-Agent (봇 차단 방지)
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# HTTP 요청 타임아웃 (초)
_TIMEOUT = 15

# DuckDuckGo 연속 요청 간 대기 시간 (초, rate limit 방지)
_DDG_DELAY = 0.8

# 진행 콜백 타입: (현재단계, 전체단계, 메시지)
ProgressCallback = Callable[[int, int, str], None]


# ═══════════════════════════════════════════════════
#  Layer 2-A: 디시인사이드 갤러리 일괄 수집
#  공개 JSON API 1회 호출로 52,000+ 갤러리 목록 획득
# ═══════════════════════════════════════════════════
def discover_dc_galleries(timeout: int = _TIMEOUT) -> list[dict]:
    """
    디시인사이드의 전체 마이너/미니 갤러리 목록을 JSON API로 가져옵니다.

    ■ 사용 API:
      https://json2.dcinside.com/json1/mgallmain/mgallery_new.php

    ■ 반환 형식 (각 갤러리):
      {"id": "gallery_id", "name": "갤러리명", "type": "minor"}

    ■ 이 API 하나로 약 52,000개 갤러리를 확보할 수 있어
      마케팅 문구 "국내 50,000+ 게시판 분석" 의 핵심 근거가 됩니다.

    Args:
        timeout: HTTP 요청 타임아웃 (초)

    Returns:
        list[dict]: 갤러리 목록 (id, name, type 포함)
    """
    if not _HAS_REQUESTS:
        log.warning("requests 미설치 — DC갤러리 수집 건너뜀")
        return []

    galleries: list[dict] = []

    # ── 마이너 갤러리 API ──
    # 디시인사이드가 공개하는 마이너 갤러리 전체 목록 JSON
    minor_url = "https://json2.dcinside.com/json1/mgallmain/mgallery_new.php"
    try:
        resp = requests.get(
            minor_url,
            headers={"User-Agent": _UA, "Referer": "https://www.dcinside.com"},
            timeout=timeout,
        )
        resp.raise_for_status()

        # API 응답이 JSON 배열 형태
        data = resp.json()
        if isinstance(data, list):
            for item in data:
                gall_id = item.get("id") or item.get("gallery_id") or ""
                gall_name = item.get("ko_name") or item.get("name") or ""
                if gall_id and gall_name:
                    galleries.append({
                        "id": str(gall_id),
                        "name": str(gall_name),
                        "type": "minor",
                    })

        log.info("DC 마이너갤러리 %d개 수집 완료", len(galleries))

    except requests.exceptions.Timeout:
        log.warning("DC API 타임아웃 (%ds)", timeout)
    except requests.exceptions.RequestException as e:
        log.warning("DC API 요청 실패: %s", e)
    except (json.JSONDecodeError, ValueError) as e:
        log.warning("DC API 응답 파싱 실패: %s", e)
    except Exception as e:
        log.error("DC 갤러리 수집 예외: %s", e)

    return galleries


# ═══════════════════════════════════════════════════
#  Layer 2-B: 사이트별 게시판 HTML 파싱
#  BeautifulSoup4로 주요 사이트의 게시판 목록을 추출
# ═══════════════════════════════════════════════════
# 사이트별 게시판 파싱 설정
# 각 사이트마다 게시판 링크를 추출하는 CSS 셀렉터와 URL 패턴을 정의
_SITE_PARSERS = {
    "clien.net": {
        "url": "https://www.clien.net/service",
        "selector": "a.board-nav-link",
        "name_attr": "text",
        "path_attr": "href",
        "filter_pattern": r"/service/board/",
    },
    "ruliweb.com": {
        "url": "https://bbs.ruliweb.com",
        "selector": ".board-menu a",
        "name_attr": "text",
        "path_attr": "href",
        "filter_pattern": r"/community/board/|/best/",
    },
    "ppomppu.co.kr": {
        "url": "https://www.ppomppu.co.kr",
        "selector": "#header_left_menu a",
        "name_attr": "text",
        "path_attr": "href",
        "filter_pattern": r"zboard\.php\?id=",
    },
    "quasarzone.com": {
        "url": "https://quasarzone.com",
        "selector": ".nav-link",
        "name_attr": "text",
        "path_attr": "href",
        "filter_pattern": r"/bbs/",
    },
}


def discover_site_boards(
    domain: str,
    timeout: int = _TIMEOUT,
) -> list[dict]:
    """
    특정 사이트의 게시판 목록을 HTML 파싱으로 추출합니다.

    ■ 동작 원리:
      1. 사이트 메인 페이지 HTTP GET
      2. BeautifulSoup으로 HTML 파싱
      3. 사전 정의된 CSS 셀렉터로 게시판 링크 추출
      4. URL 패턴 필터로 게시판 링크만 선별

    ■ 파서가 정의되지 않은 사이트는 빈 리스트 반환 (에러 아님)

    Args:
        domain: 사이트 도메인 (예: "clien.net")
        timeout: HTTP 요청 타임아웃

    Returns:
        list[dict]: [{"id": "...", "name": "...", "path": "..."}]
    """
    if not _HAS_REQUESTS or not _HAS_BS4:
        return []

    # 이 도메인에 대한 파서 설정이 있는지 확인
    parser_config = _SITE_PARSERS.get(domain)
    if not parser_config:
        return []

    boards: list[dict] = []
    seen_paths: set[str] = set()

    try:
        resp = requests.get(
            parser_config["url"],
            headers={"User-Agent": _UA},
            timeout=timeout,
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.select(parser_config["selector"])

        pattern = re.compile(parser_config.get("filter_pattern", ""))

        for link in links:
            # 게시판 이름 추출
            name = link.get_text(strip=True) if parser_config["name_attr"] == "text" else link.get(parser_config["name_attr"], "")
            name = (name or "").strip()

            # 게시판 경로 추출
            path = link.get(parser_config["path_attr"], "")
            path = (path or "").strip()

            # 필터 패턴 매칭 + 중복 제거
            if name and path and pattern.search(path) and path not in seen_paths:
                seen_paths.add(path)
                # 경로에서 게시판 ID 추출 시도
                board_id = _extract_board_id(path) or name[:20]
                boards.append({
                    "id": board_id,
                    "name": name,
                    "path": path,
                })

        log.info("%s 게시판 %d개 파싱 완료", domain, len(boards))

    except requests.exceptions.Timeout:
        log.warning("%s 파싱 타임아웃", domain)
    except requests.exceptions.RequestException as e:
        log.warning("%s HTTP 요청 실패: %s", domain, e)
    except Exception as e:
        log.error("%s 게시판 파싱 예외: %s", domain, e)

    return boards


def _extract_board_id(path: str) -> str:
    """URL 경로에서 게시판 ID를 추출하는 헬퍼"""
    # ?id=xxx 패턴
    m = re.search(r'[?&]id=([^&]+)', path)
    if m:
        return m.group(1)
    # /board/xxx 패턴
    m = re.search(r'/board/([^/?]+)', path)
    if m:
        return m.group(1)
    # /bbs/xxx 패턴
    m = re.search(r'/bbs/([^/?]+)', path)
    if m:
        return m.group(1)
    # 마지막 경로 세그먼트
    parts = [p for p in path.rstrip("/").split("/") if p]
    return parts[-1] if parts else ""


# ═══════════════════════════════════════════════════
#  Layer 3-A: DuckDuckGo로 새 사이트 발견
#  토픽별 검색어로 아직 DB에 없는 사이트를 발굴
# ═══════════════════════════════════════════════════
def discover_via_duckduckgo(
    topic: str,
    known_domains: set[str],
    max_results: int = 50,
) -> list[dict]:
    """
    DuckDuckGo 검색으로 특정 토픽과 관련된 새로운 사이트를 발견합니다.

    ■ 동작 원리:
      1. 토픽 관련 검색어 여러 개로 DuckDuckGo 검색
      2. 검색 결과에서 도메인 추출
      3. 이미 알려진 도메인(known_domains)은 제외
      4. 새로 발견된 사이트만 반환

    ■ Rate Limit 보호:
      - 검색어 사이에 _DDG_DELAY 간격 대기
      - 한 토픽당 최대 max_results개 결과

    Args:
        topic: 검색 토픽명 (예: "IT 하드웨어")
        known_domains: 이미 DB에 있는 도메인 집합
        max_results: 최대 검색 결과 수

    Returns:
        list[dict]: [{"domain": "...", "name": "...", "url": "..."}]
    """
    if not _HAS_DDGS:
        return []

    # 토픽 관련 다양한 검색어 생성
    queries = [
        f"{topic} 커뮤니티 사이트",
        f"{topic} 게시판 추천",
        f"{topic} 포럼 카페",
    ]

    discovered: list[dict] = []
    seen_domains: set[str] = set(known_domains)

    for q in queries:
        if len(discovered) >= max_results:
            break

        try:
            results = DDGS(timeout=20).text(
                q, max_results=30, region="kr-kr",
            )

            for r in results:
                href = (r.get("href") or "").strip()
                title = (r.get("title") or "").strip()
                if not href:
                    continue

                # 도메인 추출 및 정규화
                domain = _normalize_domain(href)
                if not domain or domain in seen_domains:
                    continue

                # 글로벌 사이트 제외 (한국 사이트만)
                if _is_global_site(domain):
                    continue

                seen_domains.add(domain)
                discovered.append({
                    "domain": domain,
                    "name": title[:80] if title else domain,
                    "url": href,
                })

            time.sleep(_DDG_DELAY)

        except Exception as e:
            log.warning("DDG 탐색 실패 '%s': %s", q, e)
            continue

    log.info("토픽 '%s': DDG로 %d개 신규 사이트 발견", topic, len(discovered))
    return discovered


# ═══════════════════════════════════════════════════
#  Layer 3-B: 네이버 카페 토픽별 탐색
#  DuckDuckGo의 site:cafe.naver.com 검색으로 인기 카페 발견
# ═══════════════════════════════════════════════════
def discover_naver_cafes(
    topic: str,
    max_results: int = 30,
) -> list[dict]:
    """
    DuckDuckGo를 통해 토픽별 인기 네이버 카페를 발견합니다.

    ■ 네이버 카페는 전체 목록 API를 제공하지 않으므로
      DuckDuckGo의 site: 검색 기능을 활용하여 간접적으로 탐색합니다.

    ■ 예: "site:cafe.naver.com IT 하드웨어 커뮤니티"

    Args:
        topic: 검색 토픽명
        max_results: 최대 카페 수

    Returns:
        list[dict]: [{"id": "cafe_id", "name": "카페명", "url": "..."}]
    """
    if not _HAS_DDGS:
        return []

    cafes: list[dict] = []
    seen_ids: set[str] = set()

    queries = [
        f"site:cafe.naver.com {topic} 커뮤니티",
        f"site:cafe.naver.com {topic} 카페",
    ]

    for q in queries:
        if len(cafes) >= max_results:
            break

        try:
            results = DDGS(timeout=20).text(q, max_results=20, region="kr-kr")

            for r in results:
                href = (r.get("href") or "").strip()
                title = (r.get("title") or "").strip()

                if "cafe.naver.com" not in href:
                    continue

                # 카페 ID 추출 (URL에서 /카페명 부분)
                cafe_id = _extract_naver_cafe_id(href)
                if not cafe_id or cafe_id in seen_ids:
                    continue

                seen_ids.add(cafe_id)
                cafes.append({
                    "id": cafe_id,
                    "name": title[:80] if title else cafe_id,
                    "url": f"https://cafe.naver.com/{cafe_id}",
                })

            time.sleep(_DDG_DELAY)

        except Exception as e:
            log.warning("네이버 카페 탐색 실패 '%s': %s", q, e)
            continue

    log.info("토픽 '%s': 네이버 카페 %d개 발견", topic, len(cafes))
    return cafes


def _extract_naver_cafe_id(url: str) -> str:
    """네이버 카페 URL에서 카페 ID를 추출"""
    try:
        parsed = urlparse(url)
        # https://cafe.naver.com/카페ID 형태
        if "cafe.naver.com" in parsed.netloc:
            path_parts = [p for p in parsed.path.strip("/").split("/") if p]
            if path_parts:
                return path_parts[0]
    except Exception:
        pass
    return ""


# ═══════════════════════════════════════════════════
#  통합 탐색 실행 (Full Discovery)
#  Layer 1 → 2 → 3 순차 실행, 진행률 콜백 지원
# ═══════════════════════════════════════════════════
def run_full_discovery(
    seed_data: dict,
    topic_names: list[str] | None = None,
    progress_callback: Optional[ProgressCallback] = None,
    stop_event=None,
) -> dict:
    """
    3계층 사이트 탐색을 순차적으로 실행하여 통합 DB를 구축합니다.

    ■ 실행 순서:
      1. 시드 DB를 기본 데이터로 사용 (Layer 1)
      2. DC갤러리 API 호출로 대량 게시판 추가 (Layer 2-A)
      3. 주요 사이트 게시판 HTML 파싱 (Layer 2-B)
      4. 토픽별 DuckDuckGo 확장 탐색 (Layer 3-A)
      5. 토픽별 네이버 카페 탐색 (Layer 3-B)
      6. 모든 결과를 하나의 DB 딕셔너리로 병합

    ■ 중단 지원:
      stop_event가 set되면 현재 단계 완료 후 중단

    ■ 진행률 콜백:
      progress_callback(현재단계, 전체단계, "메시지")

    Args:
        seed_data: 시드 DB 딕셔너리 (korean_sites_seed.json 내용)
        topic_names: 탐색할 토픽 목록 (None이면 seed의 매핑 키 전체)
        progress_callback: 진행률 콜백 함수
        stop_event: threading.Event (중단 신호)

    Returns:
        dict: 통합 사이트 DB 딕셔너리
    """
    # ── 결과 DB 초기화 (시드 데이터 복사) ──
    result = {
        "meta": {
            "version": "1.0",
            "description": "자동 탐색으로 구축된 통합 사이트 DB",
            "total_sites": 0,
            "total_boards": 0,
        },
        "sites": list(seed_data.get("sites", [])),
        "topic_site_mapping": dict(seed_data.get("topic_site_mapping", {})),
        "news_sites": list(seed_data.get("news_sites", [])),
        "dc_galleries": [],
        "naver_cafes": [],
        "discovered_sites": [],
    }

    # 이미 알려진 도메인 집합 (중복 방지용)
    known_domains: set[str] = set()
    for site in result["sites"]:
        if isinstance(site, dict) and site.get("domain"):
            known_domains.add(site["domain"])

    # 탐색할 토픽 목록
    if topic_names is None:
        topic_names = list(result.get("topic_site_mapping", {}).keys())

    # 전체 단계 수 계산
    # Layer 2: DC갤러리(1) + 사이트파싱(파서 수)
    # Layer 3: 토픽별 DDG(토픽수) + 네이버카페(토픽수)
    total_steps = 1 + len(_SITE_PARSERS) + len(topic_names) * 2
    current_step = 0

    def _progress(msg: str):
        nonlocal current_step
        current_step += 1
        if progress_callback:
            progress_callback(current_step, total_steps, msg)

    # ═══ Layer 2-A: DC갤러리 수집 ═══
    if stop_event and stop_event.is_set():
        return _finalize(result)

    _progress("디시인사이드 갤러리 목록 수집 중...")
    dc_galleries = discover_dc_galleries()
    result["dc_galleries"] = dc_galleries
    log.info("Layer 2-A 완료: DC갤러리 %d개", len(dc_galleries))

    # ═══ Layer 2-B: 사이트별 게시판 파싱 ═══
    for domain in _SITE_PARSERS:
        if stop_event and stop_event.is_set():
            return _finalize(result)

        _progress(f"{domain} 게시판 목록 파싱 중...")
        new_boards = discover_site_boards(domain)

        # 기존 사이트에 새로 파싱된 게시판 추가
        for site in result["sites"]:
            if isinstance(site, dict) and site.get("domain") == domain:
                existing_ids = {b.get("id") for b in site.get("boards", [])}
                for board in new_boards:
                    if board.get("id") not in existing_ids:
                        site.setdefault("boards", []).append(board)
                break

    # ═══ Layer 3: 토픽별 확장 탐색 ═══
    for topic in topic_names:
        if stop_event and stop_event.is_set():
            return _finalize(result)

        # Layer 3-A: DuckDuckGo 신규 사이트 발견
        _progress(f"'{topic}' 관련 사이트 검색 중...")
        new_sites = discover_via_duckduckgo(topic, known_domains)
        for ns in new_sites:
            known_domains.add(ns["domain"])
        result["discovered_sites"].extend(new_sites)

        if stop_event and stop_event.is_set():
            return _finalize(result)

        # Layer 3-B: 네이버 카페 탐색
        _progress(f"'{topic}' 네이버 카페 검색 중...")
        cafes = discover_naver_cafes(topic)
        result["naver_cafes"].extend(cafes)

    return _finalize(result)


def _finalize(data: dict) -> dict:
    """
    탐색 결과를 최종 정리합니다.
    메타 정보 업데이트, 중복 제거, 통계 갱신.
    """
    from datetime import datetime

    # 중복 네이버 카페 제거
    seen_cafe_ids: set[str] = set()
    unique_cafes: list[dict] = []
    for cafe in data.get("naver_cafes", []):
        cid = cafe.get("id", "")
        if cid and cid not in seen_cafe_ids:
            seen_cafe_ids.add(cid)
            unique_cafes.append(cafe)
    data["naver_cafes"] = unique_cafes

    # 중복 발견 사이트 제거
    seen_disc_domains: set[str] = set()
    unique_disc: list[dict] = []
    for ds in data.get("discovered_sites", []):
        dom = ds.get("domain", "")
        if dom and dom not in seen_disc_domains:
            seen_disc_domains.add(dom)
            unique_disc.append(ds)
    data["discovered_sites"] = unique_disc

    # 총계 산출
    total_sites = (
        len(data.get("sites", []))
        + len(unique_disc)
        + len(unique_cafes)
    )
    total_boards = (
        sum(
            len(s.get("boards", []))
            for s in data.get("sites", [])
            if isinstance(s, dict)
        )
        + len(data.get("dc_galleries", []))
    )

    # 메타 정보 갱신
    data["meta"].update({
        "updated": datetime.now().isoformat(),
        "total_sites": total_sites,
        "total_boards": total_boards,
        "dc_gallery_count": len(data.get("dc_galleries", [])),
        "naver_cafe_count": len(unique_cafes),
        "discovered_count": len(unique_disc),
    })

    log.info(
        "사이트 탐색 완료: %d개 사이트, %d개 게시판 "
        "(DC갤러리 %d, 네이버카페 %d, DDG발견 %d)",
        total_sites, total_boards,
        len(data.get("dc_galleries", [])),
        len(unique_cafes),
        len(unique_disc),
    )

    return data


# ═══════════════════════════════════════════════════
#  유틸리티 함수
# ═══════════════════════════════════════════════════
def _normalize_domain(url: str) -> str:
    """URL에서 도메인을 추출하고 정규화합니다 (www. 제거)"""
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    try:
        netloc = urlparse(url).netloc
        if netloc:
            return netloc.replace("www.", "").lower()
    except Exception:
        pass
    return ""


# 글로벌 사이트 도메인 (한국 사이트가 아니므로 제외)
_GLOBAL_DOMAINS = frozenset([
    "google.com", "youtube.com", "facebook.com", "twitter.com",
    "instagram.com", "tiktok.com", "reddit.com", "wikipedia.org",
    "amazon.com", "apple.com", "microsoft.com", "github.com",
    "linkedin.com", "pinterest.com", "tumblr.com", "quora.com",
    "stackoverflow.com", "medium.com", "discord.com", "twitch.tv",
])


def _is_global_site(domain: str) -> bool:
    """글로벌 사이트인지 확인 (한국 사이트만 수집하기 위해)"""
    if not domain:
        return True
    # 정확 매칭
    if domain in _GLOBAL_DOMAINS:
        return True
    # 서브도메인 포함 매칭 (예: m.youtube.com)
    for gd in _GLOBAL_DOMAINS:
        if domain.endswith("." + gd):
            return True
    return False


def get_all_domains_from_db(db_data: dict) -> set[str]:
    """DB에서 모든 도메인을 추출하여 집합으로 반환"""
    domains: set[str] = set()

    # 시드/큐레이션 사이트
    for site in db_data.get("sites", []):
        if isinstance(site, dict) and site.get("domain"):
            domains.add(site["domain"])

    # 발견된 사이트
    for ds in db_data.get("discovered_sites", []):
        if isinstance(ds, dict) and ds.get("domain"):
            domains.add(ds["domain"])

    # 뉴스 사이트
    for ns in db_data.get("news_sites", []):
        if isinstance(ns, dict) and ns.get("domain"):
            domains.add(ns["domain"])

    return domains
