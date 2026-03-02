#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
게시판 검색기 — 통계 수집/집계 엔진 (stats_engine.py)
═══════════════════════════════════════════════════════
검색 결과 데이터를 분석하여 전문적인 통계 지표를 산출합니다.

■ 핵심 기능:
  1. Buzz Score (회자 점수) — 키워드별 화제성을 0~100 스케일로 정량화
  2. 도메인 분포 분석 — 어떤 사이트에서 가장 많이 인용되었는지
  3. 필터링 효과 분석 — 스팸/언어 필터가 얼마나 걸러냈는지
  4. 토픽별 상세 통계 — 검색 시간, 수집 건수, 소스 다양성

■ Buzz Score 산출 공식:
  buzz = source_diversity(30) + position(25) + relevance(25) + recency(20)
  - source_diversity: 몇 개 사이트에서 동시에 언급되었는가
  - position: 검색 결과 상위 노출 여부
  - relevance: 토픽 키워드와의 관련도
  - recency: 뉴스 소스 여부 (최신성 가산)

copyright by 챠리 (challychoi@me.com)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from common import log, strip_leading_emoji


# ═══════════════════════════════════════════════════
#  Buzz Score 산출
#  키워드가 얼마나 "회자"되고 있는지를 정량화합니다.
# ═══════════════════════════════════════════════════
def calculate_buzz_score(
    item: dict,
    position: int,
    total_items: int,
    topic_name: str,
    all_items_in_topic: list[dict],
) -> int:
    """
    개별 검색 결과 항목의 Buzz Score를 0~100 스케일로 산출합니다.

    ■ 점수 구성 (총 100점):
      - source_diversity (최대 30점):
        동일 키워드의 핵심 단어가 다른 아이템에서도 언급되면 높은 점수.
        여러 사이트에서 동시에 회자되는 주제는 진짜 핫토픽.

      - position (최대 25점):
        DuckDuckGo 검색 결과에서 상위에 노출될수록 높은 점수.
        1위=25점, 10위=2.5점 식으로 선형 감소.

      - relevance (최대 25점):
        토픽 키워드와 제목의 겹치는 정도.
        "IT AI" 토픽 검색에서 "AI"가 제목에 있으면 높은 점수.

      - recency (최대 20점):
        뉴스 소스(참고라벨 존재)이면 20점 가산.
        커뮤니티 글보다 뉴스가 더 시의성이 높다는 가정.

    Args:
        item: 검색 결과 아이템 {"제목", "의견요약", "참고url", "참고라벨"}
        position: 검색 결과 내 순서 (0-based)
        total_items: 해당 토픽 전체 아이템 수
        topic_name: 토픽명
        all_items_in_topic: 해당 토픽의 전체 아이템 리스트

    Returns:
        int: 0~100 사이의 Buzz Score
    """
    title = item.get("제목", "")
    source = item.get("참고라벨", "")

    # ── 1) Source Diversity (최대 30점) ──
    # 이 아이템의 핵심 단어가 다른 아이템에서도 등장하는지 확인
    title_words = _extract_keywords(title)
    mention_count = 0
    for other in all_items_in_topic:
        if other is item:
            continue
        other_text = (other.get("제목", "") + " " + other.get("의견요약", "")).lower()
        if any(w in other_text for w in title_words):
            mention_count += 1

    # 언급된 아이템이 많을수록 source_diversity 높음
    if total_items > 1:
        diversity_ratio = min(mention_count / max(total_items - 1, 1), 1.0)
    else:
        diversity_ratio = 0
    source_diversity = round(diversity_ratio * 30)

    # ── 2) Position (최대 25점) ──
    # 검색 결과 상위일수록 높은 점수 (선형 감소)
    if total_items > 0:
        position_score = round((1 - position / max(total_items, 1)) * 25)
    else:
        position_score = 0
    position_score = max(0, min(25, position_score))

    # ── 3) Relevance (최대 25점) ──
    # 토픽 키워드와 제목의 매칭 정도
    topic_words = _extract_keywords(strip_leading_emoji(topic_name) or topic_name)
    title_lower = title.lower()
    if topic_words:
        match_count = sum(1 for tw in topic_words if tw in title_lower)
        relevance = round((match_count / len(topic_words)) * 25)
    else:
        relevance = 12  # 토픽 키워드 없으면 중간값

    # ── 4) Recency (최대 20점) ──
    # 뉴스 소스이면 최신성 가산
    recency = 20 if source else 5

    # ── 최종 점수 합산 (0~100 클램프) ──
    total = source_diversity + position_score + relevance + recency
    return max(0, min(100, total))


def _extract_keywords(text: str) -> list[str]:
    """텍스트에서 의미 있는 키워드를 추출 (2글자 이상)"""
    if not text:
        return []
    # 한글/영문 단어만 추출
    words = re.findall(r'[가-힣a-zA-Z]{2,}', text.lower())
    # 불용어 제거
    stopwords = {"이슈", "뉴스", "최신", "실시간", "화제", "인기", "관련", "게시판", "커뮤니티"}
    return [w for w in words if w not in stopwords][:5]


