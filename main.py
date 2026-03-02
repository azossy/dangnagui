#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
게시판 검색기 — 임금님귀 v1.2.1
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
    log, date_seed, get_topic_icon, get_display_name,
    acquire_instance_lock,
)

_app_settings = None
_settings_lock = threading.Lock()
_stop_event = threading.Event()
_generation_id = 0

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
    try:
        from report_engine import search_topics_online, format_for_messenger

        if settings is None:
            settings = get_settings()

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

        hours = settings.get("hours", DEFAULT_HOURS)

        data = search_topics_online(
            topic_config, hours,
            region=APP_REGION,
            progress_callback=progress_callback,
            stop_event=stop_event,
        )

        if stop_event and stop_event.is_set():
            return None, "중지됨", False

        if not data.get("카테고리"):
            return None, "검색 결과가 없습니다.\n\n인터넷 연결을 확인하거나\npip install duckduckgo-search 를 실행하세요.", False

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
        return None, str(e), False


# ═══════════════════════════════════════════════════
#  설정 창
# ═══════════════════════════════════════════════════
def _open_settings_window(parent, on_settings_saved=None):
    import tkinter as tk
    from tkinter import messagebox, ttk
    try:
        from app_settings import (
            load_settings, save_settings,
            find_related_sites_for_topic, find_related_sites_via_web_search,
            get_related_sites_for_default_topic,
        )
    except ImportError:
        load_settings = lambda: get_settings()
        save_settings = lambda _: True
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

    # ── 색상·글꼴 ──
    C = {
        "bg": "#1e1e1e", "sf": "#252526", "sf2": "#2d2d30", "inp": "#3c3c3c",
        "bdr": "#3f3f46", "bdr_a": "#0078d4",
        "tx": "#d4d4d4", "tx2": "#969696", "tx3": "#6e6e6e",
        "ac": "#0078d4", "ac_h": "#1a8ad4",
        "sel": "#0a2e4f", "sel_fg": "#a8d4ff",
        "red": "#d13438", "green": "#107c10",
    }
    F = {
        "h1": ("Segoe UI", 12, "bold"), "h2": ("Segoe UI", 10, "bold"),
        "body": ("Segoe UI", 10), "sm": ("Segoe UI", 9), "xs": ("Segoe UI", 8),
        "btn": ("Segoe UI", 10, "bold"), "icon": ("Segoe UI Emoji", 12),
    }

    # ── 윈도우 ──
    win = tk.Toplevel(parent)
    win.title("설정 — 게시판 검색기")
    win.geometry("920x560")
    win.minsize(720, 440)
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
    def do_save(*_):
        try:
            settings["hours"] = max(30, min(100, int(hours_var.get())))
        except (ValueError, TypeError):
            settings["hours"] = DEFAULT_HOURS
        _sync_spin_to_settings()
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
                _sync_spin_to_settings()
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
            win.unbind_all("<MouseWheel>")
        except Exception:
            pass
        win.destroy()

    # ══ 우측 패널 ══
    right = tk.Frame(win, bg=C["sf"], width=230)
    right.pack(side=tk.RIGHT, fill=tk.Y)
    right.pack_propagate(False)
    tk.Frame(right, bg=C["bdr"], width=1).pack(side=tk.LEFT, fill=tk.Y)
    rp = tk.Frame(right, bg=C["sf"], padx=14, pady=12)
    rp.pack(fill=tk.BOTH, expand=True)

    g_s, g_b = get_site_board_counts()
    n_en = sum(1 for n in ordered_names if selected.get(n, True))
    right_var = tk.StringVar(value=f"{n_en}개 토픽 · {g_s:,}개 사이트\n{g_b:,}개 게시판")
    tk.Label(rp, text="검색 대상", font=F["h1"], fg=C["tx"], bg=C["sf"]).pack(anchor=tk.W, pady=(0, 4))
    tk.Label(rp, textvariable=right_var, font=F["body"], fg=C["tx"], bg=C["sf"], justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 6))

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
                tk.Label(rp, text=f"⚠ {days}일 경과 — 갱신 권장", font=F["xs"], fg="#ff8c00", bg=C["sf"]).pack(anchor=tk.W, pady=(0, 4))
        except Exception:
            pass

    tk.Frame(rp, bg=C["bdr"], height=1).pack(fill=tk.X, pady=(0, 8))
    tk.Label(rp, text="토픽별 연관 사이트·게시판을\n웹검색으로 최신 갱신", font=F["xs"], fg=C["tx2"], bg=C["sf"], justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 6))

    # ── 사이트 갱신 ──
    def _run_track(mode):
        pw = tk.Toplevel(win)
        pw.title("사이트 갱신 진행")
        pw.geometry("520x380")
        pw.configure(bg=C["sf"])
        pw.transient(win)
        pw.grab_set()
        pw.resizable(False, False)
        title_txt = "전체 초기화 — 사이트·게시판 재구축" if mode == "full" else "추가 갱신 — 새 사이트·게시판만 추가"
        tk.Label(pw, text=title_txt, font=F["h1"], fg=C["tx"], bg=C["sf"]).pack(anchor=tk.W, padx=20, pady=(12, 6))
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

        def work():
            all_t = settings["topics"] + settings["custom_topics"]
            total = len(all_t)
            total_s = total_b = added_b = 0
            if mode == "full":
                _log("⚠ 기존 사이트·게시판 정보를 모두 삭제합니다.", "warn")
                for t in all_t:
                    t["related_sites"] = []
                _log("  기존 정보 초기화 완료", "ok")
            _log(f"\n총 {total}개 토픽 — 국내 주요 사이트·게시판 검색 시작", "info")
            _log("")
            for idx, t in enumerate(all_t):
                name = t.get("name")
                if not name:
                    continue
                _log(f"({idx + 1}/{total})  {name}", "bold")
                _log("  → 웹검색으로 관련 사이트·게시판 탐색 중...")
                if name in DEFAULT_TOPICS:
                    new_sites = get_related_sites_for_default_topic(name)
                else:
                    new_sites = find_related_sites_via_web_search(name) or find_related_sites_for_topic(name)

                if mode == "add":
                    existing = t.get("related_sites") or []
                    existing_urls = set()
                    for cat in existing:
                        for s in cat.get("sites") or []:
                            existing_urls.add(s.get("url", ""))
                    merged = list(existing)
                    new_count = 0
                    for cat in new_sites:
                        new_entries = [s for s in (cat.get("sites") or []) if s.get("url", "") not in existing_urls]
                        if new_entries:
                            merged.append({"category": cat.get("category", "추가"), "sites": new_entries})
                            new_count += len(new_entries)
                    t["related_sites"] = merged
                    s_c, b_c = count_unique_domains(merged)
                    total_s += s_c
                    total_b += b_c
                    added_b += new_count
                    _log(f"  ✓ {'신규 ' + str(new_count) + '개 추가' if new_count else '변경 없음'} (총 {b_c:,}개)", "ok")
                else:
                    t["related_sites"] = new_sites
                    s_c, b_c = count_unique_domains(new_sites)
                    total_s += s_c
                    total_b += b_c
                    _log(f"  ✓ {s_c:,}개 사이트, {b_c:,}개 게시판 등록", "ok")
                _log("")

            _log("접속율 검사 중...", "info")
            rate = check_sample_urls(sample_size=20, timeout=3)
            today = datetime.now().strftime("%Y-%m-%d")
            settings["last_track_date"] = today
            settings["valid_rate"] = rate
            if rate >= 0:
                _log(f"  유효 접속율: {rate}%", "ok")
            _log("")
            summary = f"총 {total}개 토픽 / {total_s:,}개 사이트 / {total_b:,}개 게시판"
            if mode == "add":
                summary += f" (신규 {added_b:,}개 추가)"
            _log(f"━━ {summary} 갱신 완료 ━━", "bold")

            save_settings(settings)
            set_settings(settings)
            _log("  ✓ 설정 자동 저장 완료", "ok")

            def done():
                if not pw.winfo_exists():
                    return
                valid_var.set(f"유효 접속율 {rate}%" if rate >= 0 else "유효 접속율 측정 실패")
                last_var.set(f"마지막 갱신: {today}")
                ok_btn = tk.Button(
                    pw, text="  확인  ", font=F["btn"], fg="#fff", bg=C["ac"],
                    activebackground=C["ac_h"], relief=tk.FLAT, cursor="hand2",
                    padx=24, pady=5,
                )
                ok_btn.pack(pady=(4, 14))
                ok_btn.bind("<Enter>", lambda e: ok_btn.config(bg=C["ac_h"]))
                ok_btn.bind("<Leave>", lambda e: ok_btn.config(bg=C["ac"]))

                def _close():
                    pw.destroy()
                    dirty[0] = False
                    _rebuild_topic_list()
                    _refresh_right()
                    if on_settings_saved:
                        on_settings_saved()
                    _toast("✓ 사이트 갱신 완료 · 설정 자동 저장됨")

                ok_btn.config(command=_close)
            win.after(0, done)

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

    tb = tk.Button(rp, text="🔄 사이트 갱신", font=F["btn"], fg="#fff", bg=C["ac"], activebackground=C["ac_h"], relief=tk.FLAT, cursor="hand2", command=on_track, pady=5)
    tb.pack(fill=tk.X)
    tb.bind("<Enter>", lambda e: tb.config(bg=C["ac_h"]))
    tb.bind("<Leave>", lambda e: tb.config(bg=C["ac"]))

    spacer = tk.Frame(rp, bg=C["sf"])
    spacer.pack(fill=tk.BOTH, expand=True)

    tk.Frame(rp, bg=C["bdr"], height=1).pack(fill=tk.X, pady=(8, 8))
    sb = tk.Button(
        rp, text="💾 설정 저장 (Ctrl+S)", font=("Segoe UI", 11, "bold"),
        fg="#fff", bg=C["green"], activebackground="#0e6b0e",
        relief=tk.FLAT, cursor="hand2", command=do_save, pady=7,
    )
    sb.pack(fill=tk.X, pady=(0, 4))
    sb.bind("<Enter>", lambda e: sb.config(bg="#0e6b0e"))
    sb.bind("<Leave>", lambda e: sb.config(bg=C["green"]))

    xb = tk.Button(
        rp, text="닫기 (Esc)", font=F["body"], fg=C["tx2"], bg=C["sf2"],
        activebackground=C["bdr"], relief=tk.FLAT, cursor="hand2",
        command=_close_win, pady=5,
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

    # ── 섹션 1: 검색 기준 시간 ──
    s1 = tk.Frame(sf, bg=C["sf"], padx=16, pady=10)
    s1.pack(fill=tk.X, padx=pd, pady=(pd, 6))
    r1 = tk.Frame(s1, bg=C["sf"])
    r1.pack(fill=tk.X)
    tk.Label(r1, text="검색 기준 시간", font=F["h2"], fg=C["tx"], bg=C["sf"]).pack(side=tk.LEFT, padx=(0, 16))
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
    tk.Label(s1, text="현재 시간 기준, 설정 시간 이전까지의 게시판 글 대상 (30~100)", font=F["xs"], fg=C["tx3"], bg=C["sf"]).pack(anchor=tk.W, pady=(4, 0))

    # ── 섹션 2: 토픽 추가 ──
    s2 = tk.Frame(sf, bg=C["sf"], padx=16, pady=10, highlightbackground=C["bdr_a"], highlightthickness=1)
    s2.pack(fill=tk.X, padx=pd, pady=(0, 6))
    tk.Label(s2, text="새 토픽 추가", font=F["h2"], fg=C["ac"], bg=C["sf"]).pack(anchor=tk.W)
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

    # ── 섹션 3: 토픽 목록 ──
    tk.Label(sf, text="토픽 목록  (클릭 = 활성 토글  ·  드래그 = 순서 변경)", font=F["h2"], fg=C["tx"], bg=C["bg"]).pack(anchor=tk.W, padx=pd, pady=(6, 4))
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

    COLORS = {
        "bg": "#1e1e1e", "card": "#252526", "inp": "#2d2d30",
        "ac": "#0078d4", "ac_h": "#106ebe", "ac_soft": "#094771",
        "text": "#cccccc", "muted": "#858585", "border": "#3f3f46",
        "stop": "#d13438", "stop_h": "#e04b4f",
    }

    root = tk.Tk()
    root.title("게시판 검색기")
    root.geometry("680x640")
    root.minsize(560, 500)
    root.configure(bg=COLORS["bg"])
    root.resizable(True, True)

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
        from duckduckgo_search import DDGS  # noqa: F401
    except ImportError:
        _missing_deps.append("duckduckgo-search")

    mf = tk.Frame(root, bg=COLORS["bg"], padx=28, pady=14)
    mf.pack(fill=tk.BOTH, expand=True)

    # ── 헤더 ──
    hdr = tk.Frame(mf, bg=COLORS["bg"])
    hdr.pack(fill=tk.X, pady=(0, 8))
    hl = tk.Frame(hdr, bg=COLORS["bg"])
    hl.pack(side=tk.LEFT, fill=tk.Y)

    title_row = tk.Frame(hl, bg=COLORS["bg"])
    title_row.pack(anchor=tk.W)
    tk.Label(title_row, text="게시판 검색기", font=FT, fg=COLORS["text"], bg=COLORS["bg"]).pack(side=tk.LEFT)
    tk.Label(title_row, text=f"  {APP_VERSION}", font=("Segoe UI", 9), fg=COLORS["muted"], bg=COLORS["bg"]).pack(side=tk.LEFT, anchor=tk.S, pady=(0, 4))
    tk.Label(title_row, text=f"  {APP_FLAG}", font=("Segoe UI Emoji", 14), fg=COLORS["text"], bg=COLORS["bg"]).pack(side=tk.LEFT, anchor=tk.S, pady=(0, 2))

    tk.Label(hl, text="토픽별 핫키워드 · 네티즌 의견 실시간 리포트", font=FS, fg=COLORS["muted"], bg=COLORS["bg"]).pack(anchor=tk.W, pady=(2, 0))

    def _settings_summary():
        s = get_settings()
        topics = (s.get("topics") or []) + (s.get("custom_topics") or [])
        enabled = sum(1 for t in topics if t.get("enabled", True))
        hours = s.get("hours", DEFAULT_HOURS)
        return f"{enabled}개 토픽 · {hours}시간 기준"

    summary_var = tk.StringVar(value=_settings_summary())
    tk.Label(hl, textvariable=summary_var, font=("Segoe UI", 9), fg=COLORS["ac"], bg=COLORS["bg"]).pack(anchor=tk.W, pady=(4, 0))

    sc, bc = get_site_board_counts_display()
    total_var = tk.StringVar(value=f"{sc:,}개 사이트 · {bc:,}개 게시판 검색")
    tk.Label(hl, textvariable=total_var, font=("Segoe UI", 9), fg=COLORS["muted"], bg=COLORS["bg"]).pack(anchor=tk.W, pady=(1, 0))

    if _missing_deps:
        dep_text = f"⚠ 미설치 모듈: {', '.join(_missing_deps)} — pip install 필요"
        tk.Label(hl, text=dep_text, font=("Segoe UI", 8), fg="#ff8c00", bg=COLORS["bg"]).pack(anchor=tk.W, pady=(2, 0))

    def open_settings():
        if is_running[0]:
            return

        def _after():
            summary_var.set(_settings_summary())
            s, b = get_site_board_counts_display()
            total_var.set(f"{s:,}개 사이트 · {b:,}개 게시판 검색")

        _open_settings_window(root, on_settings_saved=_after)

    hr = tk.Frame(hdr, bg=COLORS["bg"])
    hr.pack(side=tk.RIGHT, anchor=tk.NE)
    gear = tk.Button(
        hr, text="⚙", font=("Segoe UI Symbol", 16), fg=COLORS["muted"],
        bg=COLORS["bg"], activebackground=COLORS["card"],
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
        bg=COLORS["bg"], activebackground=COLORS["card"],
        activeforeground=COLORS["ac"], relief=tk.FLAT, cursor="hand2",
        command=_send_mail, borderwidth=0, highlightthickness=0,
    )
    mail_btn.pack(anchor=tk.E, padx=4)
    mail_btn.bind("<Enter>", lambda e: mail_btn.config(fg=COLORS["ac"]))
    mail_btn.bind("<Leave>", lambda e: mail_btn.config(fg=COLORS["muted"]))

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
            os.startfile(url)
            stat_var.set(f"리포트가 클립보드에 복사됨 → {name}에서 붙여넣기 하세요")
        except Exception as e:
            log.warning("Social share failed (%s): %s", name, e)
            stat_var.set(f"{name} 실행 실패 — 프로그램이 설치되어 있는지 확인하세요.")

    sbar = tk.Frame(mf, bg=COLORS["bg"])
    sbar.pack(fill=tk.X, pady=(0, 4))
    for icon, name, accent, url in SOCIAL_LINKS:
        b = tk.Button(
            sbar, text=icon, font=("Segoe UI Emoji", 12), fg=COLORS["muted"],
            bg=COLORS["bg"], activebackground=COLORS["card"],
            activeforeground=accent, relief=tk.FLAT, cursor="hand2",
            borderwidth=0, highlightthickness=0, padx=2, pady=0,
            command=lambda n=name, u=url: _open_social(n, u),
        )
        b.pack(side=tk.RIGHT, padx=2)
        b.bind("<Enter>", lambda e, b=b, c=accent: b.config(fg=c))
        b.bind("<Leave>", lambda e, b=b: b.config(fg=COLORS["muted"]))

    # ── 컨트롤 카드 ──
    card = tk.Frame(mf, bg=COLORS["card"], padx=20, pady=14, highlightbackground=COLORS["border"], highlightthickness=1)
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

    # 프로그레스 바
    prog_container = tk.Frame(card, bg=COLORS["card"])
    prog_container.pack(fill=tk.X, pady=(6, 0))
    try:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor="#3c3c3c", background="#0078d4", thickness=6,
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
        _stop_event.clear()
        _gen[0] += 1
        gen_id = _gen[0]
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
                count_var.set(f"토픽 {current + 1}/{total} 실시간 검색 중")
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

    # ── 하단 저작권 ──
    btm = tk.Frame(mf, bg=COLORS["bg"])
    btm.pack(fill=tk.X, pady=(8, 0))
    cr = tk.Label(btm, text=COPYRIGHT, font=("Segoe UI", 8), fg="#555555", bg=COLORS["bg"], cursor="hand2")
    cr.pack(side=tk.RIGHT)
    cr.bind("<Enter>", lambda e: cr.config(fg=COLORS["ac"]))
    cr.bind("<Leave>", lambda e: cr.config(fg="#555555"))
    cr.bind("<Button-1>", lambda e: webbrowser.open(f"mailto:{EMAIL}"))

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
