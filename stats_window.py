#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
게시판 검색기 — 통계 대시보드 UI + PDF 내보내기 (stats_window.py)
═══════════════════════════════════════════════════════════════════
matplotlib 차트를 tkinter에 임베드하여 전문적인 통계 대시보드를 제공합니다.

■ 대시보드 구성 (6개 섹션):
  1. 검색 개요 카드 — 핵심 수치 한눈에
  2. Buzz Score 순위 차트 — 가로 막대 (상위 15개)
  3. 토픽별 수집 건수 비교 — 그룹 막대
  4. 필터링 분석 — 도넛 차트
  5. 출처 도메인 TOP 15 — 가로 막대
  6. 토픽별 상세 테이블 — Treeview

■ PDF 내보내기:
  matplotlib.backends.backend_pdf.PdfPages로 멀티 페이지 PDF 생성
  한글 폰트 자동 감지 (맑은 고딕 / NanumGothic)

copyright by 챠리 (challychoi@me.com)
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime

from common import BASE, APP_VERSION, log

# ═══════════════════════════════════════════════════
#  matplotlib 로딩 (선택적 의존성)
#  없으면 간단한 텍스트 통계만 표시
# ═══════════════════════════════════════════════════
_HAS_MPL = True
try:
    import matplotlib
    matplotlib.use("Agg")  # GUI 백엔드 충돌 방지
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.figure import Figure
    import matplotlib.font_manager as fm
except ImportError:
    _HAS_MPL = False
    log.info("matplotlib 미설치 — 차트 없는 텍스트 통계만 표시")

# ═══════════════════════════════════════════════════
#  한글 폰트 자동 감지
#  Windows: 맑은 고딕, macOS: AppleGothic, Linux: NanumGothic
# ═══════════════════════════════════════════════════
_KOREAN_FONT = None


def _find_korean_font() -> str | None:
    """시스템에 설치된 한글 폰트를 자동으로 찾습니다."""
    global _KOREAN_FONT
    if _KOREAN_FONT is not None:
        return _KOREAN_FONT if _KOREAN_FONT else None

    if not _HAS_MPL:
        return None

    # 우선순위: 맑은 고딕 → NanumGothic → AppleGothic
    candidates = ["Malgun Gothic", "맑은 고딕", "NanumGothic", "AppleGothic"]
    for name in candidates:
        try:
            path = fm.findfont(name, fallback_to_default=False)
            if path and "LastResort" not in path and "cmr10" not in path:
                _KOREAN_FONT = name
                log.info("한글 폰트 감지: %s", name)
                return name
        except Exception:
            continue

    log.warning("한글 폰트를 찾을 수 없습니다 — 차트에 한글이 깨질 수 있음")
    _KOREAN_FONT = ""
    return None


def _apply_korean_font():
    """matplotlib에 한글 폰트를 적용합니다."""
    if not _HAS_MPL:
        return
    font_name = _find_korean_font()
    if font_name:
        plt.rcParams["font.family"] = font_name
        plt.rcParams["axes.unicode_minus"] = False


# ═══════════════════════════════════════════════════
#  다크 테마 색상 (메인 UI와 통일)
# ═══════════════════════════════════════════════════
_DARK_BG = "#1e1e1e"
_DARK_CARD = "#252526"
_DARK_TEXT = "#d4d4d4"
_DARK_MUTED = "#858585"
_DARK_ACCENT = "#0078d4"
_DARK_BORDER = "#3f3f46"

# 차트용 색상 팔레트 (10색, 다크 테마에 어울리는 밝은 톤)
_CHART_COLORS = [
    "#4ec9b0", "#569cd6", "#ce9178", "#c586c0", "#dcdcaa",
    "#9cdcfe", "#d7ba7d", "#f44747", "#608b4e", "#d16969",
]