# ═══════════════════════════════════════════════════
#  검색 결과에 Buzz Score 추가
# ═══════════════════════════════════════════════════
def enrich_with_buzz_scores(data: dict) -> dict:
    """
    검색 결과의 각 아이템에 buzz_score를 추가합니다.
    또한 통계 딕셔너리에 키워드별 buzz_score 순위를 추가합니다.

    ■ 이 함수는 search_topics_online() 이후,
      format_for_messenger() 이전에 호출합니다.

    Args:
        data: search_topics_online() 반환값

    Returns:
        dict: buzz_score가 추가된 동일 구조의 데이터
    """
    categories = data.get("카테고리", {})
    stats = data.get("통계", {})

    all_buzz_items: list[dict] = []

    for topic_name, items in categories.items():
        clean_name = strip_leading_emoji(topic_name) or topic_name
        topic_stats = stats.get("per_topic", {}).get(clean_name, {})
        keywords_with_buzz: list[dict] = []

        for i, item in enumerate(items):
            # Buzz Score 산출
            buzz = calculate_buzz_score(
                item=item,
                position=i,
                total_items=len(items),
                topic_name=topic_name,
                all_items_in_topic=items,
            )
            item["buzz_score"] = buzz

            # 소스 카운트 (도메인 다양성 참고)
            domain = _extract_domain_simple(item.get("참고url", ""))
            source_count = 1
            if domain and topic_stats.get("top_domains"):
                for d, cnt in topic_stats["top_domains"]:
                    if d == domain:
                        source_count = cnt
                        break

            keywords_with_buzz.append({
                "title": item["제목"],
                "buzz_score": buzz,
                "source_count": source_count,
                "topic": clean_name,
            })

            all_buzz_items.append({
                "title": item["제목"],
                "buzz_score": buzz,
                "source_count": source_count,
                "topic": clean_name,
            })

        # 토픽별 통계에 keywords 추가
        if clean_name in stats.get("per_topic", {}):
            stats["per_topic"][clean_name]["keywords"] = sorted(
                keywords_with_buzz,
                key=lambda x: x["buzz_score"],
                reverse=True,
            )

    # 전체 Buzz Score 순위 (상위 30개)
    stats["buzz_ranking"] = sorted(
        all_buzz_items,
        key=lambda x: x["buzz_score"],
        reverse=True,
    )[:30]

    return data


def _extract_domain_simple(url: str) -> str:
    """URL에서 도메인만 간단히 추출"""
    if not url:
        return ""
    try:
        if not url.startswith("http"):
            url = "https://" + url
        return urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


# ═══════════════════════════════════════════════════
#  전체 도메인 분포 집계
# ═══════════════════════════════════════════════════
def aggregate_domain_stats(data: dict) -> list[tuple[str, int]]:
    """
    전체 검색 결과에서 도메인별 인용 횟수를 집계합니다.
    통계 대시보드의 "출처 도메인 TOP 20" 차트에 사용.

    Args:
        data: search_topics_online() 반환값

    Returns:
        list[tuple[str, int]]: [(도메인, 인용횟수)] 내림차순 정렬
    """
    domain_counts: dict[str, int] = {}

    for topic_name, items in data.get("카테고리", {}).items():
        for item in items:
            domain = _extract_domain_simple(item.get("참고url", ""))
            if domain:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

    return sorted(
        domain_counts.items(),
        key=lambda x: x[1],
        reverse=True,
    )


# ═══════════════════════════════════════════════════
#  필터링 효과 분석
# ═══════════════════════════════════════════════════
def get_filter_breakdown(stats: dict) -> dict:
    """
    필터링 효과를 상세 분석합니다.
    통계 대시보드의 파이 차트에 사용.

    Args:
        stats: data["통계"] 딕셔너리

    Returns:
        dict: {
            "total_collected": int,     # 원본 수집 건수
            "final_results": int,       # 최종 선별 건수
            "lang_filtered": int,       # 언어 필터 제거
            "spam_filtered": int,       # 스팸 필터 제거
            "duplicates_removed": int,  # 중복 제거 (추정)
            "filter_rate_pct": float,   # 전체 필터율 (%)
        }
    """
    total_raw = stats.get("total_raw_results", 0)
    total_final = stats.get("total_final_results", 0)
    lang_f = stats.get("total_lang_filtered", 0)
    spam_f = stats.get("total_spam_filtered", 0)

    # 중복 제거 건수 추정 (원본 - 언어필터 - 스팸필터 - 최종)
    duplicates = max(0, total_raw - lang_f - spam_f - total_final)

    filter_rate = 0
    if total_raw > 0:
        filter_rate = round((1 - total_final / total_raw) * 100, 1)

    return {
        "total_collected": total_raw,
        "final_results": total_final,
        "lang_filtered": lang_f,
        "spam_filtered": spam_f,
        "duplicates_removed": duplicates,
        "filter_rate_pct": filter_rate,
    }


# ═══════════════════════════════════════════════════
#  토픽별 상세 테이블 데이터
# ═══════════════════════════════════════════════════
def get_topic_table_data(stats: dict) -> list[dict]:
    """
    통계 대시보드의 토픽별 상세 테이블용 데이터를 생성합니다.

    Returns:
        list[dict]: 각 토픽의 상세 통계 행
        [{"topic": str, "time": float, "raw": int, "spam": int,
          "lang": int, "translated": int, "final": int, "top_domain": str}]
    """
    rows: list[dict] = []
    per_topic = stats.get("per_topic", {})

    for topic_name, ts in per_topic.items():
        top_domain = ""
        if ts.get("top_domains"):
            top_domain = ts["top_domains"][0][0]  # 최다 인용 도메인

        rows.append({
            "topic": topic_name,
            "time": ts.get("search_time_sec", 0),
            "raw": ts.get("raw_count", 0),
            "spam": ts.get("spam_filtered", 0),
            "lang": ts.get("lang_filtered", 0),
            "translated": ts.get("translated", 0),
            "final": ts.get("final_count", 0),
            "top_domain": top_domain,
        })

    return rows
