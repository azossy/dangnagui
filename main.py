#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
게시판 검색기 — 임금님귀 v1.3.2
═══════════════════════════════════════════════════════
국내 1,000+ 사이트 / 60,000+ 게시판 실시간 분석
광고/스팸 3중 필터 · 암호화 DB · 통계 대시보드 · PDF 내보내기
DuckDuckGo 실시간 검색 · Microsoft Fluent 스타일 · USB 포터블

copyright by 챠리 (challychoi@me.com)
"""
from __future__ import annotations

import sys
import random
import threading
import webbrowser
from pathlib import Path
from datetime import datetime

if getattr(sys, "frozen", False):
    _BASE = Path(sys.executable).parent
    _INTERNAL = Path(getattr(sys, "_MEIPASS", _BASE))
else:
    _BASE = Path(__file__).parent
    _INTERNAL = _BASE
sys.path.insert(0, str(_INTERNAL))
sys.path.insert(0, str(_BASE))

from common import (
    BASE, APP_VERSION, COPYRIGHT, EMAIL, UPDATE_WARN_DAYS,
    APP_REGION, APP_FLAG,
    DEFAULT_TOPICS, DEFAULT_KEYWORD_COUNT, DEFAULT_HOURS,
    DEFAULT_REPORT_HEADER,
    log, date_seed, get_topic_icon, get_display_name,
    acquire_instance_lock, build_topic_config,
)

_app_settings = None
_settings_lock = threading.Lock()
_stop_event = threading.Event()

# v1.3.0: 최근 검색 데이터 보관 (통계 대시보드용)
_last_search_data: dict | None = None
_data_lock = threading.Lock()

PLACEHOLDER = "▶ 스타트를 눌러 리포트를 생성하세요"


# ═══════════════════════════════════════════════════
#  설정 접근 (스레드 안전)
# ═══════════════════════════════════════════════════
def get_settings():
    global _app_settings
    with _settings_lock:
        if _app_settings is None:
            try:
                from app_settings import load_settings
                _app_settings = load_settings()
            except Exception as e:
                log.error("Settings load fallback: %s", e)
                _app_settings = {
                    "topics": [
                        {"name": n, "enabled": True, "keyword_count": DEFAULT_KEYWORD_COUNT}
                        for n in DEFAULT_TOPICS
                    ],
                    "custom_topics": [],
                    "hours": DEFAULT_HOURS,
                }
        return _app_settings


def set_settings(s):
    global _app_settings
    with _settings_lock:
        _app_settings = s


def get_site_board_counts_display():
    try:
        from report_engine import get_site_board_counts
        return get_site_board_counts()
    except Exception as e:
        log.error("get_site_board_counts failed: %s", e)
        return 0, 0


def run_report(progress_callback=None, settings=None, stop_event=None):
    """
    리포트를 생성합니다.
    v1.3.0: Buzz Score 엔리치 + 통계 데이터 보관 추가
    """
    global _last_search_data
    try:
        from report_engine import search_topics_online, format_for_messenger
        from stats_engine import enrich_with_buzz_scores

        if settings is None:
            settings = get_settings()

        # DRY: common.build_topic_config()로 토픽 구성 추출
        topic_config = build_topic_config(settings)

        hours = settings.get("hours", DEFAULT_HOURS)

        # 실시간 웹 검색 (스팸 3중 필터 + 통계 수집)
        data = search_topics_online(
            topic_config, hours,
            region=APP_REGION,
            progress_callback=progress_callback,
            stop_event=stop_event,
            max_results_per_topic=settings.get("max_results_per_topic", 0),
        )

        if stop_event and stop_event.is_set():
            return None, "중지됨", False

        if not data.get("카테고리"):
            return None, "검색 결과가 없습니다.\n\n인터넷 연결을 확인하거나\npip install ddgs 를 실행하세요.", False

        # v1.3.0: Buzz Score 계산 추가 (통계 대시보드용)
        data = enrich_with_buzz_scores(data)

        # 최근 검색 데이터 보관 (통계 보기 버튼에서 사용)
        with _data_lock:
            _last_search_data = data

        # 보도자료 스타일 리포트 생성
        output, total = format_for_messenger(data, settings)

        clip_ok = False
        try:
            import pyperclip
            pyperclip.copy(output)
            clip_ok = True
        except ImportError:
            log.info("pyperclip not installed — clipboard copy skipped")
        except Exception as e:
            log.warning("Clipboard copy failed: %s", e)
        return output, total, clip_ok
    except Exception as e:
        log.error("Report generation failed: %s", e)
        return (
            None,
            "검색 중 오류가 발생했습니다. 로그 파일(logs/app.log)을 확인해 주세요.",
            False,
        )


# ═══════════════════════════════════════════════════
#  설정 창
# ═══════════════════════════════════════════════════
def _open_settings_window(parent, on_settings_saved=None):
    import json
    import tkinter as tk
    from tkinter import messagebox, ttk, filedialog
    try:
        from app_settings import (
            load_settings, save_settings,
            get_settings_for_export, normalize_imported_settings,
            find_related_sites_for_topic, find_related_sites_via_web_search,
            get_related_sites_for_default_topic,
        )
    except ImportError:
        load_settings = lambda: get_settings()
        save_settings = lambda _: True
        get_settings_for_export = lambda s: s
        normalize_imported_settings = lambda d: d
        find_related_sites_for_topic = lambda _: []
        find_related_sites_via_web_search = lambda _: []
        get_related_sites_for_default_topic = lambda _: []

    try:
        from report_engine import (
            get_per_topic_counts, get_site_board_counts,
            check_sample_urls, count_unique_domains,
        )
    except ImportError:
        get_per_topic_counts = lambda **kw: {}
        get_site_board_counts = lambda: (0, 0)
        check_sample_urls = lambda **kw: -1
        count_unique_domains = lambda _: (0, 0)

    # ── 색상·글꼴 (메인/통계 창과 동일 고급 다크 톤) ──
    C = {
        "bg": "#16161a", "sf": "#1c1c21", "sf2": "#232328", "inp": "#27272a",
        "bdr": "#3f3f46", "bdr_a": "#0ea5e9",
        "tx": "#e4e4e7", "tx2": "#a1a1aa", "tx3": "#71717a",
        "ac": "#0ea5e9", "ac_h": "#0384c7",
        "sel": "#0c4a6e", "sel_fg": "#7dd3fc",
        "red": "#ef4444", "green": "#059669",
        "accent_line": "#0ea5e9",
    }
    F = {
        "h1": ("Segoe UI Semibold", 12), "h2": ("Segoe UI Semibold", 10),
        "body": ("Segoe UI", 10), "sm": ("Segoe UI", 9), "xs": ("Segoe UI", 8),
        "btn": ("Segoe UI", 10, "bold"), "icon": ("Segoe UI Emoji", 12),
    }

    # ── 윈도우 ──
    win = tk.Toplevel(parent)
    win.title("설정 — 게시판 검색기")
    win.geometry("940x580")
    win.minsize(740, 460)
    win.configure(bg=C["bg"])
    win.transient(parent)

    # ── 설정 로드 ──
    settings = load_settings()
    settings.setdefault("topics", [])
    settings.setdefault("custom_topics", [])
    if not settings["topics"] and not settings["custom_topics"]:
        settings["topics"] = [
            {"name": n, "enabled": True, "keyword_count": DEFAULT_KEYWORD_COUNT}
            for n in DEFAULT_TOPICS
        ]

    all_topics = [
        t for t in settings["topics"] + settings["custom_topics"]
        if isinstance(t, dict) and t.get("name")
    ]
    if not all_topics:
        settings["topics"] = [
            {"name": n, "enabled": True, "keyword_count": DEFAULT_KEYWORD_COUNT}
            for n in DEFAULT_TOPICS
        ]
        all_topics = list(settings["topics"])

    topic_order = settings.get("topic_order") or []
    if topic_order:
        by_name = {t["name"]: t for t in all_topics}
        ordered = [by_name.pop(n) for n in topic_order if n in by_name]
        ordered.extend(by_name.values())
        all_topics = ordered

    selected = {t["name"]: t.get("enabled", True) for t in all_topics}
    ordered_names = [t["name"] for t in all_topics]
    spin_vars: dict[str, tk.StringVar] = {}
    topic_frames: dict[str, tk.Frame] = {}
    drag = {"src": None, "y0": 0, "active": False}
    dirty = [False]
    _mw_active = [True]

    # ── 유틸리티 ──
    def _get_topic(name):
        for t in settings["topics"] + settings["custom_topics"]:
            if t.get("name") == name:
                return t
        return None

    def _lighter(hex_c):
        r, g, b = int(hex_c[1:3], 16), int(hex_c[3:5], 16), int(hex_c[5:7], 16)
        return f"#{min(r + 30, 255):02x}{min(g + 30, 255):02x}{min(b + 30, 255):02x}"

    def _mark_dirty():
        dirty[0] = True

    def _sync_spin_to_settings():
        for t in settings["topics"] + settings["custom_topics"]:
            n = t.get("name")
            sv = spin_vars.get(n)
            if sv:
                try:
                    t["keyword_count"] = max(1, min(10, int(sv.get())))
                except (ValueError, TypeError):
                    pass

    def _toast(msg, color="green"):
        colors = {"green": C["green"], "red": C["red"], "blue": C["ac"]}
        bg = colors.get(color, C["green"])
        duration = 4000 if color == "red" else 2200
        tf = tk.Frame(win, bg=bg)
        tf.place(relx=0, y=0, relwidth=1.0)
        tk.Label(tf, text=msg, font=F["body"], fg="#fff", bg=bg, pady=6).pack()
        win.after(duration, lambda: tf.place_forget() if tf.winfo_exists() else None)

    def _refresh_right():
        ne = sum(1 for n in ordered_names if selected.get(n, True))
        all_related: list = []
        has_data = False
        for n in ordered_names:
            if not selected.get(n, True):
                continue
            t = _get_topic(n)
            if t:
                rs = t.get("related_sites") or []
                if rs:
                    has_data = True
                    all_related.extend(rs)
        if has_data:
            gs, gb = count_unique_domains(all_related)
        else:
            gs, gb = get_site_board_counts()
        right_var.set(f"{ne}개 토픽 · {gs:,}개 사이트\n{gb:,}개 게시판")

    # ── 설정 저장 ──
    def _sync_header_to_settings():
        try:
            hdr_text = header_text.get("1.0", "end-1c").strip()
            settings["report_header"] = hdr_text if hdr_text else DEFAULT_REPORT_HEADER
        except Exception:
            pass

    def do_save(*_):
        try:
            settings["hours"] = max(30, min(100, int(hours_var.get())))
        except (ValueError, TypeError):
            settings["hours"] = DEFAULT_HOURS
        try:
            mrp = int(max_results_var.get() or 0)
            settings["max_results_per_topic"] = mrp if mrp in (0, 50, 100, 200) else 0
        except (ValueError, TypeError):
            settings["max_results_per_topic"] = 0
        settings["pdf_default_dir"] = (pdf_default_dir_var.get() or "").strip()
        _sync_spin_to_settings()
        _sync_header_to_settings()
        for t in settings["topics"] + settings["custom_topics"]:
            n = t.get("name")
            if n:
                t["enabled"] = selected.get(n, True)
        settings["topic_order"] = list(ordered_names)
        ok = save_settings(settings)
        set_settings(settings)
        dirty[0] = False
        if on_settings_saved:
            on_settings_saved()
        if ok:
            _toast("✓ 설정이 저장되었습니다")
        else:
            _toast("✗ 저장에 실패했습니다", "red")

    def _close_win(*_):
        # 저장 여부 확인: dirty 플래그가 True일 때만 저장 확인 메시지 표시 (A-2 검증)
        if dirty[0]:
            ans = messagebox.askyesnocancel(
                "설정 변경",
                "변경사항이 저장되지 않았습니다.\n\n저장하시겠습니까?",
                parent=win,
            )
            if ans is None:
                return
            if ans:
                try:
                    settings["hours"] = max(30, min(100, int(hours_var.get())))
                except (ValueError, TypeError):
                    settings["hours"] = DEFAULT_HOURS
                try:
                    mrp = int(max_results_var.get() or 0)
                    settings["max_results_per_topic"] = mrp if mrp in (0, 50, 100, 200) else 0
                except (ValueError, TypeError):
                    settings["max_results_per_topic"] = 0
                settings["pdf_default_dir"] = (pdf_default_dir_var.get() or "").strip()
                _sync_spin_to_settings()
                _sync_header_to_settings()
                for t in settings["topics"] + settings["custom_topics"]:
                    n = t.get("name")
                    if n:
                        t["enabled"] = selected.get(n, True)
                settings["topic_order"] = list(ordered_names)
                save_settings(settings)
                set_settings(settings)
                if on_settings_saved:
                    on_settings_saved()
        _mw_active[0] = False
        try:
            # REQ-005: 특정 바인딩만 해제하여 메인 창 스크롤에 영향 없도록
            win.unbind("<MouseWheel>", _mw_bind_id)
        except Exception:
            pass
        win.destroy()

    # ══ 우측 패널 (고급 카드 스타일) ══
    right = tk.Frame(win, bg=C["sf"], width=240)
    right.pack(side=tk.RIGHT, fill=tk.Y)
    right.pack_propagate(False)
    tk.Frame(right, bg=C["bdr"], width=1).pack(side=tk.LEFT, fill=tk.Y)
    rp = tk.Frame(right, bg=C["sf"], padx=16, pady=14)
    rp.pack(fill=tk.BOTH, expand=True)

    # 우측 상단 액센트 바 + 제목
    rp_header = tk.Frame(rp, bg=C["sf"])
    rp_header.pack(fill=tk.X, pady=(0, 8))
    _bar = tk.Frame(rp_header, width=3, bg=C["accent_line"], height=16)
    _bar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
    _bar.pack_propagate(False)
    g_s, g_b = get_site_board_counts()
    n_en = sum(1 for n in ordered_names if selected.get(n, True))
    right_var = tk.StringVar(value=f"{n_en}개 토픽 · {g_s:,}개 사이트\n{g_b:,}개 게시판")
    tk.Label(rp_header, text="검색 대상", font=F["h1"], fg=C["tx"], bg=C["sf"]).pack(anchor=tk.W)
    tk.Label(rp, textvariable=right_var, font=F["body"], fg=C["tx"], bg=C["sf"], justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 8))

    vr = settings.get("valid_rate", -1)
    valid_var = tk.StringVar(value=f"유효 접속율 {vr}%" if vr >= 0 else "유효 접속율 미확인")
    tk.Label(rp, textvariable=valid_var, font=F["sm"], fg=C["ac"] if vr >= 0 else C["tx3"], bg=C["sf"]).pack(anchor=tk.W, pady=(0, 2))

    last_d = settings.get("last_track_date", "")
    last_var = tk.StringVar(value=f"마지막 갱신: {last_d}" if last_d else "갱신 기록 없음")
    tk.Label(rp, textvariable=last_var, font=F["xs"], fg=C["tx3"], bg=C["sf"]).pack(anchor=tk.W, pady=(0, 8))

    if last_d:
        try:
            days = (datetime.now() - datetime.fromisoformat(last_d)).days
            if days >= UPDATE_WARN_DAYS:
                tk.Label(rp, text=f"⚠ {days}일 경과 — 갱신 권장", font=F["xs"], fg="#f59e0b", bg=C["sf"]).pack(anchor=tk.W, pady=(0, 4))
        except Exception:
            pass

    tk.Frame(rp, bg=C["bdr"], height=1).pack(fill=tk.X, pady=(0, 8))
    tk.Label(rp, text="토픽별 연관 사이트·게시판을\n웹검색으로 최신 갱신", font=F["xs"], fg=C["tx2"], bg=C["sf"], justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 6))

    # ── 사이트 갱신 ──
    def _run_track(mode):
        """
        v1.3.0: 3계층 사이트 자동 탐색 실행
        Layer 1(시드DB) → Layer 2(DC API + 파싱) → Layer 3(DDG + 네이버카페)
        결과를 암호화 파일 DB에 자동 저장
        """
        pw = tk.Toplevel(win)
        pw.title("사이트 DB 갱신 (3계층 탐색)")
        pw.geometry("580x440")
        pw.configure(bg=C["sf"])
        pw.transient(win)
        pw.grab_set()
        pw.resizable(False, False)
        title_txt = (
            "전체 초기화 — 시드DB부터 3계층 재구축" if mode == "full"
            else "추가 갱신 — 기존 DB + 신규 탐색 확장"
        )
        tk.Label(pw, text=title_txt, font=F["h1"], fg=C["tx"], bg=C["sf"]).pack(anchor=tk.W, padx=20, pady=(12, 6))

        # 진행률 바
        progress_var = tk.DoubleVar(value=0)
        progress_label = tk.StringVar(value="준비 중...")
        tk.Label(pw, textvariable=progress_label, font=F["sm"], fg=C["ac"], bg=C["sf"]).pack(anchor=tk.W, padx=20, pady=(0, 2))
        pbar = ttk.Progressbar(pw, variable=progress_var, maximum=100)
        pbar.pack(fill=tk.X, padx=20, pady=(0, 6))

        log_text = tk.Text(pw, font=F["sm"], bg=C["bg"], fg=C["tx"], relief=tk.FLAT, padx=12, pady=8, height=14, state=tk.DISABLED, wrap=tk.WORD)
        log_text.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 8))
        for tag, clr in [("ok", "#4ec9b0"), ("info", C["ac"]), ("warn", "#ff8c00"), ("bold", "#ffffff")]:
            kw = {"foreground": clr}
            if tag == "bold":
                kw["font"] = ("Segoe UI", 9, "bold")
            log_text.tag_configure(tag, **kw)
        pw.update_idletasks()

        def _log(msg, tag=None):
            def _w():
                if not log_text.winfo_exists():
                    return
                log_text.configure(state=tk.NORMAL)
                log_text.insert(tk.END, msg + "\n", tag if tag else ())
                log_text.see(tk.END)
                log_text.configure(state=tk.DISABLED)
            if pw.winfo_exists():
                pw.after(0, _w)

        track_stop = threading.Event()

        def _cancel_track():
            track_stop.set()
            _log("⚠ 사용자가 중단을 요청했습니다.", "warn")

        cancel_btn = tk.Button(
            pw, text="중단", font=F["btn"], fg="#fff", bg="#d13438",
            activebackground="#e04b4f", relief=tk.FLAT, cursor="hand2",
            command=_cancel_track, pady=5,
        )
        cancel_btn.pack(pady=(0, 8))

        def work():
            try:
                from app_settings import run_site_discovery

                _log("═══ v1.3.0 3계층 사이트 자동 탐색 시작 ═══", "bold")
                _log(f"모드: {'전체 초기화' if mode == 'full' else '추가 갱신'}", "info")
                _log("")

                # 진행률 콜백
                def _progress(current, total, message):
                    if pw.winfo_exists():
                        pct = (current / max(total, 1)) * 100
                        pw.after(0, lambda: progress_var.set(pct))
                        pw.after(0, lambda: progress_label.set(f"[{current}/{total}] {message}"))
                    _log(f"  [{current}/{total}] {message}", "info")

                # 3계층 탐색 실행
                result = run_site_discovery(
                    settings=settings,
                    progress_callback=_progress,
                    stop_event=track_stop,
                )

                if "error" in result:
                    _log(f"오류: {result['error']}", "warn")
                else:
                    _log("")
                    _log("━━━ 사이트 탐색 결과 요약 ━━━", "bold")
                    _log(f"  총 사이트: {result.get('total_sites', 0):,}개", "ok")
                    _log(f"  총 게시판: {result.get('total_boards', 0):,}개", "ok")
                    _log(f"  DC갤러리: {result.get('dc_gallery_count', 0):,}개", "ok")
                    _log(f"  네이버카페: {result.get('naver_cafe_count', 0):,}개", "ok")
                    _log(f"  DDG 신규 발견: {result.get('discovered_count', 0):,}개", "ok")
                    _log("")

                # 레거시 호환: 기존 방식 사이트 갱신도 병행
                _log("레거시 호환 갱신 진행 중...", "info")
                all_t = settings["topics"] + settings["custom_topics"]
                for idx, t in enumerate(all_t):
                    name = t.get("name")
                    if not name:
                        continue
                    if track_stop.is_set():
                        break
                    if name in DEFAULT_TOPICS:
                        new_sites = get_related_sites_for_default_topic(name)
                    else:
                        new_sites = find_related_sites_via_web_search(name) or find_related_sites_for_topic(name)
                    if mode == "full":
                        t["related_sites"] = new_sites
                    elif mode == "add":
                        existing = t.get("related_sites") or []
                        existing_urls = {s.get("url", "") for cat in existing for s in cat.get("sites") or []}
                        merged = list(existing)
                        for cat in new_sites:
                            new_entries = [s for s in (cat.get("sites") or []) if s.get("url", "") not in existing_urls]
                            if new_entries:
                                merged.append({"category": cat.get("category", "추가"), "sites": new_entries})
                        t["related_sites"] = merged

                # 접속율 검사
                _log("접속율 검사 중...", "info")
                rate = check_sample_urls(sample_size=20, timeout=3)
                today = datetime.now().strftime("%Y-%m-%d")
                settings["last_track_date"] = today
                settings["valid_rate"] = rate
                if rate >= 0:
                    _log(f"  유효 접속율: {rate}%", "ok")

                save_settings(settings)
                set_settings(settings)
                _log("")
                _log("━━ 사이트 DB 갱신 완료 · 설정 자동 저장 ━━", "bold")

                def done():
                    if not pw.winfo_exists():
                        return
                    valid_var.set(f"유효 접속율 {rate}%" if rate >= 0 else "유효 접속율 측정 실패")
                    last_var.set(f"마지막 갱신: {today}")
                    cancel_btn.destroy()
                    ok_btn = tk.Button(
                        pw, text="  확인  ", font=F["btn"], fg="#fff", bg=C["ac"],
                        activebackground=C["ac_h"], relief=tk.FLAT, cursor="hand2",
                        padx=24, pady=5,
                    )
                    ok_btn.pack(pady=(4, 14))
                    ok_btn.bind("<Enter>", lambda e: ok_btn.config(bg=C["ac_h"]))
                    ok_btn.bind("<Leave>", lambda e: ok_btn.config(bg=C["ac"]))

                    def _close_track():
                        pw.destroy()
                        dirty[0] = False
                        _rebuild_topic_list()
                        _refresh_right()
                        if on_settings_saved:
                            on_settings_saved()
                        _toast("✓ 사이트 DB 갱신 완료 · 3계층 탐색 + 암호화 저장")

                    ok_btn.config(command=_close_track)
                win.after(0, done)

            except Exception as e:
                _log(f"오류 발생: {e}", "warn")
                log.error("사이트 갱신 오류: %s", e)

        threading.Thread(target=work, daemon=True).start()

    def on_track():
        cnt = len(ordered_names)
        dlg = tk.Toplevel(win)
        dlg.title("사이트 갱신 방법 선택")
        dlg.configure(bg=C["sf"])
        dlg.transient(win)
        dlg.grab_set()
        dlg.resizable(False, False)

        tk.Label(dlg, text="사이트·게시판 갱신", font=F["h1"], fg=C["tx"], bg=C["sf"]).pack(anchor=tk.W, padx=20, pady=(14, 2))
        tk.Label(
            dlg, text=f"{cnt}개 토픽의 국내 주요 사이트·게시판 목록을 온라인에서 검색합니다.",
            font=F["xs"], fg=C["tx2"], bg=C["sf"], wraplength=380, justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=20, pady=(0, 10))

        bf = tk.Frame(dlg, bg=C["sf"])
        bf.pack(fill=tk.X, padx=20, pady=(0, 14))

        def _mkbtn(prnt, text, desc, color, cmd):
            f = tk.Frame(prnt, bg=C["sf"])
            f.pack(fill=tk.X, pady=2)
            b = tk.Button(
                f, text=text, font=F["btn"], fg="#fff", bg=color,
                activebackground=_lighter(color), relief=tk.FLAT, cursor="hand2",
                anchor=tk.W, padx=12, pady=5, command=cmd,
            )
            b.pack(fill=tk.X)
            b.bind("<Enter>", lambda e, b=b, c=color: b.config(bg=_lighter(c)))
            b.bind("<Leave>", lambda e, b=b, c=color: b.config(bg=c))
            tk.Label(f, text=desc, font=F["xs"], fg=C["tx3"], bg=C["sf"]).pack(anchor=tk.W, padx=4, pady=(1, 0))

        def _full():
            dlg.destroy()
            if messagebox.askyesno(
                "전체 초기화",
                "⚠ 기존 사이트·게시판 정보를 모두 삭제하고\n"
                "처음부터 새로 구축합니다.\n\n"
                "시간이 상당히 오래 걸릴 수 있습니다.\n\n진행할까요?",
                parent=win,
            ):
                _run_track("full")

        def _add():
            dlg.destroy()
            _run_track("add")

        _mkbtn(bf, "🗑  전체 초기화 후 새로 구축", "기존 정보 삭제 → 전체 재검색 (시간 오래 걸림)", "#8b3a3a", _full)
        _mkbtn(bf, "➕  기존 유지 + 새 사이트만 추가", "기존 목록 보존, 없는 사이트·게시판만 추가", C["ac"], _add)
        tk.Frame(bf, bg=C["bdr"], height=1).pack(fill=tk.X, pady=(8, 6))
        cb = tk.Button(
            bf, text="취소", font=F["body"], fg=C["tx2"], bg=C["sf2"],
            activebackground=C["bdr"], relief=tk.FLAT, cursor="hand2",
            padx=12, pady=5, command=dlg.destroy,
        )
        cb.pack(fill=tk.X)
        cb.bind("<Enter>", lambda e: cb.config(bg=C["bdr"]))
        cb.bind("<Leave>", lambda e: cb.config(bg=C["sf2"]))
        dlg.update_idletasks()
        h = max(bf.winfo_reqheight() + 90, 280)
        dlg.geometry(f"420x{h}")

    tb = tk.Button(rp, text="  🔄 사이트 갱신  ", font=F["btn"], fg="#fff", bg=C["ac"], activebackground=C["ac_h"], relief=tk.FLAT, cursor="hand2", command=on_track, pady=6, padx=8)
    tb.pack(fill=tk.X)
    tb.bind("<Enter>", lambda e: tb.config(bg=C["ac_h"]))
    tb.bind("<Leave>", lambda e: tb.config(bg=C["ac"]))

    # 추가개발-2: 설정 내보내기 / 설정 가져오기
    def _do_export():
        try:
            settings["hours"] = max(30, min(100, int(hours_var.get())))
        except (ValueError, TypeError):
            settings["hours"] = DEFAULT_HOURS
        _sync_header_to_settings()
        for t in settings["topics"] + settings["custom_topics"]:
            n = t.get("name")
            if n:
                t["enabled"] = selected.get(n, True)
        settings["topic_order"] = list(ordered_names)
        data = get_settings_for_export(settings)
        path = filedialog.asksaveasfilename(
            parent=win, title="설정 내보내기",
            defaultextension=".json", filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")],
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                _toast("✓ 설정을 저장했습니다")
            except Exception as e:
                log.error("설정 내보내기 실패: %s", e)
                messagebox.showerror("내보내기 실패", str(e), parent=win)

    def _do_import():
        path = filedialog.askopenfilename(
            parent=win, title="설정 가져오기",
            filetypes=[("JSON 파일", "*.json"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            log.error("설정 가져오기 로드 실패: %s", e)
            messagebox.showerror("가져오기 실패", f"파일을 읽을 수 없습니다.\n{e}", parent=win)
            return
        if not messagebox.askyesno("설정 가져오기", "현재 설정을 덮어쓸까요?", parent=win):
            return
        norm = normalize_imported_settings(data)
        settings.clear()
        settings.update(norm)
        all_t = norm.get("topics", []) + norm.get("custom_topics", [])
        topic_order = norm.get("topic_order") or []
        by_name = {t["name"]: t for t in all_t}
        ordered_list = [by_name.pop(n) for n in topic_order if n in by_name]
        ordered_list.extend(by_name.values())
        ordered_names.clear()
        ordered_names.extend([t["name"] for t in ordered_list])
        selected.clear()
        selected.update({t["name"]: t.get("enabled", True) for t in ordered_list})
        hours_var.set(str(settings.get("hours", DEFAULT_HOURS)))
        max_results_var.set(str(settings.get("max_results_per_topic", 0)))
        pdf_default_dir_var.set(settings.get("pdf_default_dir") or "")
        header_text.delete("1.0", tk.END)
        header_text.insert("1.0", settings.get("report_header") or DEFAULT_REPORT_HEADER)
        _rebuild_topic_list()
        _mark_dirty()
        _toast("✓ 설정을 가져왔습니다. 저장 버튼으로 적용하세요.")

    exp_btn = tk.Button(rp, text="  📤 설정 내보내기  ", font=F["body"], fg=C["tx2"], bg=C["sf2"], activeforeground=C["ac"], relief=tk.FLAT, cursor="hand2", command=_do_export, pady=4, padx=8)
    exp_btn.pack(fill=tk.X, pady=(4, 2))
    exp_btn.bind("<Enter>", lambda e: exp_btn.config(bg=C["bdr"]))
    exp_btn.bind("<Leave>", lambda e: exp_btn.config(bg=C["sf2"]))
    imp_btn = tk.Button(rp, text="  📥 설정 가져오기  ", font=F["body"], fg=C["tx2"], bg=C["sf2"], activeforeground=C["ac"], relief=tk.FLAT, cursor="hand2", command=_do_import, pady=4, padx=8)
    imp_btn.pack(fill=tk.X, pady=(0, 4))
    imp_btn.bind("<Enter>", lambda e: imp_btn.config(bg=C["bdr"]))
    imp_btn.bind("<Leave>", lambda e: imp_btn.config(bg=C["sf2"]))

    spacer = tk.Frame(rp, bg=C["sf"])
    spacer.pack(fill=tk.BOTH, expand=True)

    tk.Frame(rp, bg=C["bdr"], height=1).pack(fill=tk.X, pady=(10, 8))
    sb = tk.Button(
        rp, text="  💾 설정 저장 (Ctrl+S)  ", font=("Segoe UI Semibold", 11),
        fg="#fff", bg=C["green"], activebackground="#047857",
        relief=tk.FLAT, cursor="hand2", command=do_save, pady=8, padx=12,
    )
    sb.pack(fill=tk.X, pady=(0, 6))
    sb.bind("<Enter>", lambda e: sb.config(bg="#047857"))
    sb.bind("<Leave>", lambda e: sb.config(bg=C["green"]))

    xb = tk.Button(
        rp, text="닫기 (Esc)", font=F["body"], fg=C["tx2"], bg=C["sf2"],
        activebackground=C["bdr"], relief=tk.FLAT, cursor="hand2",
        command=_close_win, pady=6,
    )
    xb.pack(fill=tk.X)
    xb.bind("<Enter>", lambda e: xb.config(bg=C["bdr"]))
    xb.bind("<Leave>", lambda e: xb.config(bg=C["sf2"]))

    # ══ 왼쪽 스크롤 영역 ══
    left = tk.Frame(win, bg=C["bg"])
    left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    canvas = tk.Canvas(left, bg=C["bg"], highlightthickness=0)
    vsb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=canvas.yview)
    sf = tk.Frame(canvas, bg=C["bg"])
    sf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=sf, anchor=tk.NW)
    canvas.configure(yscrollcommand=vsb.set)
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas.find_all()[0], width=e.width))

    def _mw(e):
        if not _mw_active[0]:
            return
        if isinstance(e.widget, (tk.Spinbox, tk.Entry)):
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
    win.protocol("WM_DELETE_WINDOW", _close_win)
    win.bind("<Escape>", _close_win)
    win.bind("<Control-s>", do_save)
    vsb.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    pd = 18

    def _settings_section_title(parent_frame, title):
        """설정 창 섹션 제목 (왼쪽 액센트 바 + 텍스트)"""
        f = tk.Frame(parent_frame, bg=C["sf"])
        f.pack(fill=tk.X, pady=(0, 4))
        bar = tk.Frame(f, width=3, bg=C["accent_line"], height=14)
        bar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        bar.pack_propagate(False)
        tk.Label(f, text=title, font=F["h2"], fg=C["tx"], bg=C["sf"]).pack(anchor=tk.W)
        return f

    # ── 섹션 1: 검색 기준 시간 ──
    s1 = tk.Frame(sf, bg=C["sf"], padx=18, pady=12)
    s1.pack(fill=tk.X, padx=pd, pady=(pd, 8))
    _settings_section_title(s1, "검색 기준 시간")
    r1 = tk.Frame(s1, bg=C["sf"])
    r1.pack(fill=tk.X)
    hours_var = tk.StringVar(value=str(max(30, min(100, settings.get("hours", DEFAULT_HOURS)))))

    def _h_adj(delta):
        try:
            v = int(hours_var.get() or DEFAULT_HOURS)
            hours_var.set(str(max(30, min(100, v + delta))))
            _mark_dirty()
        except (ValueError, TypeError):
            pass

    tk.Button(r1, text="◀", font=("Segoe UI", 9), fg=C["tx2"], bg=C["sf"], activeforeground=C["ac"], relief=tk.FLAT, cursor="hand2", command=lambda: _h_adj(-1), padx=6, pady=2).pack(side=tk.LEFT)
    tk.Label(r1, textvariable=hours_var, font=("Segoe UI", 13, "bold"), fg=C["ac"], bg=C["sf"], width=4, anchor=tk.CENTER).pack(side=tk.LEFT)
    tk.Button(r1, text="▶", font=("Segoe UI", 9), fg=C["tx2"], bg=C["sf"], activeforeground=C["ac"], relief=tk.FLAT, cursor="hand2", command=lambda: _h_adj(1), padx=6, pady=2).pack(side=tk.LEFT)
    tk.Label(r1, text="시간 전", font=F["body"], fg=C["tx2"], bg=C["sf"]).pack(side=tk.LEFT, padx=(4, 0))
    # 추가개발-1: 검색 기준 시간 프리셋 (30/48/72/100)
    r1b = tk.Frame(s1, bg=C["sf"])
    r1b.pack(fill=tk.X, pady=(6, 0))
    for h in (30, 48, 72, 100):
        def _set_h(val=h):
            hours_var.set(str(val))
            _mark_dirty()
        b = tk.Button(r1b, text=f"{h}h", font=("Segoe UI", 9), fg=C["tx2"], bg=C["inp"], activeforeground=C["ac"], relief=tk.FLAT, cursor="hand2", command=_set_h, padx=8, pady=3)
        b.pack(side=tk.LEFT, padx=(0, 4))
        b.bind("<Enter>", lambda e, btn=b: btn.config(bg=C["bdr"], fg=C["ac"]))
        b.bind("<Leave>", lambda e, btn=b: btn.config(bg=C["inp"], fg=C["tx2"]))
    tk.Label(s1, text="현재 시간 기준, 설정 시간 이전까지의 게시판 글 대상 (30~100)", font=F["xs"], fg=C["tx3"], bg=C["sf"]).pack(anchor=tk.W, pady=(4, 0))
    # 추가개발-3: 토픽당 최대 검색 결과 상한
    r1c = tk.Frame(s1, bg=C["sf"])
    r1c.pack(fill=tk.X, pady=(8, 0))
    tk.Label(r1c, text="토픽당 최대 결과:", font=F["xs"], fg=C["tx2"], bg=C["sf"]).pack(side=tk.LEFT, padx=(0, 8))
    max_results_var = tk.StringVar(value=str(settings.get("max_results_per_topic", 0)))
    for val, lbl in [(0, "제한없음"), (50, "50"), (100, "100"), (200, "200")]:
        def _set_max(v=val):
            max_results_var.set(str(v))
            _mark_dirty()
        b = tk.Button(r1c, text=lbl, font=("Segoe UI", 9), fg=C["tx2"], bg=C["inp"], activeforeground=C["ac"], relief=tk.FLAT, cursor="hand2", command=_set_max, padx=6, pady=2)
        b.pack(side=tk.LEFT, padx=(0, 2))
        b.bind("<Enter>", lambda e, btn=b: btn.config(bg=C["bdr"], fg=C["ac"]))
        b.bind("<Leave>", lambda e, btn=b: btn.config(bg=C["inp"], fg=C["tx2"]))

    # 추가개발-5: PDF 기본 저장 폴더 (통계)
    r1d = tk.Frame(s1, bg=C["sf"])
    r1d.pack(fill=tk.X, pady=(8, 0))
    tk.Label(r1d, text="PDF 기본 폴더 (통계):", font=F["xs"], fg=C["tx2"], bg=C["sf"]).pack(side=tk.LEFT, padx=(0, 8))
    pdf_default_dir_var = tk.StringVar(value=settings.get("pdf_default_dir") or "")
    pdf_dir_entry = tk.Entry(r1d, textvariable=pdf_default_dir_var, font=("Segoe UI", 9), bg=C["inp"], fg=C["tx"], width=28, relief=tk.FLAT)
    pdf_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, ipadx=6, padx=(0, 4))
    def _browse_pdf_dir():
        d = filedialog.askdirectory(parent=win, title="PDF 저장 기본 폴더 선택")
        if d:
            pdf_default_dir_var.set(d)
            _mark_dirty()
    tk.Button(r1d, text="찾아보기", font=F["xs"], fg=C["ac"], bg=C["sf"], relief=tk.FLAT, cursor="hand2", command=_browse_pdf_dir).pack(side=tk.LEFT)
    pdf_dir_entry.bind("<Key>", lambda e: _mark_dirty())

    # U-4: 섹션 구분선
    tk.Frame(sf, height=1, bg=C["bdr"]).pack(fill=tk.X, padx=pd, pady=(8, 0))

    # ── 섹션 1.5: 리포트 헤더 편집 ──
    s15 = tk.Frame(sf, bg=C["sf"], padx=18, pady=12)
    s15.pack(fill=tk.X, padx=pd, pady=(0, 8))
    _settings_section_title(s15, "리포트 헤더 편집")
    tk.Label(s15, text="리포트 상단에 표시되는 헤더를 자유롭게 편집할 수 있습니다", font=F["xs"], fg=C["tx2"], bg=C["sf"]).pack(anchor=tk.W, pady=(2, 6))
    header_text = tk.Text(
        s15, font=("Consolas", 10), bg=C["inp"], fg=C["tx"],
        insertbackground=C["tx"], relief=tk.FLAT, height=3, wrap=tk.NONE,
        padx=8, pady=6,
    )
    header_text.pack(fill=tk.X, ipady=2)
    _saved_header = settings.get("report_header") or DEFAULT_REPORT_HEADER
    header_text.insert("1.0", _saved_header)
    header_text.bind("<Key>", lambda e: _mark_dirty())
    hdr_hint = tk.Frame(s15, bg=C["sf"])
    hdr_hint.pack(fill=tk.X, pady=(4, 0))
    tk.Label(hdr_hint, text="기본값으로 되돌리려면:", font=F["xs"], fg=C["tx3"], bg=C["sf"]).pack(side=tk.LEFT)

    def _reset_header():
        header_text.delete("1.0", tk.END)
        header_text.insert("1.0", DEFAULT_REPORT_HEADER)
        _mark_dirty()

    rst_btn = tk.Button(
        hdr_hint, text="초기화", font=F["xs"], fg=C["ac"], bg=C["sf"],
        activeforeground=C["ac_h"], relief=tk.FLAT, cursor="hand2",
        command=_reset_header, padx=4,
    )
    rst_btn.pack(side=tk.LEFT, padx=(4, 0))
    rst_btn.bind("<Enter>", lambda e: rst_btn.config(fg=C["ac_h"]))
    rst_btn.bind("<Leave>", lambda e: rst_btn.config(fg=C["ac"]))

    # U-4: 섹션 구분선
    tk.Frame(sf, height=1, bg=C["bdr"]).pack(fill=tk.X, padx=pd, pady=(8, 0))

    # ── 섹션 2: 토픽 추가 ──
    s2 = tk.Frame(sf, bg=C["sf"], padx=18, pady=12, highlightbackground=C["bdr_a"], highlightthickness=1)
    s2.pack(fill=tk.X, padx=pd, pady=(0, 8))
    _settings_section_title(s2, "새 토픽 추가")
    tk.Label(s2, text="웹검색으로 관련 사이트·게시판 자동 탐색 후 등록", font=F["xs"], fg=C["tx2"], bg=C["sf"]).pack(anchor=tk.W, pady=(2, 6))
    ar = tk.Frame(s2, bg=C["sf"])
    ar.pack(fill=tk.X)
    add_var = tk.StringVar()
    ae = tk.Entry(ar, textvariable=add_var, font=("Segoe UI", 10), bg=C["inp"], fg=C["tx"], insertbackground=C["tx"], relief=tk.FLAT)
    ae.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, ipadx=10, padx=(0, 8))
    abtn = tk.Button(ar, text="+ 추가", font=F["btn"], fg="#fff", bg=C["ac"], activebackground=C["ac_h"], relief=tk.FLAT, cursor="hand2", padx=16, pady=4)
    abtn.pack(side=tk.LEFT)
    abtn.bind("<Enter>", lambda e: abtn.config(bg=C["ac_h"]))
    abtn.bind("<Leave>", lambda e: abtn.config(bg=C["ac"]))

    def add_topic():
        name = add_var.get().strip()
        if not name:
            return
        all_names = {t.get("name") for t in settings["topics"] + settings["custom_topics"]}
        if name in all_names:
            _toast("이미 등록된 토픽입니다", "red")
            return
        if not messagebox.askyesno(
            "토픽 추가",
            f"'{name}' 토픽 추가를 위해 관련 사이트와\n"
            "게시판을 모두 검색합니다.\n시간이 걸릴 수 있습니다.",
            parent=win,
        ):
            return
        ww = tk.Toplevel(win)
        ww.title("검색 중")
        ww.geometry("360x80")
        ww.configure(bg=C["sf"])
        ww.transient(win)
        ww.grab_set()
        ww.resizable(False, False)
        tk.Label(ww, text=f"'{name}' 연관 사이트 검색 중...", font=F["body"], fg=C["tx"], bg=C["sf"]).pack(pady=(24, 6))
        ww.update_idletasks()

        def _search():
            related = find_related_sites_via_web_search(name)
            if not related or not any(r.get("sites") for r in related):
                related = find_related_sites_for_topic(name)

            def _done():
                if not ww.winfo_exists():
                    return
                ww.destroy()
                sc, bc = count_unique_domains(related) if related else (0, 0)
                if sc or bc:
                    msg = (
                        f"총 {sc:,}개 사이트, {bc:,}개 게시판이 검색되었습니다.\n"
                        "이 목록은 토픽별 핫키워드 검색 실행 시 참고하여 사용됩니다.\n\n등록할까요?"
                    )
                else:
                    msg = f"'{name}'와 일치하는 항목이 없어 0건입니다.\n그래도 등록할까요?"
                if not messagebox.askyesno("등록 확인", msg, parent=win):
                    return
                new_topic = {
                    "name": name, "enabled": True,
                    "keyword_count": DEFAULT_KEYWORD_COUNT,
                    "related_sites": related or [],
                }
                settings["custom_topics"].append(new_topic)
                ordered_names.append(name)
                selected[name] = True
                add_var.set("")
                _mark_dirty()
                _rebuild_topic_list()
                _toast(f"✓ '{name}' 토픽 추가됨")

            win.after(0, _done)

        threading.Thread(target=_search, daemon=True).start()

    abtn.config(command=add_topic)
    ae.bind("<Return>", lambda e: add_topic())
    ae.focus_set()

    # U-4: 섹션 구분선
    tk.Frame(sf, height=1, bg=C["bdr"]).pack(fill=tk.X, padx=pd, pady=(8, 0))

    # ── 섹션 3: 토픽 목록 ──
    s3_header = tk.Frame(sf, bg=C["bg"])
    s3_header.pack(fill=tk.X, padx=pd, pady=(10, 4))
    bar3 = tk.Frame(s3_header, width=3, bg=C["accent_line"], height=14)
    bar3.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
    bar3.pack_propagate(False)
    tk.Label(s3_header, text="토픽 목록  (클릭 = 활성 토글  ·  드래그 = 순서 변경)", font=F["h2"], fg=C["tx"], bg=C["bg"]).pack(anchor=tk.W)
    inner = tk.Frame(sf, bg=C["bg"])
    inner.pack(fill=tk.X, padx=pd, pady=(0, pd))

    def _build_row(t, name, ptc=None):
        is_on = selected.get(name, True)
        bg = C["sel"] if is_on else C["sf2"]
        fg = C["sel_fg"] if is_on else C["tx"]
        fg2 = C["sel_fg"] if is_on else C["tx2"]

        related = t.get("related_sites") or []
        if related:
            s_cnt, b_cnt = count_unique_domains(related)
        elif ptc and name in ptc:
            s_cnt, b_cnt = ptc[name]
        else:
            s_cnt, b_cnt = 0, 0

        row = tk.Frame(inner, bg=bg, padx=10, pady=8, highlightbackground=C["bdr"], highlightthickness=1, cursor="hand2")
        row.pack(fill=tk.X, pady=2)
        tk.Label(row, text="⋮⋮", font=("Segoe UI", 9), fg=C["tx3"], bg=bg, cursor="fleur").pack(side=tk.LEFT, padx=(0, 6))
        tk.Label(row, text=get_topic_icon(name), font=F["icon"], fg=fg, bg=bg, cursor="hand2").pack(side=tk.LEFT, padx=(0, 6))
        tk.Label(row, text=get_display_name(name), font=("Segoe UI", 10, "bold"), fg=fg, bg=bg, cursor="hand2").pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(row, text=f"{s_cnt:,}사이트·{b_cnt:,}게시판", font=F["xs"], fg=fg2, bg=bg, cursor="hand2").pack(side=tk.LEFT, padx=(0, 6))

        kf = tk.Frame(row, bg=bg)
        kf.pack(side=tk.RIGHT)
        db = tk.Button(kf, text="✕", font=("Segoe UI", 9), fg=C["tx3"], bg=bg, activeforeground=C["red"], relief=tk.FLAT, cursor="hand2")
        db.pack(side=tk.RIGHT, padx=(6, 0))
        db.bind("<Enter>", lambda e, b=db: b.config(fg=C["red"]))
        db.bind("<Leave>", lambda e, b=db: b.config(fg=C["tx3"]))
        tk.Label(kf, text="개", font=F["xs"], fg=fg2, bg=bg).pack(side=tk.RIGHT)
        sv = tk.StringVar(value=str(max(1, min(10, int(t.get("keyword_count", DEFAULT_KEYWORD_COUNT))))))
        spin_vars[name] = sv
        sp = tk.Spinbox(kf, from_=1, to=10, width=3, textvariable=sv, font=("Segoe UI", 9), bg=C["inp"], fg=C["tx"], buttonbackground=C["sf2"])
        sp.pack(side=tk.RIGHT, ipady=2)

        def _on_spin_change(*_a):
            _mark_dirty()
        sv.trace_add("write", _on_spin_change)

        def _sw(e, v=sv):
            try:
                val = int(v.get() or 1)
                v.set(str(max(1, min(10, val + (1 if e.delta > 0 else -1)))))
            except (ValueError, TypeError):
                pass
        sp.bind("<MouseWheel>", _sw)
        tk.Label(kf, text="핫키워드", font=F["xs"], fg=fg2, bg=bg).pack(side=tk.RIGHT, padx=(0, 4))

        topic_frames[name] = row

        def _apply_colors(on):
            bg_ = C["sel"] if on else C["sf2"]
            fg_ = C["sel_fg"] if on else C["tx"]
            fg2_ = C["sel_fg"] if on else C["tx2"]
            row.config(bg=bg_)
            for ch in row.winfo_children():
                try:
                    ch.config(bg=bg_)
                    if isinstance(ch, tk.Label):
                        ch.config(fg=fg_ if ch.cget("cursor") in ("hand2", "fleur") else fg2_)
                    elif isinstance(ch, tk.Frame):
                        ch.config(bg=bg_)
                        for sub in ch.winfo_children():
                            try:
                                sub.config(bg=bg_)
                                if isinstance(sub, tk.Label):
                                    sub.config(fg=fg2_)
                            except Exception:
                                pass
                except Exception:
                    pass

        def _press(e):
            drag["src"] = name
            drag["y0"] = e.y_root
            drag["active"] = False

        def _motion(e):
            if drag["src"] is None:
                return
            if not drag["active"] and abs(e.y_root - drag["y0"]) > 8:
                drag["active"] = True
            if not drag["active"]:
                return
            for nm, rw in topic_frames.items():
                try:
                    ry = rw.winfo_rooty()
                    rh = rw.winfo_height()
                    if ry <= e.y_root <= ry + rh and nm != drag["src"]:
                        rw.config(highlightbackground=C["ac"], highlightthickness=2)
                    else:
                        rw.config(highlightbackground=C["bdr"], highlightthickness=1)
                except Exception:
                    pass

        def _release(e):
            src = drag["src"]
            was_drag = drag["active"]
            drag["src"] = None
            drag["active"] = False
            for rw in topic_frames.values():
                try:
                    rw.config(highlightbackground=C["bdr"], highlightthickness=1)
                except Exception:
                    pass
            if not src:
                return
            if not was_drag:
                selected[src] = not selected.get(src, True)
                _apply_colors(selected[src])
                _refresh_right()
                _mark_dirty()
                return
            tgt = None
            for nm, rw in topic_frames.items():
                try:
                    ry = rw.winfo_rooty()
                    rh = rw.winfo_height()
                    if ry <= e.y_root <= ry + rh:
                        tgt = nm
                        break
                except Exception:
                    pass
            if tgt and tgt != src and src in ordered_names and tgt in ordered_names:
                si = ordered_names.index(src)
                ti = ordered_names.index(tgt)
                ordered_names.insert(ti, ordered_names.pop(si))
                _mark_dirty()
                for rw in topic_frames.values():
                    rw.pack_forget()
                for nm in ordered_names:
                    rw = topic_frames.get(nm)
                    if rw:
                        rw.pack(fill=tk.X, pady=2)

        for w in row.winfo_children():
            if not isinstance(w, (tk.Spinbox, tk.Button)):
                w.bind("<ButtonPress-1>", lambda e: _press(e))
                w.bind("<B1-Motion>", lambda e: _motion(e))
                w.bind("<ButtonRelease-1>", lambda e: _release(e))
        row.bind("<ButtonPress-1>", lambda e: _press(e))
        row.bind("<B1-Motion>", lambda e: _motion(e))
        row.bind("<ButtonRelease-1>", lambda e: _release(e))

        def _del(n=name):
            if messagebox.askyesno("삭제", f"'{n}' 토픽을 삭제하시겠습니까?", parent=win):
                settings["topics"] = [x for x in settings["topics"] if x.get("name") != n]
                settings["custom_topics"] = [x for x in settings["custom_topics"] if x.get("name") != n]
                if n in ordered_names:
                    ordered_names.remove(n)
                selected.pop(n, None)
                _mark_dirty()
                _rebuild_topic_list()
                _toast(f"'{n}' 삭제됨")

        db.config(command=_del)

    def _rebuild_topic_list():
        _sync_spin_to_settings()
        scroll_pos = canvas.yview()
        for w in inner.winfo_children():
            w.destroy()
        topic_frames.clear()
        spin_vars.clear()
        ptc = get_per_topic_counts(topic_names=list(ordered_names))
        for name in list(ordered_names):
            t = _get_topic(name)
            if t:
                _build_row(t, name, ptc)
        _refresh_right()
        canvas.update_idletasks()
        canvas.yview_moveto(scroll_pos[0])

    ptc_initial = get_per_topic_counts(topic_names=[t.get("name", "") for t in all_topics])
    for t in all_topics:
        name = t.get("name", "")
        if name:
            _build_row(t, name, ptc_initial)


# ═══════════════════════════════════════════════════
#  메인 윈도우
# ═══════════════════════════════════════════════════
def main():
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox, filedialog

    _instance_ok = acquire_instance_lock()

    if not _instance_ok:
        log.warning("Instance lock not acquired")
        _r = tk.Tk()
        _r.withdraw()
        go = messagebox.askyesno(
            "게시판 검색기",
            "프로그램이 이미 실행 중일 수 있습니다.\n"
            "계속 실행하시겠습니까?\n\n"
            "(동시 실행 시 설정 파일이 손상될 수 있습니다)",
        )
        _r.destroy()
        if not go:
            sys.exit(0)

    # 고급 다크 테마 (통계 대시보드와 톤 통일)
    COLORS = {
        "bg": "#16161a", "card": "#1c1c21", "inp": "#232328",
        "ac": "#0ea5e9", "ac_h": "#0384c7", "ac_soft": "#0c4a6e",
        "text": "#e4e4e7", "muted": "#a1a1aa", "border": "#27272a",
        "stop": "#ef4444", "stop_h": "#dc2626",
        "accent_line": "#0ea5e9",
    }

    root = tk.Tk()
    root.title(f"게시판 검색기 — {APP_VERSION}")
    root.geometry("740x700")
    root.minsize(620, 540)
    root.configure(bg=COLORS["bg"])
    root.resizable(True, True)

    ico_path = BASE / "dangnagui.ico"
    if ico_path.exists():
        try:
            root.iconbitmap(str(ico_path))
        except Exception:
            pass

    FT = ("Segoe UI", 18, "bold")
    FS = ("Segoe UI", 10)
    FB = ("Segoe UI", 11, "bold")
    is_running = [False]
    _gen = [0]

    _missing_deps: list[str] = []
    try:
        import pyperclip  # noqa: F401
    except ImportError:
        _missing_deps.append("pyperclip")
    try:
        from ddgs import DDGS  # noqa: F401
    except ImportError:
        try:
            from duckduckgo_search import DDGS  # noqa: F401
        except ImportError:
            _missing_deps.append("ddgs")

    mf = tk.Frame(root, bg=COLORS["bg"], padx=28, pady=14)
    mf.pack(fill=tk.BOTH, expand=True)

    # ── 헤더 (고급 스타일: 하단 액센트 라인) ──
    hdr = tk.Frame(mf, bg=COLORS["card"], pady=12)
    hdr.pack(fill=tk.X, pady=(0, 10))
    tk.Frame(hdr, height=2, bg=COLORS["accent_line"]).pack(side=tk.BOTTOM, fill=tk.X)
    hl = tk.Frame(hdr, bg=COLORS["card"], padx=4)
    hl.pack(side=tk.LEFT, fill=tk.Y)

    title_row = tk.Frame(hl, bg=COLORS["card"])
    title_row.pack(anchor=tk.W)
    tk.Label(title_row, text="게시판 검색기", font=("Segoe UI Semibold", 18), fg=COLORS["text"], bg=COLORS["card"]).pack(side=tk.LEFT)
    tk.Label(title_row, text=f"  {APP_VERSION}", font=("Segoe UI", 9), fg=COLORS["muted"], bg=COLORS["card"]).pack(side=tk.LEFT, anchor=tk.S, pady=(0, 4))
    tk.Label(title_row, text=f"  {APP_FLAG}", font=("Segoe UI Emoji", 14), fg=COLORS["text"], bg=COLORS["card"]).pack(side=tk.LEFT, anchor=tk.S, pady=(0, 2))

    tk.Label(hl, text="토픽별 핫키워드 · 네티즌 의견 실시간 리포트", font=("Segoe UI", 10), fg=COLORS["muted"], bg=COLORS["card"]).pack(anchor=tk.W, pady=(4, 0))

    def _settings_summary():
        s = get_settings()
        topics = (s.get("topics") or []) + (s.get("custom_topics") or [])
        enabled = sum(1 for t in topics if t.get("enabled", True))
        hours = s.get("hours", DEFAULT_HOURS)
        return f"{enabled}개 토픽 · {hours}시간 기준"

    summary_var = tk.StringVar(value=_settings_summary())
    tk.Label(hl, textvariable=summary_var, font=("Segoe UI", 9), fg=COLORS["ac"], bg=COLORS["card"]).pack(anchor=tk.W, pady=(6, 0))

    sc, bc = get_site_board_counts_display()
    total_var = tk.StringVar(value=f"{sc:,}개 사이트 · {bc:,}개 게시판 검색")
    tk.Label(hl, textvariable=total_var, font=("Segoe UI", 9), fg=COLORS["muted"], bg=COLORS["card"]).pack(anchor=tk.W, pady=(2, 0))

    if _missing_deps:
        dep_text = f"⚠ 미설치 모듈: {', '.join(_missing_deps)} — pip install 필요"
        tk.Label(hl, text=dep_text, font=("Segoe UI", 8), fg="#f59e0b", bg=COLORS["card"]).pack(anchor=tk.W, pady=(2, 0))

    def open_settings():
        if is_running[0]:
            messagebox.showinfo(
                "설정",
                "검색 중에는 설정을 변경할 수 없습니다.\n검색이 끝난 뒤 다시 시도해 주세요.",
            )
            return

        def _after():
            try:
                from report_engine import invalidate_db_cache
                invalidate_db_cache()
            except Exception:
                pass
            summary_var.set(_settings_summary())
            s, b = get_site_board_counts_display()
            total_var.set(f"{s:,}개 사이트 · {b:,}개 게시판 검색")

        _open_settings_window(root, on_settings_saved=_after)

    hr = tk.Frame(hdr, bg=COLORS["card"])
    hr.pack(side=tk.RIGHT, anchor=tk.NE)
    gear = tk.Button(
        hr, text="⚙", font=("Segoe UI Symbol", 16), fg=COLORS["muted"],
        bg=COLORS["card"], activebackground=COLORS["inp"],
        activeforeground=COLORS["ac"], relief=tk.FLAT, cursor="hand2",
        command=open_settings, borderwidth=0, highlightthickness=0,
    )
    gear.pack(anchor=tk.E, padx=4, pady=(0, 2))
    gear.bind("<Enter>", lambda e: gear.config(fg=COLORS["ac"]))
    gear.bind("<Leave>", lambda e: gear.config(fg=COLORS["muted"]))

    def _send_mail():
        if messagebox.askyesno("메일 보내기", f"저작권자에게 메일을 보내시겠습니까?\n\n받는 사람: {EMAIL}"):
            webbrowser.open(f"mailto:{EMAIL}?subject=게시판 검색기 문의")

    mail_btn = tk.Button(
        hr, text="✉", font=("Segoe UI Symbol", 14), fg=COLORS["muted"],
        bg=COLORS["card"], activebackground=COLORS["inp"],
        activeforeground=COLORS["ac"], relief=tk.FLAT, cursor="hand2",
        command=_send_mail, borderwidth=0, highlightthickness=0,
    )
    mail_btn.pack(anchor=tk.E, padx=4)
    mail_btn.bind("<Enter>", lambda e: mail_btn.config(fg=COLORS["ac"]))
    mail_btn.bind("<Leave>", lambda e: mail_btn.config(fg=COLORS["muted"]))

    # v1.3.0: 통계 보기 버튼
    def _open_stats():
        """통계 대시보드 창을 엽니다. 검색 데이터가 없으면 안내 메시지."""
        with _data_lock:
            search_data = _last_search_data
        if search_data is None:
            messagebox.showinfo(
                "통계 보기",
                "먼저 ▶ 스타트로 리포트를 생성한 뒤 통계를 확인할 수 있습니다.",
            )
            return
        try:
            from stats_window import open_stats_window
            stats = search_data.get("통계", {})
            open_stats_window(root, stats, search_data, initial_pdf_dir=get_settings().get("pdf_default_dir") or None)
        except ImportError:
            messagebox.showwarning("통계 보기", "stats_window 모듈을 로드할 수 없습니다.")
        except Exception as e:
            log.error("통계 대시보드 오류: %s", e)
            messagebox.showerror("오류", "통계 대시보드를 열 수 없습니다.\n\n로그 파일(logs/app.log)을 확인해 주세요.")

    stats_btn = tk.Button(
        hr, text="📊", font=("Segoe UI Emoji", 14), fg=COLORS["muted"],
        bg=COLORS["card"], activebackground=COLORS["inp"],
        activeforeground=COLORS["ac"], relief=tk.FLAT, cursor="hand2",
        command=_open_stats, borderwidth=0, highlightthickness=0,
    )
    stats_btn.pack(anchor=tk.E, padx=4)
    stats_btn.bind("<Enter>", lambda e: stats_btn.config(fg=COLORS["ac"]))
    stats_btn.bind("<Leave>", lambda e: stats_btn.config(fg=COLORS["muted"]))

    # ── 소셜 공유 아이콘 ──
    SOCIAL_LINKS = [
        ("f", "Facebook", "#1877f2", "https://www.facebook.com"),
        ("𝕏", "X", "#9ca3af", "https://x.com"),
        ("💬", "카카오톡", "#fee500", "kakaotalk://main"),
        ("✈", "텔레그램", "#26a5e4", "tg://resolve"),
        ("📷", "인스타그램", "#e4405f", "https://www.instagram.com"),
        ("🎮", "디스코드", "#5865f2", "discord://"),
    ]

    stat_var = tk.StringVar(value=PLACEHOLDER)

    def _open_social(name, url):
        txt = text_area.get("1.0", tk.END).strip()
        if not txt or txt == PLACEHOLDER:
            stat_var.set("공유할 리포트가 없습니다. 먼저 리포트를 생성하세요.")
            return
        try:
            import pyperclip
            pyperclip.copy(txt)
        except Exception:
            pass
        try:
            import os
            # Windows 전용 API — 크로스 플랫폼 시 webbrowser.open(url)로 대체 필요
            os.startfile(url)
            stat_var.set(f"리포트가 클립보드에 복사됨 → {name}에서 붙여넣기 하세요")
        except Exception as e:
            log.warning("Social share failed (%s): %s", name, e)
            stat_var.set(f"{name} 실행 실패 — 프로그램이 설치되어 있는지 확인하세요.")

    sbar = tk.Frame(mf, bg=COLORS["card"])
    sbar.pack(fill=tk.X, pady=(0, 6))
    for icon, name, accent, url in SOCIAL_LINKS:
        b = tk.Button(
            sbar, text=icon, font=("Segoe UI Emoji", 12), fg=COLORS["muted"],
            bg=COLORS["card"], activebackground=COLORS["inp"],
            activeforeground=accent, relief=tk.FLAT, cursor="hand2",
            borderwidth=0, highlightthickness=0, padx=3, pady=2,
            command=lambda n=name, u=url: _open_social(n, u),
        )
        b.pack(side=tk.RIGHT, padx=2)
        b.bind("<Enter>", lambda e, b=b, c=accent: b.config(fg=c))
        b.bind("<Leave>", lambda e, b=b: b.config(fg=COLORS["muted"]))

    # ── 컨트롤 카드 (고급 스타일) ──
    card = tk.Frame(mf, bg=COLORS["card"], padx=22, pady=16, highlightbackground=COLORS["border"], highlightthickness=1)
    card.pack(fill=tk.X, pady=(0, 12))
    bf = tk.Frame(card, bg=COLORS["card"])
    bf.pack(fill=tk.X)

    start_btn = tk.Button(
        bf, text="  ▶  스타트  ", font=FB, fg="#fff", bg=COLORS["ac"],
        activebackground=COLORS["ac_h"], activeforeground="#fff",
        relief=tk.FLAT, padx=22, pady=8, cursor="hand2",
        borderwidth=0, highlightthickness=0,
    )
    start_btn.pack(side=tk.LEFT, padx=(0, 8))
    start_btn.bind("<Enter>", lambda e: start_btn.config(bg=COLORS["ac_h"] if not is_running[0] else COLORS["stop_h"]))
    start_btn.bind("<Leave>", lambda e: start_btn.config(bg=COLORS["ac"] if not is_running[0] else COLORS["stop"]))

    copy_btn = tk.Button(
        bf, text="  📋 복사  ", font=FB, fg=COLORS["text"], bg=COLORS["inp"],
        activebackground=COLORS["border"], activeforeground="#fff",
        relief=tk.FLAT, padx=22, pady=8, cursor="hand2",
        borderwidth=0, highlightthickness=0,
    )
    copy_btn.pack(side=tk.LEFT, padx=(0, 8))
    copy_btn.bind("<Enter>", lambda e: copy_btn.config(bg=COLORS["border"]))
    copy_btn.bind("<Leave>", lambda e: copy_btn.config(bg=COLORS["inp"]))

    save_file_btn = tk.Button(
        bf, text="  💾 저장  ", font=FB, fg=COLORS["text"], bg=COLORS["inp"],
        activebackground=COLORS["border"], activeforeground="#fff",
        relief=tk.FLAT, padx=22, pady=8, cursor="hand2",
        borderwidth=0, highlightthickness=0,
    )
    save_file_btn.pack(side=tk.LEFT)
    save_file_btn.bind("<Enter>", lambda e: save_file_btn.config(bg=COLORS["border"]))
    save_file_btn.bind("<Leave>", lambda e: save_file_btn.config(bg=COLORS["inp"]))

    # 추가개발-4: 리포트 이력 (최근 5개)
    report_history = []
    report_history_index = [0]

    def _show_history_at(idx):
        if not report_history or idx < 0 or idx >= len(report_history):
            return
        report_history_index[0] = idx
        text_area.configure(state=tk.NORMAL)
        text_area.delete("1.0", tk.END)
        text_area.insert(tk.END, report_history[idx]["text"])
        _color_result()
        text_area.see("1.0")
        text_area.configure(state=tk.DISABLED)
        stat_var.set(f"리포트 이력 {idx + 1}/{len(report_history)} ({report_history[idx]['ts']})")
        prev_btn.config(state=tk.NORMAL if idx < len(report_history) - 1 else tk.DISABLED)
        next_btn.config(state=tk.NORMAL if idx > 0 else tk.DISABLED)

    prev_btn = tk.Button(
        bf, text="  ◀ 이전  ", font=FB, fg=COLORS["muted"], bg=COLORS["inp"],
        activebackground=COLORS["border"], relief=tk.FLAT, padx=12, pady=8, cursor="hand2",
        state=tk.DISABLED,
    )
    prev_btn.pack(side=tk.LEFT, padx=(8, 4))
    next_btn = tk.Button(
        bf, text="  다음 ▶  ", font=FB, fg=COLORS["muted"], bg=COLORS["inp"],
        activebackground=COLORS["border"], relief=tk.FLAT, padx=12, pady=8, cursor="hand2",
        state=tk.DISABLED,
    )
    next_btn.pack(side=tk.LEFT)
    prev_btn.config(command=lambda: _show_history_at(report_history_index[0] + 1))
    next_btn.config(command=lambda: _show_history_at(report_history_index[0] - 1))
    prev_btn.bind("<Enter>", lambda e: prev_btn.config(bg=COLORS["border"]) if prev_btn["state"] == tk.NORMAL else None)
    prev_btn.bind("<Leave>", lambda e: prev_btn.config(bg=COLORS["inp"]))
    next_btn.bind("<Enter>", lambda e: next_btn.config(bg=COLORS["border"]) if next_btn["state"] == tk.NORMAL else None)
    next_btn.bind("<Leave>", lambda e: next_btn.config(bg=COLORS["inp"]))

    # 프로그레스 바
    prog_container = tk.Frame(card, bg=COLORS["card"])
    prog_container.pack(fill=tk.X, pady=(6, 0))
    try:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor=COLORS["inp"], background=COLORS["ac"], thickness=6,
        )
    except Exception:
        pass
    progress_bar = ttk.Progressbar(
        prog_container, style="Custom.Horizontal.TProgressbar",
        mode="determinate", maximum=100,
    )

    count_var = tk.StringVar(value="")
    tk.Label(card, textvariable=count_var, font=("Segoe UI", 10, "bold"), fg=COLORS["ac"], bg=COLORS["card"]).pack(anchor=tk.W, pady=(4, 2))
    cur_var = tk.StringVar(value="")
    tk.Label(card, textvariable=cur_var, font=FS, fg=COLORS["muted"], bg=COLORS["card"]).pack(anchor=tk.W, pady=(0, 2))
    tk.Label(card, textvariable=stat_var, font=FS, fg=COLORS["muted"], bg=COLORS["card"]).pack(anchor=tk.W)

    def _btn_start():
        is_running[0] = False
        start_btn.config(text="  ▶  스타트  ", bg=COLORS["ac"], activebackground=COLORS["ac_h"])

    def _btn_stop():
        is_running[0] = True
        start_btn.config(text="  ■  중지  ", bg=COLORS["stop"], activebackground=COLORS["stop_h"])

    def _reset():
        _btn_start()
        count_var.set("")
        cur_var.set("")
        stat_var.set(PLACEHOLDER)
        progress_bar.pack_forget()
        text_area.configure(state=tk.NORMAL)
        text_area.delete("1.0", tk.END)
        text_area.insert(tk.END, PLACEHOLDER)
        text_area.configure(state=tk.DISABLED)

    def on_start_stop():
        if is_running[0]:
            _stop_event.set()
            _reset()
            return
        # V-3: 토픽이 0개면 스타트 차단
        topic_config = build_topic_config(get_settings())
        if not topic_config:
            messagebox.showinfo(
                "검색",
                "최소 1개 이상 토픽을 활성화해 주세요.\n\n설정(⚙)에서 토픽을 선택한 뒤 다시 시도하세요.",
            )
            return
        _stop_event.clear()  # V-2: 재시작 시 이벤트 초기화
        _gen[0] += 1
        gen_id = _gen[0]  # V-2: gen_id로 이전 완료 콜백 적용 방지
        _btn_stop()
        stat_var.set("리포트 생성 중...")
        count_var.set("")
        cur_var.set("")
        text_area.configure(state=tk.NORMAL)
        text_area.delete("1.0", tk.END)
        text_area.insert(tk.END, "검색 진행 중...")
        text_area.configure(state=tk.DISABLED)
        progress_bar.pack(fill=tk.X)
        progress_bar["value"] = 0
        root.update_idletasks()

        def pcb(current, total, topic_name, detail=""):
            if _stop_event.is_set():
                return
            pct = (current / total * 100) if total > 0 else 0

            def _update():
                pct_str = f" ({int(pct)}%)" if total > 0 else ""
                count_var.set(f"토픽 {current + 1}/{total}{pct_str} 실시간 검색 중")
                cur_var.set(f"🔍 {topic_name}  {detail}")
                progress_bar["value"] = pct
            root.after(0, _update)

        def work():
            result = run_report(progress_callback=pcb, stop_event=_stop_event)
            if _stop_event.is_set():
                return
            root.after(0, lambda: _apply_result(result, gen_id))

        threading.Thread(target=work, daemon=True).start()

    start_btn.config(command=on_start_stop)

    _tags: set[str] = set()

    def _color_result():
        _tags.clear()
        rng = random.Random(date_seed())
        tp = ["#fef08a", "#86efac", "#93c5fd", "#c4b5fd", "#f9a8d4", "#fdba74", "#7dd3fc", "#bbf7d0", "#ddd6fe", "#a5f3fc"]
        hp = ["#fde047", "#a5f3fc", "#fbcfe8", "#bfdbfe", "#d9f99d", "#fed7aa", "#e9d5ff", "#99f6e4", "#fecdd3", "#cffafe"]
        rng.shuffle(tp)
        rng.shuffle(hp)
        ti = hi = 0
        for i, line in enumerate(text_area.get("1.0", tk.END).split("\n")):
            s, e = f"{i + 1}.0", f"{i + 1}.end"
            st = line.strip()
            if st.startswith("•") or st.startswith("\u2022"):
                tag = f"t{ti % 10}"
                text_area.tag_configure(tag, foreground=tp[ti % 10])
                _tags.add(tag)
                text_area.tag_add(tag, s, e)
                ti += 1
            elif line.startswith("  ·") or line.startswith("  \u00b7"):
                tag = f"h{hi % 10}"
                text_area.tag_configure(tag, foreground=hp[hi % 10])
                _tags.add(tag)
                text_area.tag_add(tag, s, e)
                hi += 1

    def _apply_result(result, gen_id):
        if gen_id != _gen[0]:
            return
        _btn_start()
        progress_bar.pack_forget()
        output, msg, clip = result
        count_var.set("")
        cur_var.set("")
        text_area.configure(state=tk.NORMAL)
        text_area.delete("1.0", tk.END)
        if output:
            text_area.insert(tk.END, output)
            _color_result()
            text_area.see("1.0")
            stat_var.set(f"완료 · 핫키워드 {msg}개" + (" · 클립보드 복사됨" if clip else ""))
            # 추가개발-4: 이력에 추가 (최대 5개)
            report_history.insert(0, {"text": output, "ts": datetime.now().strftime("%Y-%m-%d %H:%M")})
            report_history[:] = report_history[:5]
            report_history_index[0] = 0
            prev_btn.config(state=tk.NORMAL if len(report_history) > 1 else tk.DISABLED)
            next_btn.config(state=tk.DISABLED)
        else:
            text_area.insert(tk.END, f"오류\n\n{msg}")
            stat_var.set("오류 발생")
        text_area.configure(state=tk.DISABLED)

    def on_copy():
        try:
            import pyperclip
            txt = text_area.get("1.0", tk.END).strip()
            if not txt or txt == PLACEHOLDER:
                stat_var.set("복사할 리포트가 없습니다.")
                return
            pyperclip.copy(txt)
            stat_var.set("클립보드에 복사되었습니다.")
        except ImportError:
            stat_var.set("복사 실패 — pip install pyperclip 필요")
        except Exception as e:
            log.warning("Copy failed: %s", e)
            stat_var.set("복사 실패")

    copy_btn.config(command=on_copy)

    def on_save_file():
        txt = text_area.get("1.0", tk.END).strip()
        if not txt or txt == PLACEHOLDER:
            stat_var.set("저장할 리포트가 없습니다.")
            return
        default_dir = BASE / "IMoutput"
        try:
            default_dir.mkdir(exist_ok=True)
        except OSError:
            default_dir = Path.home()
        default_name = f"리포트_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = filedialog.asksaveasfilename(
            parent=root,
            title="리포트 저장",
            initialdir=str(default_dir),
            initialfile=default_name,
            defaultextension=".txt",
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")],
        )
        if not filepath:
            return
        try:
            Path(filepath).write_text(txt, encoding="utf-8")
            stat_var.set(f"저장 완료 → {Path(filepath).name}")
        except Exception as e:
            log.error("File save failed: %s", e)
            stat_var.set(f"저장 실패: {e}")

    save_file_btn.config(command=on_save_file)

    # ── 결과 영역 ──
    rf = tk.Frame(mf, bg=COLORS["bg"])
    rf.pack(fill=tk.BOTH, expand=True)
    text_area = scrolledtext.ScrolledText(
        rf, wrap=tk.WORD, font=FS, bg=COLORS["inp"], fg=COLORS["text"],
        insertbackground=COLORS["text"], selectbackground=COLORS["ac_soft"],
        selectforeground=COLORS["text"], relief=tk.FLAT, padx=14, pady=14,
        borderwidth=0, highlightthickness=0,
    )
    text_area.pack(fill=tk.BOTH, expand=True)
    text_area.insert(tk.END, PLACEHOLDER)
    text_area.configure(state=tk.DISABLED)
    text_area.bind("<FocusIn>", lambda e: text_area.configure(highlightthickness=1, highlightbackground=COLORS["ac"]))
    text_area.bind("<FocusOut>", lambda e: text_area.configure(highlightthickness=0))

    # ── 하단 상태바 (고급 스타일) ──
    status_bar = tk.Frame(mf, bg=COLORS["card"], highlightbackground=COLORS["border"], highlightthickness=1)
    status_bar.pack(fill=tk.X, pady=(10, 0))
    tk.Frame(status_bar, height=1, bg=COLORS["accent_line"]).pack(side=tk.TOP, fill=tk.X)
    sb_inner = tk.Frame(status_bar, bg=COLORS["card"], padx=12, pady=5)
    sb_inner.pack(fill=tk.X)

    tip_var = tk.StringVar(value="")
    db_status = "암호화 DB" if sc > 0 else "DB 미설정"
    db_color = "#22d3ee" if sc > 0 else "#f59e0b"
    db_lbl = tk.Label(
        sb_inner, text=f"● {db_status}", font=("Segoe UI", 9),
        fg=db_color, bg=COLORS["card"],
    )
    db_lbl.pack(side=tk.LEFT, padx=(0, 14))
    db_lbl.bind("<Enter>", lambda e: tip_var.set("사이트 DB가 로드되었습니다." if sc > 0 else "설정에서 사이트 갱신을 실행해 주세요."))
    db_lbl.bind("<Leave>", lambda e: tip_var.set(""))

    tk.Label(
        sb_inner, text="Ctrl+R 시작 | Ctrl+S 저장 | F5 새로고침",
        font=("Segoe UI", 9), fg=COLORS["muted"], bg=COLORS["card"],
    ).pack(side=tk.LEFT)

    tip_lbl = tk.Label(sb_inner, textvariable=tip_var, font=("Segoe UI", 8), fg=COLORS["muted"], bg=COLORS["card"])
    tip_lbl.pack(side=tk.LEFT, padx=(12, 0))
    for w, msg in [(gear, "설정"), (stats_btn, "통계 보기"), (mail_btn, "메일 보내기")]:
        w.bind("<Enter>", lambda e, m=msg: tip_var.set(m))
        w.bind("<Leave>", lambda e: tip_var.set(""))

    cr = tk.Label(
        sb_inner, text=f"{COPYRIGHT} · {EMAIL}",
        font=("Segoe UI", 8), fg=COLORS["muted"], bg=COLORS["card"], cursor="hand2",
    )
    cr.pack(side=tk.RIGHT)
    cr.bind("<Enter>", lambda e: cr.config(fg=COLORS["ac"]))
    cr.bind("<Leave>", lambda e: cr.config(fg=COLORS["muted"]))
    cr.bind("<Button-1>", lambda e: webbrowser.open(f"mailto:{EMAIL}"))

    # ── 키보드 단축키 (V-1: root에만 바인딩, 설정 창은 자체 Esc/Ctrl+S 사용 → 충돌 없음) ──
    root.bind("<Control-r>", lambda e: on_start_stop())
    root.bind("<Control-s>", lambda e: on_save_file())
    root.bind("<F5>", lambda e: on_start_stop())

    # ── 갱신 알림 (인라인 배너 — 팝업 대신) ──
    def _check_update():
        s = get_settings()
        last = s.get("last_track_date", "")
        msg = None
        if last:
            try:
                days = (datetime.now() - datetime.fromisoformat(last)).days
                if days >= UPDATE_WARN_DAYS:
                    msg = f"⚠ 검색 대상 사이트가 {days}일간 갱신되지 않았습니다. 설정(⚙) → 사이트 갱신을 권장합니다."
            except Exception:
                pass
        else:
            msg = "ℹ 첫 실행: 설정(⚙) → '사이트 갱신'으로 최신 사이트 목록을 가져오세요."
        if msg:
            banner = tk.Frame(mf, bg="#3a2f00")
            banner.pack(fill=tk.X, before=rf, pady=(0, 6))
            tk.Label(banner, text=msg, font=("Segoe UI", 9), fg="#ffd700", bg="#3a2f00", pady=4).pack(side=tk.LEFT, padx=10)
            close_b = tk.Button(
                banner, text="✕", font=("Segoe UI", 9), fg="#ffd700", bg="#3a2f00",
                activeforeground="#fff", relief=tk.FLAT, cursor="hand2",
                command=banner.destroy,
            )
            close_b.pack(side=tk.RIGHT, padx=6)

    root.after(1500, _check_update)
    root.mainloop()


if __name__ == "__main__":
    main()