# ═══════════════════════════════════════════════════
#  메인 진입점: 통계 대시보드 창 열기
# ═══════════════════════════════════════════════════
def open_stats_window(parent: tk.Tk, stats_data: dict, search_data: dict):
    """
    통계 대시보드 Toplevel 창을 엽니다.

    Args:
        parent: 부모 Tk 윈도우
        stats_data: data["통계"] 딕셔너리
        search_data: search_topics_online() 전체 반환값
    """
    from stats_engine import (
        aggregate_domain_stats,
        get_filter_breakdown,
        get_topic_table_data,
    )

    _apply_korean_font()

    # ── 윈도우 생성 ──
    win = tk.Toplevel(parent)
    win.title("통계 대시보드 — 게시판 검색기")
    win.geometry("1000x700")
    win.minsize(800, 550)
    win.configure(bg=_DARK_BG)
    win.transient(parent)

    # ── 상단 툴바 ──
    toolbar = tk.Frame(win, bg=_DARK_CARD, pady=6)
    toolbar.pack(fill=tk.X)

    tk.Label(
        toolbar, text="📊 통계 대시보드",
        font=("Segoe UI", 14, "bold"), fg=_DARK_TEXT, bg=_DARK_CARD,
    ).pack(side=tk.LEFT, padx=16)

    tk.Label(
        toolbar, text=APP_VERSION,
        font=("Segoe UI", 9), fg=_DARK_MUTED, bg=_DARK_CARD,
    ).pack(side=tk.LEFT, padx=(0, 20))

    # PDF 내보내기 버튼
    def _on_export_pdf():
        _export_pdf(stats_data, search_data, win)

    pdf_btn = tk.Button(
        toolbar, text="  📄 PDF 내보내기  ",
        font=("Segoe UI", 10, "bold"), fg="#fff", bg=_DARK_ACCENT,
        activebackground="#1a8ad4", relief=tk.FLAT, cursor="hand2",
        command=_on_export_pdf,
    )
    pdf_btn.pack(side=tk.RIGHT, padx=16)
    pdf_btn.bind("<Enter>", lambda e: pdf_btn.config(bg="#1a8ad4"))
    pdf_btn.bind("<Leave>", lambda e: pdf_btn.config(bg=_DARK_ACCENT))

    # 닫기 버튼
    close_btn = tk.Button(
        toolbar, text="닫기",
        font=("Segoe UI", 9), fg=_DARK_MUTED, bg=_DARK_CARD,
        activeforeground=_DARK_TEXT, relief=tk.FLAT, cursor="hand2",
        command=win.destroy,
    )
    close_btn.pack(side=tk.RIGHT, padx=4)

    # ── 스크롤 가능한 메인 영역 ──
    canvas = tk.Canvas(win, bg=_DARK_BG, highlightthickness=0)
    vsb = ttk.Scrollbar(win, orient=tk.VERTICAL, command=canvas.yview)
    main_frame = tk.Frame(canvas, bg=_DARK_BG)
    main_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.create_window((0, 0), window=main_frame, anchor=tk.NW)
    canvas.configure(yscrollcommand=vsb.set)
    canvas.bind(
        "<Configure>",
        lambda e: canvas.itemconfig(canvas.find_all()[0], width=e.width),
    )

    def _mw(e):
        if not canvas.winfo_exists():
            return
        w = e.widget
        while w:
            if w is win:
                canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
                return
            try:
                w = w.master
            except AttributeError:
                return

    _mw_bind_id = win.bind_all("<MouseWheel>", _mw, add=True)

    def _on_close():
        _safe_unbind(win, _mw_bind_id)
        for fig in _embedded_figures:
            try:
                plt.close(fig)
            except Exception:
                pass
        _embedded_figures.clear()
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", _on_close)

    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    pad = 16

    # ═══════════════════════════════════════════════
    #  Section 1: 검색 개요 카드
    # ═══════════════════════════════════════════════
    _build_summary_cards(main_frame, stats_data, pad)

    # ═══════════════════════════════════════════════
    #  Section 2~5: matplotlib 차트 (설치 시)
    # ═══════════════════════════════════════════════
    if _HAS_MPL:
        # Section 2: Buzz Score 순위 차트
        _build_buzz_chart(main_frame, stats_data, pad)

        # Section 3: 토픽별 수집 건수 비교
        _build_topic_comparison(main_frame, stats_data, pad)

        # Section 4: 필터링 분석 도넛 차트
        filter_info = get_filter_breakdown(stats_data)
        _build_filter_chart(main_frame, filter_info, pad)

        # Section 5: 출처 도메인 TOP 15
        domain_stats = aggregate_domain_stats(search_data)
        _build_domain_chart(main_frame, domain_stats, pad)
    else:
        _build_no_matplotlib_notice(main_frame, pad)

    # ═══════════════════════════════════════════════
    #  Section 6: 토픽별 상세 테이블
    # ═══════════════════════════════════════════════
    table_data = get_topic_table_data(stats_data)
    _build_detail_table(main_frame, table_data, pad)


