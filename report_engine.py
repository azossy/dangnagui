#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
게시판 검색기 — 실시간 웹 검색 + 리포트 포맷 엔진 (report_engine.py)
═══════════════════════════════════════════════════════════════════════
DuckDuckGo 기반 실시간 검색 → 3중 필터링 → 통계 수집 → 리포트 생성

■ v1.3.0 주요 변경사항:
  1. 광고/홍보/스팸 3중 필터링 엔진 추가 (키워드 + URL + 점수제)
  2. 검색 통계 자동 수집 (토픽별 시간, 필터 건수, 도메인 분포)
  3. 암호화 DB 연동 (site: 타겟 검색으로 품질 향상)
  4. Buzz Score (회자 점수) 산출

copyright by 챠리 (challychoi@me.com)
"""
from __future__ import annotations

import re
import time
import random
from urllib.parse import urlparse
from datetime import datetime

from common import (
    SITES_CONFIG,
    DEFAULT_TOPICS, DEFAULT_KEYWORD_COUNT, DEFAULT_HOURS,
    DEFAULT_REPORT_HEADER,
    load_json, log, strip_leading_emoji, build_topic_config,
)

# ═══════════════════════════════════════════════════
#  DuckDuckGo 검색 라이브러리 로딩
# ═══════════════════════════════════════════════════
_HAS_DDGS = True
try:
    from duckduckgo_search import DDGS
except ImportError:
    _HAS_DDGS = False

# ═══════════════════════════════════════════════════
#  암호화 DB 로딩 (v1.3.0 신규)
#  사이트 DB에서 토픽별 도메인 목록을 가져와
#  site: 타겟 검색에 활용합니다.
# ═══════════════════════════════════════════════════
_HAS_DB_CRYPTO = True
try:
    from db_crypto import load_encrypted_db, get_db_summary
except ImportError:
    _HAS_DB_CRYPTO = False

# ═══════════════════════════════════════════════════
#  리포트 포맷 상수
# ═══════════════════════════════════════════════════
LINE_WIDTH = 24
SUMMARY_WIDTH = 32


# ═══════════════════════════════════════════════════
#  ◆◆◆ 광고/홍보/스팸 3중 필터링 엔진 (v1.3.0 신규) ◆◆◆
#  커뮤니티 게시판에서 흔히 보이는 광고/스팸 패턴을
#  3단계로 감지하여 리포트 품질을 보장합니다.
# ═══════════════════════════════════════════════════

# ── Filter 1: 광고 키워드 블랙리스트 ──
# 한국 커뮤니티에서 빈번한 광고/홍보 키워드 50개+
# 각 키워드가 제목+본문에 등장하면 스팸 점수 +1
_SPAM_KEYWORDS = frozenset([
    # 직접 광고/홍보
    "구매하기", "지금 바로", "최저가", "할인", "쿠폰", "무료배송",
    "이벤트 참여", "한정 수량", "선착순", "파격 할인", "특가",
    "홍보", "협찬", "제휴", "스폰서", "프로모션",
    # 도박/불법 (한국 커뮤니티 최대 스팸 유형)
    "카지노", "토토", "바카라", "슬롯", "배팅", "꽁머니",
    "대출", "당일대출", "무직자대출", "급전", "사채",
    # 마케팅 유도
    "클릭하세요", "지금 확인", "무료 체험", "가입하면",
    "텔레그램 문의", "카톡 문의", "문의", "상담",
    # 허위/과장
    "월 수익", "수익 인증", "재테크 비법", "부업 추천",
    "하루 만에", "100% 보장", "검증완료", "수익보장",
    # 성인/불법 콘텐츠
    "성인", "19금", "몰카", "불법촬영",
])

# ── Filter 2: 광고성 URL 패턴 ──
# 쇼핑몰 직링크, 단축URL, 제휴링크 등 광고 URL 패턴
_SPAM_URL_PATTERNS = [
    r"\.shopping\.",       # 쇼핑 도메인
    r"shop\.",             # shop. 서브도메인
    r"store\.",            # store. 서브도메인
    r"buy\.",              # buy. 서브도메인
    r"bit\.ly/",           # bit.ly 단축 URL
    r"tinyurl\.com/",      # tinyurl 단축 URL
    r"t\.co/",             # Twitter 단축 URL
    r"link\.coupang\.com", # 쿠팡 제휴 링크
    r"coupa\.ng/",         # 쿠팡 단축 링크
    r"coupang\.com/np/search",  # 쿠팡 검색 직링크
    r"partners\.coupang",  # 쿠팡 파트너스
    r"click\.",            # click tracking 도메인
    r"redirect\.",         # redirect 도메인
    r"tracking\.",         # tracking 도메인
    r"affiliate",          # 제휴 링크
]

# 컴파일된 URL 패턴 정규식 (성능 최적화)
_RE_SPAM_URL = re.compile("|".join(_SPAM_URL_PATTERNS), re.IGNORECASE)

# ── Filter 3: 스팸 점수 산출용 추가 패턴 ──
# 전화번호 패턴 (010-xxxx-xxxx, 02-xxx-xxxx 등)
_RE_PHONE = re.compile(r'0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}')

# 가격 패턴 반복 (xxxxx원, x,xxx원)
_RE_PRICE = re.compile(r'\d+[,.]?\d*원')


def _is_spam_url(url: str) -> bool:
    """URL이 광고성 패턴에 해당하는지 검사"""
    return bool(_RE_SPAM_URL.search(url)) if url else False


def _spam_score(title: str, body: str, url: str) -> int:
    """
    검색 결과 항목의 스팸 점수를 산출합니다 (0점 ~ 무한대).
    3점 이상이면 리포트에서 제외됩니다.

    ■ 점수 체계:
      - 광고 키워드 매칭: 1점/개 (최대 5점까지만)
      - 광고성 URL 패턴: 2점
      - 과도한 특수문자/이모지 (제목의 30% 초과): 1점
      - 전화번호 패턴 포함: 2점
      - 가격 표기 2회 이상 반복: 1점

    ■ 설계 의도:
      키워드 1개만으로는 제거되지 않아 오탐(false positive)을 최소화합니다.
      예: 뉴스 제목에 "할인"이 들어가도 다른 스팸 지표가 없으면 통과.

    Args:
        title: 검색 결과 제목
        body: 검색 결과 본문/요약
        url: 검색 결과 URL

    Returns:
        int: 스팸 점수 (0=깨끗, 3이상=스팸)
    """
    score = 0
    # 제목+본문을 합쳐서 검사 (소문자 변환)
    text = (title + " " + body).lower()

    # ── 키워드 블랙리스트 매칭 (1점씩, 최대 5점) ──
    kw_hits = sum(1 for kw in _SPAM_KEYWORDS if kw in text)
    score += min(kw_hits, 5)

    # ── 광고성 URL 패턴 (2점) ──
    if _is_spam_url(url):
        score += 2

    # ── 과도한 특수문자/이모지 비율 (1점) ──
    # 광고 게시글은 주목 끌기 위해 특수문자를 남발하는 경향
    if title:
        special_count = sum(
            1 for c in title
            if not c.isalnum() and c != ' ' and c != '·' and c != '-'
        )
        special_ratio = special_count / max(len(title), 1)
        if special_ratio > 0.3:
            score += 1

    # ── 전화번호 패턴 (2점) ──
    # 연락처가 본문에 있으면 높은 확률로 광고/영업 글
    if _RE_PHONE.search(text):
        score += 2

    # ── 가격 표기 반복 (1점) ──
    # "29,900원", "할인가 19,900원" 등이 2번 이상 나오면 쇼핑 광고
    price_matches = _RE_PRICE.findall(text)
    if len(price_matches) >= 2:
        score += 1

    return score


# ═══════════════════════════════════════════════════
#  언어 감지 — 한국어/영어만 허용, 중국어·일본어 등 배제
# ═══════════════════════════════════════════════════
_RE_HANGUL = re.compile(r'[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F\uFFA0-\uFFDC]')
_RE_CJK = re.compile(r'[\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF]')
_RE_JPONLY = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u31F0-\u31FF]')
_RE_LATIN = re.compile(r'[a-zA-Z]')


def _is_acceptable_lang(text: str) -> bool:
    """한국어 또는 영어가 주를 이루면 True, 중국어·일본어 등이면 False."""
    if not text:
        return False
    ko = len(_RE_HANGUL.findall(text))
    cjk = len(_RE_CJK.findall(text))
    jp = len(_RE_JPONLY.findall(text))
    en = len(_RE_LATIN.findall(text))

    other = cjk + jp
    if other == 0:
        return True
    if ko == 0 and en == 0 and other > 2:
        return False
    if ko > 0:
        return ko >= other * 0.5
    return en >= other


def _has_korean(text: str) -> bool:
    return bool(_RE_HANGUL.search(text)) if text else False


def _try_translate_text(text: str) -> str:
    """
    DuckDuckGo 번역 API로 영문 텍스트를 한국어로 번역 시도.
    duckduckgo-search 버전에 따라 반환 타입이 list 또는 dict일 수 있어
    양쪽 모두 방어적으로 처리합니다.
    """
    if not text or not _HAS_DDGS:
        return text
    if _has_korean(text):
        return text
    try:
        result = DDGS(timeout=10).translate(text[:500], to="ko")
        # duckduckgo-search >= 7.0: dict 반환 가능
        if isinstance(result, dict):
            translated = result.get("translated", "")
            if translated:
                return translated
        # duckduckgo-search < 7.0: list[dict] 반환
        elif isinstance(result, list) and result:
            translated = result[0].get("translated", "")
            if translated:
                return translated
        # 문자열 직접 반환 케이스 (미래 호환)
        elif isinstance(result, str) and result:
            return result
    except Exception as e:
        log.debug("Translation failed: %s", e)
    return text


# ═══════════════════════════════════════════════════
#  사이트 config 접근 (레거시 호환 + 암호화DB 통합)
# ═══════════════════════════════════════════════════
def _load_sites_config() -> dict:
    """사이트 설정을 로드합니다 (암호화 DB 우선, 레거시 폴백)"""
    # v1.3.0: 암호화 DB에서 먼저 로드 시도
    if _HAS_DB_CRYPTO:
        try:
            db = load_encrypted_db()
            if db and db.get("sites"):
                return db
        except Exception as e:
            log.debug("암호화 DB 로드 실패, 레거시 폴백: %s", e)

    # 레거시 sites_config.json 폴백
    return load_json(SITES_CONFIG)


def _extract_domain(url: str) -> str | None:
    """URL에서 도메인을 추출 (www. 제거)"""
    if not url or url in ("앱", "app"):
        return None
    u = url if url.startswith("http") else "https://" + url
    try:
        netloc = urlparse(u).netloc or u.split("/")[0]
        return netloc.replace("www.", "") if netloc else None
    except Exception:
        return None


def _get_topic_domains(topic_name: str) -> list[str]:
    """
    토픽에 매핑된 주요 도메인 목록을 반환합니다.
    v1.3.0: 암호화 DB의 topic_site_mapping에서 조회하여
    site: 타겟 검색에 활용합니다.

    Args:
        topic_name: 토픽명 (이모지 포함 가능)

    Returns:
        list[str]: 도메인 목록 (예: ["clien.net", "quasarzone.com"])
    """
    if not _HAS_DB_CRYPTO:
        return []

    try:
        db = load_encrypted_db()
        if not db:
            return []

        clean_name = strip_leading_emoji(topic_name) or topic_name
        mapping = db.get("topic_site_mapping", {})

        # 정확 매칭
        site_ids = mapping.get(clean_name, [])
        if not site_ids:
            # 퍼지 매칭 (부분 문자열)
            for key, ids in mapping.items():
                if clean_name in key or key in clean_name:
                    site_ids = ids
                    break

        if not site_ids:
            return []

        # site_id → domain 변환
        sites = db.get("sites", [])
        id_to_domain = {
            s["id"]: s["domain"]
            for s in sites
            if isinstance(s, dict) and s.get("id") and s.get("domain")
        }

        domains = []
        for sid in site_ids:
            domain = id_to_domain.get(sid)
            if domain:
                domains.append(domain)

        return domains[:10]  # site: 검색 과부하 방지, 상위 10개만

    except Exception as e:
        log.debug("토픽 도메인 조회 실패: %s", e)
        return []


# ═══════════════════════════════════════════════════
#  사이트·게시판 집계 (UI 표시용)
# ═══════════════════════════════════════════════════
def get_site_board_counts() -> tuple[int, int]:
    """전체 사이트 수, 게시판 수를 반환 (메인 화면 표시용)"""
    # v1.3.0: 암호화 DB 우선
    if _HAS_DB_CRYPTO:
        try:
            db = load_encrypted_db()
            if db and db.get("meta"):
                return (
                    db["meta"].get("total_sites", 0),
                    db["meta"].get("total_boards", 0),
                )
        except Exception:
            pass

    # 레거시 폴백
    cfg = load_json(SITES_CONFIG)
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
    """토픽별 사이트/게시판 수 반환 (설정 화면 표시용)"""
    cfg = _load_sites_config()
    if not cfg:
        return {}

    # v1.3.0: 새 DB 형식 처리
    if cfg.get("sites") and isinstance(cfg["sites"], list):
        mapping = cfg.get("topic_site_mapping", {})
        sites_by_id = {
            s["id"]: s
            for s in cfg["sites"]
            if isinstance(s, dict) and s.get("id")
        }
        targets = topic_names if topic_names else list(DEFAULT_TOPICS)
        result = {}
        for topic in targets:
            clean = strip_leading_emoji(topic) or topic
            site_ids = mapping.get(clean, [])
            domains: set[str] = set()
            boards = 0
            for sid in site_ids:
                site = sites_by_id.get(sid)
                if site:
                    d = site.get("domain")
                    if d:
                        domains.add(d)
                    boards += len(site.get("boards", []))
            result[topic] = (len(domains), boards)
        return result

    # 레거시 형식 처리
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
    """related_sites 리스트에서 고유 도메인/게시판 수 집계"""
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
    """무작위 URL 샘플 접속 검사 (유효율 백분율 반환)"""
    cfg = _load_sites_config()
    if not cfg:
        return -1
    urls = []

    # 새 DB 형식
    if cfg.get("sites") and isinstance(cfg["sites"], list):
        for site in cfg["sites"]:
            u = site.get("url", "")
            if u and u.startswith("http"):
                urls.append(u)
    else:
        # 레거시 형식
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
#  폴백 데이터 (검색 결과 없을 때 참고 정보)
# ═══════════════════════════════════════════════════
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
#  ◆◆◆ 실시간 웹 검색 (핵심 엔진) ◆◆◆
#  DuckDuckGo text + news 검색
#  + 언어 필터 + 스팸 3중 필터 + 통계 수집
#  + site: 타겟 검색 (v1.3.0)
# ═══════════════════════════════════════════════════
def search_topics_online(
    topic_config: dict[str, int],
    hours: int = 36,
    region: str = "kr-kr",
    progress_callback=None,
    stop_event=None,
) -> dict:
    """
    각 토픽에 대해 DuckDuckGo 실시간 검색을 수행하여 핫키워드를 수집합니다.

    ■ v1.3.0 개선사항:
      - 광고/스팸 3중 필터로 깨끗한 결과만 수집
      - site: 타겟 검색으로 알려진 커뮤니티에서 직접 검색
      - 검색 통계 자동 수집 (통계 대시보드용)
      - Buzz Score (회자 점수) 기초 데이터 수집

    Args:
        topic_config: {토픽명: 키워드수} 딕셔너리
        hours: 검색 시간 범위 (시간 단위)
        region: 검색 지역 코드
        progress_callback: 진행률 콜백 (current, total, topic, detail)
        stop_event: 중단 이벤트 (threading.Event)

    Returns:
        dict: {
            "수집시각": str,
            "기준": str,
            "카테고리": {토픽명: [아이템...]},
            "통계": {전체통계 + 토픽별통계}
        }
    """
    if not _HAS_DDGS:
        log.error("duckduckgo_search 미설치 — pip install duckduckgo-search")
        return {"카테고리": {}, "통계": {}}

    # ── 전체 검색 시작 시간 ──
    search_start_time = time.time()

    timelimit = _hours_to_timelimit(hours)
    total = len(topic_config)
    categories: dict[str, list] = {}

    # REQ-010: DDGS 인스턴스를 한 번만 생성하여 커넥션 재사용 (성능 개선)
    ddgs = DDGS(timeout=20)

    # ── 통계 수집용 딕셔너리 ──
    stats = {
        "total_time_sec": 0,
        "total_topics": total,
        "total_raw_results": 0,
        "total_lang_filtered": 0,
        "total_spam_filtered": 0,
        "total_translated": 0,
        "total_final_results": 0,
        "search_region": region,
        "search_hours": hours,
        "per_topic": {},
    }

    # 사이트/게시판 수 (UI 표시용)
    s_count, b_count = get_site_board_counts()
    stats["sites_searched"] = s_count
    stats["boards_searched"] = b_count

    for idx, (topic_name, kw_count) in enumerate(topic_config.items()):
        if stop_event and stop_event.is_set():
            break

        # ── 토픽별 검색 시작 시간 ──
        topic_start = time.time()

        clean_name = strip_leading_emoji(topic_name) or topic_name
        target = max(kw_count * 3, 10)

        if progress_callback:
            progress_callback(idx, total, clean_name, "웹 검색 중...")

        seen: set[str] = set()
        raw_items: list[dict] = []

        # ── v1.3.0: site: 타겟 검색 쿼리 추가 ──
        # 알려진 주요 사이트에서 직접 검색하여 품질 향상
        topic_domains = _get_topic_domains(topic_name)

        queries = [
            f"{clean_name} 커뮤니티 핫이슈 인기",
            f"{clean_name} 게시판 실시간 화제",
            f"{clean_name} 최신 이슈 논란",
        ]

        # 주요 도메인 상위 3개에 대해 site: 검색 추가
        for domain in topic_domains[:3]:
            queries.append(f"site:{domain} {clean_name} 인기")

        for q in queries:
            if len(raw_items) >= target:
                break
            try:
                for r in ddgs.text(
                    q, max_results=target,
                    timelimit=timelimit, region=region,
                ):
                    title = (r.get("title") or "").strip()
                    body = (r.get("body") or "").strip()
                    href = (r.get("href") or "").strip()
                    if not title or title.lower() in seen:
                        continue
                    seen.add(title.lower())
                    raw_items.append({
                        "제목": title[:80],
                        "의견요약": body[:300] if body else "",
                        "참고url": href,
                        "참고라벨": "",
                    })
            except Exception as e:
                log.warning("텍스트 검색 실패 '%s': %s", q, e)

        # ── 뉴스 검색 ──
        if progress_callback:
            progress_callback(idx, total, clean_name, "뉴스 검색 중...")

        try:
            for r in ddgs.news(
                clean_name, max_results=target,
                timelimit=timelimit, region=region,
            ):
                title = (r.get("title") or "").strip()
                body = (r.get("body") or "").strip()
                url = (r.get("url") or "").strip()
                if not title or title.lower() in seen:
                    continue
                seen.add(title.lower())
                raw_items.append({
                    "제목": title[:80],
                    "의견요약": body[:300] if body else "",
                    "참고url": url,
                    "참고라벨": r.get("source", ""),
                })
        except Exception as e:
            log.warning("뉴스 검색 실패 '%s': %s", clean_name, e)

        raw_count = len(raw_items)

        # ── 언어 필터: 한국어/영어만, 중국어·일본어 배제 ──
        items = [
            i for i in raw_items
            if _is_acceptable_lang(i["제목"] + " " + i["의견요약"])
        ]
        lang_filtered = raw_count - len(items)
        if lang_filtered:
            log.info("토픽 '%s': %d건 타국어 필터링", clean_name, lang_filtered)

        # ── ◆ v1.3.0: 광고/스팸 3중 필터 ◆ ──
        if progress_callback:
            progress_callback(idx, total, clean_name, "스팸 필터링 중...")

        pre_spam = len(items)
        items = [
            i for i in items
            if _spam_score(i["제목"], i["의견요약"], i["참고url"]) < 3
        ]
        spam_filtered = pre_spam - len(items)
        if spam_filtered:
            log.info(
                "토픽 '%s': %d건 광고/스팸 필터링 (3중 필터)",
                clean_name, spam_filtered,
            )

        # ── 한국어 결과 부족 시 영문 항목 번역 ──
        ko_items = [i for i in items if _has_korean(i["제목"])]
        en_items = [i for i in items if not _has_korean(i["제목"])]
        translated_count = 0

        if len(ko_items) < kw_count and en_items:
            if progress_callback:
                progress_callback(idx, total, clean_name, "영문 결과 번역 중...")
            need = kw_count - len(ko_items)
            for ei in en_items[:need]:
                tr_title = _try_translate_text(ei["제목"])
                tr_body = _try_translate_text(ei["의견요약"][:200])
                if tr_title != ei["제목"]:
                    translated_count += 1
                ko_items.append({
                    "제목": tr_title,
                    "의견요약": tr_body,
                    "참고url": ei["참고url"],
                    "참고라벨": (ei.get("참고라벨") or "") + (" (번역)" if tr_title != ei["제목"] else ""),
                })
            items = ko_items + [i for i in en_items[need:]]
        else:
            items = ko_items + en_items

        # ── 도메인 분포 집계 (통계용) ──
        domain_counts: dict[str, int] = {}
        for item in items:
            d = _extract_domain(item.get("참고url", ""))
            if d:
                domain_counts[d] = domain_counts.get(d, 0) + 1

        # 상위 도메인 정렬
        top_domains = sorted(
            domain_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]

        # ── 토픽별 통계 저장 ──
        topic_time = time.time() - topic_start
        stats["per_topic"][clean_name] = {
            "search_time_sec": round(topic_time, 2),
            "raw_count": raw_count,
            "lang_filtered": lang_filtered,
            "spam_filtered": spam_filtered,
            "translated": translated_count,
            "final_count": len(items),
            "top_domains": top_domains,
        }

        # ── 전체 통계 누적 ──
        stats["total_raw_results"] += raw_count
        stats["total_lang_filtered"] += lang_filtered
        stats["total_spam_filtered"] += spam_filtered
        stats["total_translated"] += translated_count
        stats["total_final_results"] += len(items)

        categories[topic_name] = items
        log.info(
            "토픽 '%s': %d건 수집 (원본 %d → 언어필터 -%d → 스팸필터 -%d → 최종 %d)",
            clean_name, len(items), raw_count, lang_filtered, spam_filtered, len(items),
        )

        if idx < total - 1:
            time.sleep(0.5)

    if progress_callback:
        progress_callback(total, total, "완료", "검색 완료")

    # ── 전체 검색 시간 기록 ──
    stats["total_time_sec"] = round(time.time() - search_start_time, 2)

    return {
        "수집시각": datetime.now().strftime("%Y년 %m월 %d일 %H:%M"),
        "기준": f"현재 시점 대비 {_timelimit_label(timelimit)} 이내",
        "검색어": [],
        "카테고리": categories,
        "베스트": [],
        "통계": stats,
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
#  메신저용 리포트 포맷 — 신문기사/보도자료 스타일
# ═══════════════════════════════════════════════════
def format_for_messenger(
    data: dict, settings: dict | None = None,
) -> tuple[str, int]:
    """
    검색 결과를 보도자료 스타일의 텍스트 리포트로 변환합니다.

    ■ v1.3.0 개선:
      - 스팸 필터 통계를 리포트 하단에 요약 표시
      - site: 타겟 검색 출처 표시 강화

    Args:
        data: search_topics_online() 결과
        settings: 사용자 설정 딕셔너리

    Returns:
        tuple[str, int]: (리포트 텍스트, 핫키워드 총 수)
    """
    lines: list[str] = []
    now = datetime.now()
    date_str = now.strftime("%Y년 %m월 %d일")
    site_count, board_count = get_site_board_counts()
    hours = settings.get("hours", DEFAULT_HOURS) if settings else DEFAULT_HOURS

    # DRY: common.build_topic_config()로 토픽 구성 추출
    topic_config = build_topic_config(settings or {})

    n_topics = len(topic_config)
    lines.append("")
    lines.append("✦ 게시판 검색기")
    lines.append(f"  {date_str} · {now.strftime('%H:%M')} 기준")
    lines.append("")
    actual_range = _timelimit_label(_hours_to_timelimit(hours))
    lines.append(f"※ {n_topics}개 토픽 · {hours}시간 기준 (실제 검색: {actual_range} 이내) · 실시간 웹 검색")
    if site_count or board_count:
        lines.append(f"  {site_count:,}개 사이트 · {board_count:,}개 게시판 DB 기반")
    lines.append("")

    # ── 사용자 정의 헤더 또는 기본 헤더 ──
    custom_header = ""
    if settings:
        custom_header = (settings.get("report_header") or "").strip()
    if custom_header:
        for hl in custom_header.split("\n"):
            lines.append(hl)
    else:
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
            title = t["제목"]
            source = t.get("참고라벨", "")
            if source:
                lines.append(f"  · {title} — {source}")
            else:
                lines.append(f"  · {title}")
            summary = t["의견요약"]
            if summary:
                for ln in _wrap(summary, width=SUMMARY_WIDTH):
                    lines.append(f"    {ln}")
            lines.append("")

    # ── v1.3.0: 스팸 필터 통계 요약 ──
    search_stats = data.get("통계", {})
    spam_count = search_stats.get("total_spam_filtered", 0)
    if spam_count > 0:
        lines.append(f"  ※ 광고/스팸 {spam_count}건 자동 필터링됨")

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