def _safe_unbind(win, bind_id):
    """특정 bind ID만 해제하여 다른 윈도우의 바인딩을 보존합니다."""
    try:
        if bind_id:
            win.unbind("<MouseWheel>", bind_id)
    except Exception:
        pass


# ═══════════════════════════════════════════════════
#  Section 1: 검색 개요 카드
# ═══════════════════════════════════════════════════
def _build_summary_cards(parent: tk.Frame, stats: dict, pad: int):
    """핵심 수치를 카드 형태로 표시합니다."""
    section = tk.Frame(parent, bg=_DARK_BG)
    section.pack(fill=tk.X, padx=pad, pady=(pad, 8))

    tk.Label(
        section, text="검색 개요",
        font=("Segoe UI", 12, "bold"), fg=_DARK_TEXT, bg=_DARK_BG,
    ).pack(anchor=tk.W, pady=(0, 8))

    cards_frame = tk.Frame(section, bg=_DARK_BG)
    cards_frame.pack(fill=tk.X)

    # 카드 데이터
    total_time = stats.get("total_time_sec", 0)
    card_items = [
        ("⏱", "총 검색 시간", f"{total_time:.1f}초"),
        ("📋", "검색 토픽", f"{stats.get('total_topics', 0)}개"),
        ("🌐", "검색 대상", f"{stats.get('sites_searched', 0):,}사이트 / {stats.get('boards_searched', 0):,}게시판"),
        ("📊", "수집 결과", f"{stats.get('total_raw_results', 0):,}건 → {stats.get('total_final_results', 0):,}건"),
        ("🛡", "스팸 제거", f"{stats.get('total_spam_filtered', 0):,}건"),
        ("🌏", "언어 필터", f"{stats.get('total_lang_filtered', 0):,}건"),
        ("🔄", "번역 처리", f"{stats.get('total_translated', 0):,}건"),
        ("📡", "검색 지역", f"{stats.get('search_region', 'kr-kr')} / {stats.get('search_hours', 36)}시간"),
    ]

    for i, (icon, label, value) in enumerate(card_items):
        col = i % 4
        row = i // 4
        card = tk.Frame(
            cards_frame, bg=_DARK_CARD, padx=12, pady=8,
            highlightbackground=_DARK_BORDER, highlightthickness=1,
        )
        card.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")

        tk.Label(
            card, text=f"{icon} {label}",
            font=("Segoe UI", 9), fg=_DARK_MUTED, bg=_DARK_CARD,
        ).pack(anchor=tk.W)
        tk.Label(
            card, text=value,
            font=("Segoe UI", 11, "bold"), fg=_DARK_TEXT, bg=_DARK_CARD,
        ).pack(anchor=tk.W, pady=(2, 0))

    for c in range(4):
        cards_frame.columnconfigure(c, weight=1)


# ═══════════════════════════════════════════════════
#  Section 2: Buzz Score 순위 차트
# ═══════════════════════════════════════════════════
def _build_buzz_chart(parent: tk.Frame, stats: dict, pad: int):
    """Buzz Score 상위 15개 키워드 가로 막대 차트"""
    buzz_ranking = stats.get("buzz_ranking", [])
    if not buzz_ranking:
        return

    section = tk.Frame(parent, bg=_DARK_BG)
    section.pack(fill=tk.X, padx=pad, pady=(8, 8))
    tk.Label(
        section, text="Buzz Score 순위 (회자 점수 TOP 15)",
        font=("Segoe UI", 12, "bold"), fg=_DARK_TEXT, bg=_DARK_BG,
    ).pack(anchor=tk.W, pady=(0, 4))

    top_items = buzz_ranking[:15]
    labels = [_truncate(item["title"], 25) for item in reversed(top_items)]
    scores = [item["buzz_score"] for item in reversed(top_items)]
    colors = [_CHART_COLORS[i % len(_CHART_COLORS)] for i in range(len(top_items))]
    colors.reverse()

    fig = Figure(figsize=(9, max(4, len(top_items) * 0.35)), dpi=100)
    fig.patch.set_facecolor(_DARK_BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(_DARK_CARD)

    bars = ax.barh(labels, scores, color=colors, height=0.6)
    ax.set_xlabel("Buzz Score", color=_DARK_MUTED, fontsize=9)
    ax.set_xlim(0, 105)
    ax.tick_params(colors=_DARK_MUTED, labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color(_DARK_BORDER)
    ax.spines["left"].set_color(_DARK_BORDER)

    for bar, score in zip(bars, scores):
        ax.text(
            bar.get_width() + 1, bar.get_y() + bar.get_height() / 2,
            str(score), va="center", color=_DARK_TEXT, fontsize=8,
        )

    fig.tight_layout()
    _embed_figure(section, fig)


# ═══════════════════════════════════════════════════
#  Section 3: 토픽별 수집 건수 비교
# ═══════════════════════════════════════════════════
def _build_topic_comparison(parent: tk.Frame, stats: dict, pad: int):
    """토픽별 원본/필터후/최종 건수 그룹 막대 차트"""
    per_topic = stats.get("per_topic", {})
    if not per_topic:
        return

    section = tk.Frame(parent, bg=_DARK_BG)
    section.pack(fill=tk.X, padx=pad, pady=(8, 8))
    tk.Label(
        section, text="토픽별 수집 건수 비교",
        font=("Segoe UI", 12, "bold"), fg=_DARK_TEXT, bg=_DARK_BG,
    ).pack(anchor=tk.W, pady=(0, 4))

    topics = list(per_topic.keys())
    raw_counts = [per_topic[t].get("raw_count", 0) for t in topics]
    spam_removed = [
        per_topic[t].get("raw_count", 0) - per_topic[t].get("lang_filtered", 0) - per_topic[t].get("spam_filtered", 0)
        for t in topics
    ]
    final_counts = [per_topic[t].get("final_count", 0) for t in topics]
    labels = [_truncate(t, 12) for t in topics]

    fig = Figure(figsize=(9, 4), dpi=100)
    fig.patch.set_facecolor(_DARK_BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(_DARK_CARD)

    import numpy as np
    x = np.arange(len(topics))
    width = 0.25

    ax.bar(x - width, raw_counts, width, label="원본 수집", color="#569cd6", alpha=0.8)
    ax.bar(x, spam_removed, width, label="필터 후", color="#4ec9b0", alpha=0.8)
    ax.bar(x + width, final_counts, width, label="최종 선별", color="#dcdcaa", alpha=0.8)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("건수", color=_DARK_MUTED, fontsize=9)
    ax.legend(fontsize=8, facecolor=_DARK_CARD, edgecolor=_DARK_BORDER, labelcolor=_DARK_TEXT)
    ax.tick_params(colors=_DARK_MUTED, labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color(_DARK_BORDER)
    ax.spines["left"].set_color(_DARK_BORDER)

    fig.tight_layout()
    _embed_figure(section, fig)


# ═══════════════════════════════════════════════════
#  Section 4: 필터링 분석 도넛 차트
# ═══════════════════════════════════════════════════
def _build_filter_chart(parent: tk.Frame, filter_info: dict, pad: int):
    """필터링 효과 도넛 차트"""
    section = tk.Frame(parent, bg=_DARK_BG)
    section.pack(fill=tk.X, padx=pad, pady=(8, 8))
    tk.Label(
        section, text=f"필터링 효과 분석 (필터율: {filter_info.get('filter_rate_pct', 0)}%)",
        font=("Segoe UI", 12, "bold"), fg=_DARK_TEXT, bg=_DARK_BG,
    ).pack(anchor=tk.W, pady=(0, 4))

    fig = Figure(figsize=(9, 3.5), dpi=100)
    fig.patch.set_facecolor(_DARK_BG)

    # 좌측: 전체 결과 구성
    ax1 = fig.add_subplot(121)
    ax1.set_facecolor(_DARK_BG)

    sizes1 = [
        filter_info.get("final_results", 0),
        filter_info.get("spam_filtered", 0),
        filter_info.get("lang_filtered", 0),
        filter_info.get("duplicates_removed", 0),
    ]
    labels1 = ["최종 선별", "스팸 제거", "언어 필터", "기타 제거"]
    colors1 = ["#4ec9b0", "#f44747", "#569cd6", "#858585"]

    # 0인 항목 제외
    non_zero = [(s, l, c) for s, l, c in zip(sizes1, labels1, colors1) if s > 0]
    if non_zero:
        s, l, c = zip(*non_zero)
        wedges, texts, autotexts = ax1.pie(
            s, labels=l, colors=c, autopct="%1.0f%%",
            startangle=90, pctdistance=0.75,
            textprops={"color": _DARK_TEXT, "fontsize": 8},
        )
        for at in autotexts:
            at.set_fontsize(7)
        centre_circle = plt.Circle((0, 0), 0.50, fc=_DARK_BG)
        ax1.add_artist(centre_circle)
    ax1.set_title("결과 구성", color=_DARK_TEXT, fontsize=10, pad=10)

    # 우측: 스팸 유형 상세 (있으면)
    ax2 = fig.add_subplot(122)
    ax2.set_facecolor(_DARK_BG)

    spam_total = filter_info.get("spam_filtered", 0)
    if spam_total > 0:
        sizes2 = [spam_total]
        labels2 = [f"스팸 {spam_total}건"]
        colors2 = ["#f44747"]
        lang_total = filter_info.get("lang_filtered", 0)
        if lang_total > 0:
            sizes2.append(lang_total)
            labels2.append(f"언어필터 {lang_total}건")
            colors2.append("#569cd6")

        wedges2, texts2, autotexts2 = ax2.pie(
            sizes2, labels=labels2, colors=colors2, autopct="%1.0f%%",
            startangle=90, pctdistance=0.75,
            textprops={"color": _DARK_TEXT, "fontsize": 8},
        )
        for at in autotexts2:
            at.set_fontsize(7)
        centre2 = plt.Circle((0, 0), 0.50, fc=_DARK_BG)
        ax2.add_artist(centre2)
    else:
        ax2.text(
            0.5, 0.5, "스팸 0건\n필터링 없음",
            ha="center", va="center", color=_DARK_MUTED, fontsize=10,
            transform=ax2.transAxes,
        )
        ax2.set_xlim(0, 1)
        ax2.set_ylim(0, 1)
        ax2.axis("off")

    ax2.set_title("필터 상세", color=_DARK_TEXT, fontsize=10, pad=10)

    fig.tight_layout()
    _embed_figure(section, fig)


# ═══════════════════════════════════════════════════
#  Section 5: 출처 도메인 TOP 15
# ═══════════════════════════════════════════════════
def _build_domain_chart(parent: tk.Frame, domain_stats: list, pad: int):
    """가장 많이 인용된 도메인 상위 15개 가로 막대 차트"""
    if not domain_stats:
        return

    section = tk.Frame(parent, bg=_DARK_BG)
    section.pack(fill=tk.X, padx=pad, pady=(8, 8))
    tk.Label(
        section, text="출처 도메인 TOP 15",
        font=("Segoe UI", 12, "bold"), fg=_DARK_TEXT, bg=_DARK_BG,
    ).pack(anchor=tk.W, pady=(0, 4))

    top = domain_stats[:15]
    labels = [d for d, _ in reversed(top)]
    counts = [c for _, c in reversed(top)]
    colors = [_CHART_COLORS[i % len(_CHART_COLORS)] for i in range(len(top))]
    colors.reverse()

    fig = Figure(figsize=(9, max(3, len(top) * 0.3)), dpi=100)
    fig.patch.set_facecolor(_DARK_BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(_DARK_CARD)

    bars = ax.barh(labels, counts, color=colors, height=0.6)
    ax.set_xlabel("인용 횟수", color=_DARK_MUTED, fontsize=9)
    ax.tick_params(colors=_DARK_MUTED, labelsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color(_DARK_BORDER)
    ax.spines["left"].set_color(_DARK_BORDER)

    for bar, count in zip(bars, counts):
        ax.text(
            bar.get_width() + 0.3, bar.get_y() + bar.get_height() / 2,
            str(count), va="center", color=_DARK_TEXT, fontsize=8,
        )

    fig.tight_layout()
    _embed_figure(section, fig)


# ═══════════════════════════════════════════════════
#  Section 6: 토픽별 상세 테이블
# ═══════════════════════════════════════════════════
def _build_detail_table(parent: tk.Frame, table_data: list, pad: int):
    """토픽별 상세 통계 Treeview 테이블"""
    section = tk.Frame(parent, bg=_DARK_BG)
    section.pack(fill=tk.X, padx=pad, pady=(8, pad))
    tk.Label(
        section, text="토픽별 상세 통계",
        font=("Segoe UI", 12, "bold"), fg=_DARK_TEXT, bg=_DARK_BG,
    ).pack(anchor=tk.W, pady=(0, 4))

    columns = ("topic", "time", "raw", "spam", "lang", "trans", "final", "domain")
    tree = ttk.Treeview(section, columns=columns, show="headings", height=min(len(table_data) + 1, 15))

    headings = {
        "topic": ("토픽", 120),
        "time": ("검색시간", 70),
        "raw": ("원본건수", 70),
        "spam": ("스팸제거", 70),
        "lang": ("언어필터", 70),
        "trans": ("번역", 50),
        "final": ("최종건수", 70),
        "domain": ("상위 도메인", 150),
    }

    for col, (heading, width) in headings.items():
        tree.heading(col, text=heading)
        tree.column(col, width=width, anchor=tk.CENTER if col != "domain" else tk.W)

    # 다크 테마 스타일
    style = ttk.Style()
    style.configure(
        "Stats.Treeview",
        background=_DARK_CARD,
        foreground=_DARK_TEXT,
        fieldbackground=_DARK_CARD,
        borderwidth=0,
        font=("Segoe UI", 9),
    )
    style.configure(
        "Stats.Treeview.Heading",
        background=_DARK_BORDER,
        foreground=_DARK_TEXT,
        font=("Segoe UI", 9, "bold"),
    )
    tree.configure(style="Stats.Treeview")

    for row in table_data:
        tree.insert("", tk.END, values=(
            row["topic"],
            f"{row['time']:.1f}초",
            f"{row['raw']}건",
            f"{row['spam']}건",
            f"{row['lang']}건",
            f"{row['translated']}건",
            f"{row['final']}건",
            row["top_domain"],
        ))

    tree.pack(fill=tk.X, pady=(0, 8))


# ═══════════════════════════════════════════════════
#  matplotlib 미설치 시 안내
# ═══════════════════════════════════════════════════
def _build_no_matplotlib_notice(parent: tk.Frame, pad: int):
    """matplotlib 미설치 시 텍스트 안내"""
    section = tk.Frame(parent, bg=_DARK_CARD, padx=20, pady=16)
    section.pack(fill=tk.X, padx=pad, pady=8)
    tk.Label(
        section,
        text="차트를 표시하려면 matplotlib을 설치하세요:\npip install matplotlib",
        font=("Segoe UI", 10), fg="#ff8c00", bg=_DARK_CARD,
        justify=tk.LEFT,
    ).pack(anchor=tk.W)


# ═══════════════════════════════════════════════════
#  matplotlib Figure를 tkinter에 임베드
# ═══════════════════════════════════════════════════
_embedded_figures: list = []


def _embed_figure(parent: tk.Frame, fig: Figure):
    """matplotlib Figure를 tkinter Frame에 임베드합니다."""
    _embedded_figures.append(fig)
    canvas = FigureCanvasTkAgg(fig, master=parent)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=tk.X, pady=(0, 4))


# ═══════════════════════════════════════════════════
#  PDF 내보내기
# ═══════════════════════════════════════════════════
def _export_pdf(stats: dict, search_data: dict, parent_win: tk.Toplevel):
    """
    통계 대시보드를 PDF로 내보냅니다.

    ■ PDF 구성 (3~4 페이지):
      Page 1: 표지 + 검색 개요
      Page 2: Buzz Score 순위 + 토픽별 비교
      Page 3: 필터링 분석 + 도메인 TOP 15
      Page 4: 토픽별 상세 테이블
    """
    if not _HAS_MPL:
        messagebox.showwarning(
            "PDF 내보내기",
            "matplotlib이 설치되지 않아 PDF를 생성할 수 없습니다.\n\n"
            "pip install matplotlib 로 설치하세요.",
            parent=parent_win,
        )
        return

    from stats_engine import aggregate_domain_stats, get_filter_breakdown, get_topic_table_data

    _apply_korean_font()

    # 저장 경로 선택
    default_dir = BASE / "IMoutput"
    try:
        default_dir.mkdir(exist_ok=True)
    except OSError:
        default_dir = Path.home()

    filename = f"통계리포트_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = filedialog.asksaveasfilename(
        parent=parent_win,
        title="통계 리포트 PDF 저장",
        initialdir=str(default_dir),
        initialfile=filename,
        defaultextension=".pdf",
        filetypes=[("PDF 파일", "*.pdf")],
    )
    if not filepath:
        return

    try:
        with PdfPages(filepath) as pdf:
            # ── Page 1: 표지 + 검색 개요 ──
            fig1 = plt.figure(figsize=(8.5, 11))
            fig1.patch.set_facecolor("white")

            fig1.text(0.5, 0.85, "게시판 검색기 — 통계 리포트", ha="center", fontsize=20, fontweight="bold")
            fig1.text(0.5, 0.80, APP_VERSION, ha="center", fontsize=12, color="gray")
            fig1.text(0.5, 0.76, datetime.now().strftime("%Y년 %m월 %d일 %H:%M 기준"), ha="center", fontsize=11, color="gray")

            summary_lines = [
                f"총 검색 시간: {stats.get('total_time_sec', 0):.1f}초",
                f"검색 토픽 수: {stats.get('total_topics', 0)}개",
                f"검색 대상: {stats.get('sites_searched', 0):,}개 사이트 / {stats.get('boards_searched', 0):,}개 게시판",
                f"수집 결과: {stats.get('total_raw_results', 0):,}건 수집 → {stats.get('total_final_results', 0):,}건 선별",
                f"스팸 제거: {stats.get('total_spam_filtered', 0):,}건",
                f"언어 필터: {stats.get('total_lang_filtered', 0):,}건",
                f"번역 처리: {stats.get('total_translated', 0):,}건",
            ]
            for i, line in enumerate(summary_lines):
                fig1.text(0.15, 0.65 - i * 0.04, line, fontsize=11)

            fig1.text(0.5, 0.08, "ⓒ 챠리 · 게시판 검색기", ha="center", fontsize=9, color="gray")
            pdf.savefig(fig1)
            plt.close(fig1)

            # ── Page 2: Buzz Score + 토픽별 비교 ──
            fig2 = plt.figure(figsize=(8.5, 11))
            fig2.patch.set_facecolor("white")

            # Buzz Score 상위 15
            buzz_ranking = stats.get("buzz_ranking", [])[:15]
            if buzz_ranking:
                ax_buzz = fig2.add_subplot(211)
                labels = [_truncate(item["title"], 30) for item in reversed(buzz_ranking)]
                scores = [item["buzz_score"] for item in reversed(buzz_ranking)]
                colors = [_CHART_COLORS[i % len(_CHART_COLORS)] for i in range(len(buzz_ranking))]
                colors.reverse()
                ax_buzz.barh(labels, scores, color=colors, height=0.6)
                ax_buzz.set_xlabel("Buzz Score")
                ax_buzz.set_title("Buzz Score 순위 (회자 점수 TOP 15)", fontsize=12, fontweight="bold")
                ax_buzz.tick_params(labelsize=7)

            # 토픽별 비교
            per_topic = stats.get("per_topic", {})
            if per_topic:
                ax_comp = fig2.add_subplot(212)
                topics = list(per_topic.keys())
                raw_c = [per_topic[t].get("raw_count", 0) for t in topics]
                final_c = [per_topic[t].get("final_count", 0) for t in topics]
                import numpy as np
                x = np.arange(len(topics))
                ax_comp.bar(x - 0.15, raw_c, 0.3, label="원본", color="#569cd6")
                ax_comp.bar(x + 0.15, final_c, 0.3, label="최종", color="#4ec9b0")
                ax_comp.set_xticks(x)
                ax_comp.set_xticklabels([_truncate(t, 10) for t in topics], rotation=30, ha="right", fontsize=7)
                ax_comp.set_title("토픽별 수집 건수 비교", fontsize=12, fontweight="bold")
                ax_comp.legend(fontsize=8)

            fig2.tight_layout(pad=3)
            pdf.savefig(fig2)
            plt.close(fig2)

            # ── Page 3: 필터 + 도메인 ──
            fig3 = plt.figure(figsize=(8.5, 11))
            fig3.patch.set_facecolor("white")

            filter_info = get_filter_breakdown(stats)
            ax_pie = fig3.add_subplot(211)
            sizes = [filter_info["final_results"], filter_info["spam_filtered"], filter_info["lang_filtered"]]
            labels_pie = ["최종 선별", "스팸 제거", "언어 필터"]
            colors_pie = ["#4ec9b0", "#f44747", "#569cd6"]
            non_zero_pie = [(s, l, c) for s, l, c in zip(sizes, labels_pie, colors_pie) if s > 0]
            if non_zero_pie:
                s, l, c = zip(*non_zero_pie)
                ax_pie.pie(s, labels=l, colors=c, autopct="%1.0f%%", startangle=90)
            ax_pie.set_title(f"필터링 효과 (필터율: {filter_info['filter_rate_pct']}%)", fontsize=12, fontweight="bold")

            domain_stats = aggregate_domain_stats(search_data)[:15]
            if domain_stats:
                ax_dom = fig3.add_subplot(212)
                d_labels = [d for d, _ in reversed(domain_stats)]
                d_counts = [c for _, c in reversed(domain_stats)]
                d_colors = [_CHART_COLORS[i % len(_CHART_COLORS)] for i in range(len(domain_stats))]
                d_colors.reverse()
                ax_dom.barh(d_labels, d_counts, color=d_colors, height=0.6)
                ax_dom.set_xlabel("인용 횟수")
                ax_dom.set_title("출처 도메인 TOP 15", fontsize=12, fontweight="bold")
                ax_dom.tick_params(labelsize=7)

            fig3.tight_layout(pad=3)
            pdf.savefig(fig3)
            plt.close(fig3)

            # ── Page 4: 토픽별 상세 테이블 ──
            table_rows = get_topic_table_data(stats)
            if table_rows:
                fig4 = plt.figure(figsize=(8.5, 11))
                fig4.patch.set_facecolor("white")
                fig4.text(0.5, 0.95, "토픽별 상세 통계", ha="center", fontsize=14, fontweight="bold")

                col_labels = ["토픽", "시간", "원본", "스팸", "언어", "번역", "최종", "상위 도메인"]
                cell_data = []
                for r in table_rows:
                    cell_data.append([
                        r["topic"], f"{r['time']:.1f}s", str(r["raw"]),
                        str(r["spam"]), str(r["lang"]), str(r["translated"]),
                        str(r["final"]), r["top_domain"][:20],
                    ])

                ax_table = fig4.add_subplot(111)
                ax_table.axis("off")
                table = ax_table.table(
                    cellText=cell_data, colLabels=col_labels,
                    cellLoc="center", loc="upper center",
                )
                table.auto_set_font_size(False)
                table.set_fontsize(8)
                table.scale(1, 1.5)

                for key, cell in table.get_celld().items():
                    if key[0] == 0:
                        cell.set_facecolor("#0078d4")
                        cell.set_text_props(color="white", fontweight="bold")
                    else:
                        cell.set_facecolor("#f8f8f8" if key[0] % 2 == 0 else "white")

                fig4.tight_layout()
                pdf.savefig(fig4)
                plt.close(fig4)

        messagebox.showinfo(
            "PDF 저장 완료",
            f"통계 리포트가 저장되었습니다.\n\n{filepath}",
            parent=parent_win,
        )
        log.info("통계 PDF 저장: %s", filepath)

    except Exception as e:
        log.error("PDF 저장 실패: %s", e)
        messagebox.showerror(
            "PDF 저장 실패",
            f"PDF를 저장하는 중 오류가 발생했습니다.\n\n{e}",
            parent=parent_win,
        )


# ═══════════════════════════════════════════════════
#  유틸리티
# ═══════════════════════════════════════════════════
def _truncate(text: str, max_len: int) -> str:
    """텍스트를 지정 길이로 자르고 말줄임표 추가"""
    if len(text) <= max_len:
        return text
    return text[:max_len - 1] + "…"
