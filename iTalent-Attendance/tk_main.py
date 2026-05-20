from __future__ import annotations

import calendar
import ctypes
from ctypes import wintypes
import queue
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from services.italent_client import ItalentClient
from services.overtime import AttendanceSummary, format_minutes, merge_overtime_records, summarize_attendance
from services.updater import ReleaseInfo, UpdateCheckResult, check_releases, download_release, install_downloaded_update
from version import APP_VERSION


def resource_path(relative_path: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path.cwd()))
    return root / relative_path


BG = "#eef3f8"
PANEL = "#ffffff"
INK = "#182234"
MUTED = "#6b7688"
PRIMARY = "#2563eb"
PRIMARY_DARK = "#1d4ed8"
LINE = "#d8e0eb"
SOFT = "#f7f9fc"
POSITIVE_ROW_BG = "#d9f2df"
POSITIVE_ROW_FG = "#14532d"
NEGATIVE_ROW_BG = "#fff1f2"
NEGATIVE_ROW_FG = "#9f1239"
DEFAULT_WORKDAY_END = "17:30"
LOGIN_GROUP_GAP = 18
APP_TITLE = f"iTalent-Attendance {APP_VERSION}"
ICON_ICO = resource_path("assets/italent_icon_true_transparent.ico")
ICON_PNG = resource_path("assets/italent_icon_true_transparent.png")
CREDENTIAL_TARGET = "iTalent-Attendance/iTalent"
SPINNER_FRAMES = ("◐", "◓", "◑", "◒")
REST_DAY_ICON_PNG = resource_path("assets/rest_day_icon.png")
REST_DAY_ICON_COLOR = "#F28D49"
REST_DAY_ICON_PATTERN = (
    "...##...##...##..",
    "..##...##...##...",
    "...##...##...##..",
    "..##...##...##...",
    "..................",
    "..##############..",
    ".##............##.",
    ".##............##.",
    ".##............##.",
    ".##............##.",
    ".##............##.",
    "..##..........##..",
    "...############...",
    "....##########....",
    ".....########.....",
    "..................",
    "..................",
)
REST_DAY_ICON_GAP = 2
REST_DAY_ICON_X_OFFSET = 11
DETAIL_SELECTED_BG = "#dbeafe"


class AttendanceApp(tk.Tk):
    def __init__(self) -> None:
        enable_dpi_awareness()
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1100x660")
        self.minsize(1040, 660)
        self.configure(bg=BG)
        self._set_window_icon()
        self.logo_image = load_logo_image(50)
        self.rest_day_icon = create_rest_day_icon()
        self.result_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.update_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.summary: AttendanceSummary | None = None
        self.client: ItalentClient | None = None
        self.query_meta: dict[str, str] = {}
        self.update_result: UpdateCheckResult | None = None
        self.update_state = "idle"
        self.update_message = ""
        self.update_status_frame: tk.Frame | None = None
        self.update_status_icon: tk.Label | None = None
        self.update_status_text: tk.Label | None = None
        self.update_window: tk.Toplevel | None = None
        self.update_download_label: tk.Label | None = None
        self.update_download_button: ttk.Button | None = None
        self.update_download_release_tag: str | None = None
        self.update_spinner_index = 0
        self.update_spinner_job: str | None = None
        self._configure_styles()
        self._build_login_page()
        center_window(self)
        self.after(100, self._poll_result)
        self.after(120, self._poll_update_result)
        self.after(180, self._start_update_check)

    def _set_window_icon(self) -> None:
        if ICON_ICO.exists():
            try:
                self.iconbitmap(default=str(ICON_ICO))
            except tk.TclError:
                pass

    def _configure_styles(self) -> None:
        self.option_add("*Font", ("Microsoft YaHei UI", 10))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=INK, font=("Microsoft YaHei UI", 10))
        style.configure("Panel.TLabel", background=PANEL, foreground=INK, font=("Microsoft YaHei UI", 10))
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", background=PANEL, foreground=INK, font=("Microsoft YaHei UI", 22, "bold"))
        style.configure("Subtitle.TLabel", background=PANEL, foreground=MUTED, font=("Microsoft YaHei UI", 10))
        style.configure("Metric.TLabel", background="#eef5ff", foreground=PRIMARY_DARK, font=("Microsoft YaHei UI", 42, "bold"))
        style.configure("CardTitle.TLabel", background=SOFT, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("CardValue.TLabel", background=SOFT, foreground=INK, font=("Microsoft YaHei UI", 15, "bold"))
        style.configure("TEntry", fieldbackground="#ffffff", bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, padding=10)
        style.map(
            "TEntry",
            bordercolor=[("focus", PRIMARY), ("hover", "#a9bad2")],
            lightcolor=[("focus", PRIMARY), ("hover", "#a9bad2")],
            darkcolor=[("focus", PRIMARY), ("hover", "#a9bad2")],
        )
        style.configure("Primary.TButton", background=PRIMARY, foreground="#ffffff", font=("Microsoft YaHei UI", 11, "bold"), padding=(18, 11), borderwidth=0)
        style.map("Primary.TButton", background=[("active", PRIMARY_DARK), ("disabled", "#93a4c7")])
        style.configure("Ghost.TButton", background=PANEL, foreground=PRIMARY, font=("Microsoft YaHei UI", 10, "bold"), padding=(14, 9), borderwidth=1)
        style.map("Ghost.TButton", background=[("active", "#eaf1ff")])
        style.configure("SmallGhost.TButton", background=PANEL, foreground=PRIMARY, font=("Microsoft YaHei UI", 8, "bold"), padding=(12, 10), borderwidth=1)
        style.map("SmallGhost.TButton", background=[("active", "#eaf1ff")])
        style.configure("Treeview", background="#ffffff", fieldbackground="#ffffff", foreground=INK, rowheight=38, bordercolor=LINE, font=("Microsoft YaHei UI", 10))
        style.configure("Treeview.Heading", background="#edf2f7", foreground=INK, font=("Microsoft YaHei UI", 10, "bold"), relief=tk.FLAT)
        style.configure(
            "Detail.Treeview",
            background="#ffffff",
            fieldbackground="#ffffff",
            foreground=INK,
            rowheight=42,
            bordercolor=LINE,
            lightcolor=LINE,
            darkcolor=LINE,
            focuscolor="",
            borderwidth=0,
            relief=tk.FLAT,
            font=("Microsoft YaHei UI", 10),
        )
        style.layout(
            "Detail.Treeview",
            [("Treeview.padding", {"sticky": "nswe", "children": [("Treeview.treearea", {"sticky": "nswe"})]})],
        )
        style.configure(
            "Detail.Treeview.Heading",
            background="#edf2f7",
            foreground=INK,
            font=("Microsoft YaHei UI", 10, "bold"),
            bordercolor=LINE,
            lightcolor=LINE,
            darkcolor=LINE,
            borderwidth=1,
            relief=tk.SOLID,
        )
        style.map(
            "Detail.Treeview",
            background=[("selected", DETAIL_SELECTED_BG)],
            foreground=[("selected", INK)],
            bordercolor=[("focus", LINE)],
            lightcolor=[("focus", LINE)],
            darkcolor=[("focus", LINE)],
            focuscolor=[("focus", "")],
        )

    def _clear(self) -> None:
        for child in self.winfo_children():
            child.destroy()

    def _build_login_page(self) -> None:
        self._clear()
        self.geometry("1100x660")
        center_window(self)
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill=tk.BOTH, expand=True)

        card = tk.Frame(shell, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        card.place(relx=0.5, rely=0.5, anchor=tk.CENTER, width=820, height=535)

        brand = tk.Frame(card, bg=PANEL)
        brand.pack(fill=tk.X, padx=58, pady=(28, 4))
        tk.Label(brand, image=self.logo_image, bg=PANEL).pack(side=tk.LEFT, padx=(0, 16))
        text_box = tk.Frame(brand, bg=PANEL)
        text_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(text_box, text="奋斗值计算器", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(
            text_box,
            text="登录 iTalent 后自动获取本月考勤，计算奋斗值与关键考勤指标。",
            style="Subtitle.TLabel",
            wraplength=620,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(4, 0))

        form = tk.Frame(card, bg=PANEL)
        form.pack(fill=tk.X, padx=58, pady=(24, 0))
        form.columnconfigure(0, weight=1)

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        saved_username, saved_password = load_saved_credentials()
        if saved_username:
            self.username_var.set(saved_username)
        if saved_password:
            self.password_var.set(saved_password)
        month_start, month_end = current_month_range()
        self.start_var = tk.StringVar(value=month_start)
        self.end_var = tk.StringVar(value=month_end)

        self._field(form, "用户名", self.username_var, 0)
        self._password_field(form, "密码", self.password_var, 1)

        date_row = tk.Frame(form, bg=PANEL)
        date_row.grid(row=4, column=0, sticky=tk.EW, pady=(LOGIN_GROUP_GAP, 0))
        date_row.columnconfigure(0, weight=1, uniform="login_dates")
        date_row.columnconfigure(1, weight=1, uniform="login_dates")
        self._date_box(date_row, "开始日期", self.start_var, 0, padx=(0, 10))
        self._date_box(date_row, "结束日期", self.end_var, 1, padx=(10, 0))

        self.query_button = ttk.Button(card, text="登录并计算", style="Primary.TButton", command=self._query)
        self.query_button.pack(fill=tk.X, padx=58, pady=(LOGIN_GROUP_GAP, 0))
        self._build_update_status(shell)
        self.bind("<Return>", lambda _event: self._query())
        self.after_idle(lambda: center_window(self))
        self.after(120, lambda: center_window(self))

    def _build_update_status(self, parent: tk.Widget) -> None:
        self.update_status_frame = tk.Frame(parent, bg=BG, cursor="hand2")
        self.update_status_frame.place(relx=1, rely=1, anchor=tk.SE, x=-8, y=-3)
        self.update_status_icon = tk.Label(
            self.update_status_frame,
            text="",
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 10, "bold"),
            width=1,
            cursor="hand2",
        )
        self.update_status_icon.pack(side=tk.LEFT, padx=(0, 4), pady=7)
        self.update_status_text = tk.Label(
            self.update_status_frame,
            text="",
            bg=BG,
            fg=MUTED,
            font=("Microsoft YaHei UI", 9),
            cursor="hand2",
        )
        self.update_status_text.pack(side=tk.LEFT, padx=(0, 0), pady=7)

        def set_hover(active: bool, pressed: bool = False) -> None:
            if not self.update_status_text or not self.update_status_icon:
                return
            color = PRIMARY_DARK if pressed else PRIMARY if active else None
            font = ("Microsoft YaHei UI", 9, "underline") if active else ("Microsoft YaHei UI", 9)
            self.update_status_text.configure(font=font)
            if color:
                self.update_status_icon.configure(fg=color)
                self.update_status_text.configure(fg=color)
            else:
                self._paint_update_status()

        def on_enter(_event: tk.Event) -> None:
            set_hover(True)

        def on_leave(_event: tk.Event) -> None:
            set_hover(False)

        def on_press(_event: tk.Event) -> None:
            set_hover(True, pressed=True)

        def on_release(_event: tk.Event) -> None:
            set_hover(True)
            self._handle_update_status_click()

        for widget in (self.update_status_frame, self.update_status_icon, self.update_status_text):
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            widget.bind("<ButtonPress-1>", on_press)
            widget.bind("<ButtonRelease-1>", on_release)
        self._paint_update_status()

    def _paint_update_status(self) -> None:
        if (
            not self.update_status_icon
            or not self.update_status_text
            or not self.update_status_icon.winfo_exists()
            or not self.update_status_text.winfo_exists()
        ):
            return
        if self.update_state == "checking":
            icon = SPINNER_FRAMES[self.update_spinner_index % len(SPINNER_FRAMES)]
            text = "正在检查更新"
            color = PRIMARY
        elif self.update_state == "failed":
            icon = "!"
            text = "连接GitHub失败，请更换网络环境"
            color = "#b45309"
        elif self.update_state == "has_update":
            icon = "⬆"
            text = "有新版本"
            color = PRIMARY
        elif self.update_state == "current":
            icon = "✓"
            text = "当前已是最新版本"
            color = "#15803d"
        else:
            icon = "↻"
            text = "检查更新"
            color = MUTED
        self.update_status_icon.configure(text=icon, fg=color)
        self.update_status_text.configure(text=text, fg=color)
        if self.update_state == "has_update":
            self.update_status_icon.pack_configure(padx=(2, 2), pady=(8, 6))
        else:
            self.update_status_icon.pack_configure(padx=(0, 4), pady=(7, 7))

    def _start_update_check(self, force: bool = False) -> None:
        if self.update_state == "checking":
            return
        if self.update_result and not force:
            self.update_state = "has_update" if self.update_result.has_update else "current"
            self._paint_update_status()
            return
        self.update_state = "checking"
        self.update_message = ""
        self.update_spinner_index = 0
        self._paint_update_status()
        self._spin_update_status()
        threading.Thread(target=self._update_check_worker, daemon=True).start()

    def _spin_update_status(self) -> None:
        if self.update_spinner_job:
            try:
                self.after_cancel(self.update_spinner_job)
            except tk.TclError:
                pass
            self.update_spinner_job = None
        if self.update_state != "checking":
            self._paint_update_status()
            return
        self.update_spinner_index += 1
        self._paint_update_status()
        self.update_spinner_job = self.after(140, self._spin_update_status)

    def _update_check_worker(self) -> None:
        try:
            self.update_queue.put(("success", check_releases(APP_VERSION)))
        except Exception as exc:
            self.update_queue.put(("failed", str(exc)))

    def _poll_update_result(self) -> None:
        try:
            kind, payload = self.update_queue.get_nowait()
        except queue.Empty:
            self.after(120, self._poll_update_result)
            return

        if kind == "success":
            self.update_result = payload
            self.update_state = "has_update" if payload.has_update else "current"
        elif kind == "failed":
            self.update_message = str(payload)
            self.update_state = "failed"
        elif kind == "download_progress":
            written, total = payload
            self._set_update_download_message(format_download_progress(written, total))
        elif kind == "download_error":
            self._set_update_download_message(str(payload), error=True)
        elif kind == "download_ready":
            self._set_update_download_message("下载完成，正在替换并重启...")
            try:
                install_downloaded_update(payload)
            except Exception as exc:
                self._set_update_download_message(str(exc), error=True)
        self._paint_update_status()
        self.after(120, self._poll_update_result)

    def _handle_update_status_click(self) -> None:
        if self.update_state == "checking":
            return
        if self.update_state in {"failed", "idle"}:
            self._start_update_check(force=True)
            return
        if self.update_result:
            self._show_update_window()

    def _show_update_window(self) -> None:
        if not self.update_result:
            return
        if self.update_window and self.update_window.winfo_exists():
            self.update_window.lift()
            self.update_window.focus_force()
            return

        window = tk.Toplevel(self)
        self.update_window = window
        window.withdraw()
        window.title(APP_TITLE)
        window.geometry("820x620")
        window.minsize(760, 540)
        window.configure(bg=BG)
        if ICON_ICO.exists():
            try:
                window.iconbitmap(default=str(ICON_ICO))
            except tk.TclError:
                pass

        header = tk.Frame(window, bg="#eef5ff", highlightthickness=1, highlightbackground="#b9cdf7")
        header.pack(fill=tk.X, padx=24, pady=(22, 14))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="版本更新", font=("Microsoft YaHei UI", 19, "bold"), background="#eef5ff", foreground=INK).grid(row=0, column=0, sticky=tk.W, padx=18, pady=(16, 2))
        tk.Label(
            header,
            text=f"当前版本 {APP_VERSION} · 更新记录来自 GitHub Releases",
            bg="#eef5ff",
            fg=MUTED,
            font=("Microsoft YaHei UI", 10),
        ).grid(row=1, column=0, sticky=tk.W, padx=18, pady=(0, 16))
        status_text = "发现可更新版本" if self.update_result.has_update else "当前已是最新版本"
        status_color = PRIMARY if self.update_result.has_update else "#15803d"
        tk.Label(header, text=status_text, bg="#eef5ff", fg=status_color, font=("Microsoft YaHei UI", 11, "bold")).grid(row=0, column=1, rowspan=2, sticky=tk.E, padx=18)

        outer = tk.Frame(window, bg=BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 12))
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, bd=0)
        list_frame = tk.Frame(canvas, bg=BG)
        list_window = canvas.create_window((0, 0), window=list_frame, anchor=tk.NW)
        yscroll = ModernScrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=yscroll.set)
        canvas.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 0), pady=(0, 0))
        yscroll.grid(row=0, column=1, sticky=tk.NS, padx=(4, 6), pady=8)

        def update_scroll_region(_event: tk.Event | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def resize_inner(event: tk.Event) -> None:
            canvas.itemconfigure(list_window, width=event.width)

        def on_mousewheel(event: tk.Event) -> str:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        list_frame.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", resize_inner)
        canvas.bind("<MouseWheel>", on_mousewheel)
        list_frame.bind("<MouseWheel>", on_mousewheel)
        window.bind("<MouseWheel>", on_mousewheel, add=True)

        if self.update_result.releases:
            latest_update = self.update_result.latest_update
            for release in self.update_result.releases:
                self._build_release_card(list_frame, release, can_download=release is latest_update)
        else:
            tk.Label(
                list_frame,
                text="GitHub 仓库里暂时还没有发布版本。",
                bg=BG,
                fg=MUTED,
                font=("Microsoft YaHei UI", 10),
            ).pack(anchor=tk.W, padx=18, pady=18)

        footer = tk.Frame(window, bg=BG)
        footer.pack(fill=tk.X, padx=24, pady=(0, 18))
        self.update_download_label = tk.Label(footer, text="", bg=BG, fg=MUTED, font=("Microsoft YaHei UI", 9))
        self.update_download_label.pack(side=tk.LEFT)
        close_button = motion_button(
            footer,
            hover="#eef5ff",
            pressed="#dbeafe",
            text="关闭",
            command=window.destroy,
            bg=PANEL,
            fg=PRIMARY,
            activebackground="#eaf1ff",
            activeforeground=PRIMARY_DARK,
            font=("Microsoft YaHei UI", 8, "bold"),
            width=6,
            height=2,
            bd=1,
            relief=tk.SOLID,
            highlightthickness=0,
            cursor="hand2",
        )
        close_button.pack(side=tk.RIGHT)

        window.transient(self)
        center_window(window)
        window.deiconify()
        window.lift()
        window.focus_force()

    def _build_release_card(self, parent: tk.Widget, release: ReleaseInfo, can_download: bool) -> None:
        card_bg = "#eef5ff" if release.is_newer else PANEL
        border = "#b9cdf7" if release.is_newer else LINE
        accent_color = PRIMARY if release.is_newer else "#9fb2c9"
        card = tk.Frame(parent, bg=card_bg, highlightthickness=1, highlightbackground=border)
        card.pack(fill=tk.X, padx=2, pady=(0, 14))
        card.columnconfigure(1, weight=1)

        tk.Frame(card, bg=accent_color, width=5).grid(row=0, column=0, rowspan=3, sticky=tk.NS)

        top = tk.Frame(card, bg=card_bg)
        top.grid(row=0, column=1, sticky=tk.EW, padx=18, pady=(16, 8))
        top.columnconfigure(0, weight=1)
        title_row = tk.Frame(top, bg=card_bg)
        title_row.grid(row=0, column=0, sticky=tk.W)
        tk.Label(title_row, text=release.name, bg=card_bg, fg=INK, font=("Microsoft YaHei UI", 15, "bold")).pack(side=tk.LEFT)
        badge_text = "预发布" if release.is_prerelease else "正式版"
        badge_bg = "#fff7ed" if release.is_prerelease else "#ecfdf5"
        badge_fg = "#b45309" if release.is_prerelease else "#15803d"
        tk.Label(
            title_row,
            text=badge_text,
            bg=badge_bg,
            fg=badge_fg,
            font=("Microsoft YaHei UI", 8, "bold"),
            padx=8,
            pady=2,
        ).pack(side=tk.LEFT, padx=(10, 0))
        meta = f"{release.tag} · {format_release_date(release.published_at)}"
        if release.asset_name:
            meta += f" · {release.asset_name}"
        tk.Label(top, text=meta, bg=card_bg, fg=MUTED, font=("Microsoft YaHei UI", 9)).grid(row=1, column=0, sticky=tk.W, pady=(5, 0))

        if can_download:
            button = ttk.Button(top, text="下载并更新", style="Primary.TButton")
            button.configure(command=lambda item=release, control=button: self._start_update_download(item, control))
            button.grid(row=0, column=1, rowspan=2, sticky=tk.E, padx=(16, 0))
            if not release.download_url:
                button.configure(state=tk.DISABLED, text="缺少 exe")
            elif self.update_download_release_tag:
                button.configure(state=tk.DISABLED, text="正在下载..." if self.update_download_release_tag == release.tag else "请稍候")

        body = release.body or "这个版本没有填写更新记录。"
        tk.Label(
            card,
            text=body,
            bg=card_bg,
            fg=INK,
            font=("Microsoft YaHei UI", 10),
            justify=tk.LEFT,
            anchor=tk.W,
            wraplength=720,
        ).grid(row=1, column=1, sticky=tk.W, padx=18, pady=(0, 16))

    def _start_update_download(self, release: ReleaseInfo, button: ttk.Button | None = None) -> None:
        if self.update_download_release_tag:
            self._set_update_download_message("更新正在下载，请稍候...")
            return
        if not messagebox.askyesno("确认更新", f"确定下载并更新到 {release.tag} 吗？\n下载完成后程序会自动重启。", parent=self.update_window or self):
            return
        self._set_update_download_message("正在下载更新...")
        self.update_download_release_tag = release.tag
        self.update_download_button = button
        if button:
            button.configure(state=tk.DISABLED, text="正在下载...")
        threading.Thread(target=self._download_update_worker, args=(release,), daemon=True).start()

    def _download_update_worker(self, release: ReleaseInfo) -> None:
        try:
            path = download_release(release, progress=lambda written, total: self.update_queue.put(("download_progress", (written, total))))
            self.update_queue.put(("download_ready", path))
        except Exception as exc:
            self.update_queue.put(("download_error", str(exc)))

    def _set_update_download_message(self, message: str, error: bool = False) -> None:
        if self.update_download_label and self.update_download_label.winfo_exists():
            self.update_download_label.configure(text=message, fg="#b45309" if error else MUTED)
        if error:
            self.update_download_release_tag = None
            if self.update_download_button and self.update_download_button.winfo_exists():
                self.update_download_button.configure(state=tk.NORMAL, text="重新下载")

    def _field(self, parent: tk.Widget, label: str, variable: tk.StringVar, row: int) -> ttk.Entry:
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(row=row * 2, column=0, sticky=tk.W, pady=(0, 7))
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row * 2 + 1, column=0, sticky=tk.EW)
        return entry

    def _password_field(self, parent: tk.Widget, label: str, variable: tk.StringVar, row: int) -> ttk.Entry:
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(row=row * 2, column=0, sticky=tk.W, pady=(LOGIN_GROUP_GAP, 7))
        entry = ttk.Entry(parent, textvariable=variable, show="●")
        entry.grid(row=row * 2 + 1, column=0, sticky=tk.EW)
        disable_ime_for_widget(entry)
        return entry

    def _date_box(
        self,
        parent: tk.Widget,
        label: str,
        variable: tk.StringVar,
        column: int,
        padx: tuple[int, int] = (0, 0),
        pady: tuple[int, int] | int = 0,
        on_month_selected: Any | None = None,
    ) -> tk.Frame:
        box = tk.Frame(parent, bg=SOFT, highlightthickness=1, highlightbackground=LINE, cursor="hand2")
        box.grid(row=0, column=column, sticky=tk.EW, padx=padx, pady=pady)
        box.columnconfigure(0, weight=1)
        title = tk.Label(box, text=label, bg=SOFT, fg=MUTED, font=("Microsoft YaHei UI", 9), cursor="hand2")
        title.grid(row=0, column=0, sticky=tk.W, padx=14, pady=(6, 0))
        value = tk.Label(box, text=variable.get(), bg=SOFT, fg=INK, font=("Microsoft YaHei UI", 12, "bold"), cursor="hand2")
        value.grid(row=1, column=0, sticky=tk.W, padx=14, pady=(0, 7))

        def open_picker(_event: tk.Event | None = None) -> None:
            DatePicker(self, variable, on_month_selected=on_month_selected)

        def refresh(*_args: object) -> None:
            value.configure(text=variable.get())

        def paint(background: str, border: str) -> None:
            box.configure(highlightbackground=border)
            animate_background((box, title, value), background)

        def on_enter(_event: tk.Event) -> None:
            paint("#eef5ff", "#b9cdf7")

        def on_leave(_event: tk.Event) -> None:
            paint(SOFT, LINE)

        def on_press(_event: tk.Event) -> None:
            paint("#dbeafe", PRIMARY)

        def on_release(event: tk.Event) -> None:
            paint("#eef5ff", "#b9cdf7")
            open_picker(event)

        variable.trace_add("write", refresh)
        for widget in (box, title, value):
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            widget.bind("<ButtonPress-1>", on_press)
            widget.bind("<ButtonRelease-1>", on_release)
        return box

    def _query(self) -> None:
        username = self.username_var.get().strip()
        password = self.password_var.get()
        start_date = self.start_var.get().strip()
        end_date = self.end_var.get().strip()
        workday_end = DEFAULT_WORKDAY_END

        if not username or not password:
            messagebox.showwarning("缺少信息", "请先输入用户名和密码。")
            return
        if not validate_date_range(start_date, end_date):
            return

        self.query_button.configure(state=tk.DISABLED, text="正在登录并计算...")
        self.query_meta = {"username": username, "start": start_date, "end": end_date, "workday_end": workday_end}
        thread = threading.Thread(target=self._query_worker, args=(username, password, start_date, end_date, workday_end), daemon=True)
        thread.start()

    def _query_worker(self, username: str, password: str, start_date: str, end_date: str, workday_end: str) -> None:
        try:
            client = ItalentClient()
            client.login(username, password)
            data = client.query_attendance(start_date, end_date, username=username)
            overtime_data = client.query_overtime(username=username)
            data = merge_overtime_records(data, overtime_data, start_date, end_date)
            summary = summarize_attendance(data, workday_end=workday_end)
            self.client = client
            save_credentials(username, password)
            self.result_queue.put(("summary", summary))
        except Exception as exc:
            self.result_queue.put(("error", str(exc)))

    def _requery(self) -> None:
        if not self.client:
            messagebox.showwarning("需要登录", "请先返回登录页重新登录。")
            return
        start_date = self.start_var.get().strip()
        end_date = self.end_var.get().strip()
        if not validate_date_range(start_date, end_date):
            return

        self.query_meta["start"] = start_date
        self.query_meta["end"] = end_date
        thread = threading.Thread(target=self._requery_worker, args=(start_date, end_date), daemon=True)
        thread.start()

    def _requery_worker(self, start_date: str, end_date: str) -> None:
        try:
            assert self.client is not None
            data = self.client.query_attendance(start_date, end_date, username=self.query_meta["username"])
            overtime_data = self.client.query_overtime(username=self.query_meta["username"])
            data = merge_overtime_records(data, overtime_data, start_date, end_date)
            summary = summarize_attendance(data, workday_end=DEFAULT_WORKDAY_END)
            self.result_queue.put(("summary", summary))
        except Exception as exc:
            self.result_queue.put(("error", str(exc)))

    def _poll_result(self) -> None:
        try:
            kind, payload = self.result_queue.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_result)
            return

        if kind == "summary":
            self.summary = payload
            self._build_summary_page(payload)
        else:
            self.query_button.configure(state=tk.NORMAL, text="登录并计算")
            messagebox.showerror("查询失败", payload)
        self.after(100, self._poll_result)

    def _build_summary_page(self, summary: AttendanceSummary) -> None:
        self._clear()
        self.geometry("1100x660")
        center_window(self)
        root = tk.Frame(self, bg=BG)
        root.pack(fill=tk.BOTH, expand=True, padx=28, pady=24)

        top = tk.Frame(root, bg=BG)
        top.pack(fill=tk.X)
        tk.Label(top, image=self.logo_image, bg=BG).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Label(top, text="奋斗值概览", font=("Microsoft YaHei UI", 22, "bold"), background=BG, foreground=INK).pack(side=tk.LEFT)
        ttk.Button(top, text="返回登录", style="Ghost.TButton", command=self._build_login_page).pack(side=tk.RIGHT)

        filters = tk.Frame(root, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        filters.pack(fill=tk.X, pady=(18, 0))
        filters.columnconfigure((0, 1), weight=1, uniform="dates")
        self._date_box(filters, "开始日期", self.start_var, 0, padx=(22, 12), pady=14, on_month_selected=self._requery)
        self._date_box(filters, "结束日期", self.end_var, 1, padx=(0, 18), pady=14, on_month_selected=self._requery)
        ttk.Button(filters, text="重新查询", style="Primary.TButton", command=self._requery).grid(row=0, column=2, padx=(0, 22), pady=16, sticky=tk.NS)

        hero = tk.Frame(root, bg="#eef5ff", highlightthickness=1, highlightbackground="#b9cdf7")
        hero.pack(fill=tk.X, pady=(16, 14))
        hero.columnconfigure(1, weight=1)
        hero.columnconfigure(2, weight=1)

        accent = tk.Frame(hero, bg=PRIMARY, width=6)
        accent.grid(row=0, column=0, sticky=tk.NS)

        left = tk.Frame(hero, bg="#eef5ff")
        left.grid(row=0, column=1, sticky=tk.NSEW, padx=(24, 30), pady=24)
        tk.Label(left, text="累计奋斗值", bg="#eef5ff", fg=MUTED, font=("Microsoft YaHei UI", 10)).pack(anchor=tk.W)
        ttk.Label(left, text=format_minutes(summary.total_minutes), style="Metric.TLabel").pack(anchor=tk.W, pady=(4, 0))
        tk.Label(left, text=f"{summary.total_hours} 小时 · {self.query_meta['start']} 至 {self.query_meta['end']}", bg="#eef5ff", fg=MUTED, font=("Microsoft YaHei UI", 10)).pack(anchor=tk.W)

        right = tk.Frame(hero, bg="#eef5ff")
        right.grid(row=0, column=2, sticky=tk.E, padx=30, pady=24)
        ttk.Button(right, text="查看打卡明细", style="Primary.TButton", command=self._show_detail_window).pack(anchor=tk.E)
        tk.Label(right, text=f"账号：{self.query_meta['username']}", bg="#eef5ff", fg=MUTED, font=("Microsoft YaHei UI", 10)).pack(anchor=tk.E, pady=(12, 0))

        stats = tk.Frame(root, bg=BG)
        stats.pack(fill=tk.X)
        stats.columnconfigure((0, 1, 2, 3), weight=1, uniform="stats")
        self._stat_card(stats, "单休加班时长", format_minutes(summary.restday_overtime_minutes), 0)
        self._stat_card(stats, "加班时长", format_minutes(summary.workday_overtime_minutes + summary.applied_overtime_minutes), 1)
        self._stat_card(stats, "缺勤时长", format_minutes(summary.absence_minutes), 2)
        self._stat_card(stats, "请假时长", format_minutes(summary.leave_minutes), 3)

        info = tk.Frame(root, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        info.pack(fill=tk.X, pady=(14, 0))
        ttk.Label(info, text="统计说明", style="Panel.TLabel", font=("Microsoft YaHei UI", 11, "bold")).pack(anchor=tk.W, padx=18, pady=(12, 4))
        ttk.Label(info, text=f"当前共读取 {len(summary.rows)} 条考勤记录。当天尚未结束，不纳入奋斗值、缺勤和请假统计。", style="Muted.TLabel").pack(anchor=tk.W, padx=18, pady=(0, 3))
        ttk.Label(info, text="需要核对具体打卡时间时，点击右上角“查看打卡明细”。", style="Muted.TLabel").pack(anchor=tk.W, padx=18, pady=(0, 12))
        self.after_idle(lambda: center_window(self))
        self.after(120, lambda: center_window(self))

    def _stat_card(self, parent: tk.Widget, title: str, value: str, column: int) -> None:
        card = tk.Frame(parent, bg=SOFT, highlightthickness=1, highlightbackground=LINE)
        card.grid(row=0, column=column, sticky=tk.EW, padx=(0, 12) if column < 3 else 0)
        ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor=tk.W, padx=18, pady=(16, 3))
        ttk.Label(card, text=value, style="CardValue.TLabel").pack(anchor=tk.W, padx=18, pady=(0, 16))

    def _show_detail_window(self) -> None:
        if not self.summary:
            return
        window = tk.Toplevel(self)
        window.withdraw()
        window.title("打卡明细")
        if ICON_ICO.exists():
            try:
                window.iconbitmap(default=str(ICON_ICO))
            except tk.TclError:
                pass
        detail_width = min(1850, max(1320, window.winfo_screenwidth() - 18))
        detail_height = min(780, max(680, window.winfo_screenheight() - 80))
        window.geometry(f"{detail_width}x{detail_height}")
        window.minsize(min(1580, detail_width), min(700, detail_height))
        window.configure(bg=BG)

        header = tk.Frame(window, bg=BG)
        header.pack(fill=tk.X, padx=24, pady=(22, 12))
        ttk.Label(header, text="打卡明细", font=("Microsoft YaHei UI", 18, "bold"), background=BG, foreground=INK).pack(side=tk.LEFT)

        table_frame = tk.Frame(window, bg=PANEL, highlightthickness=1, highlightbackground=LINE)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 24))

        self._build_detail_table(table_frame)
        center_window(window)
        window.deiconify()
        center_window(window)
        window.attributes("-topmost", True)
        window.lift()
        window.focus_force()
        window.after(120, lambda: center_window(window))
        window.after(80, lambda: window.attributes("-topmost", False))

    def _build_detail_table(self, parent: tk.Widget) -> None:
        assert self.summary is not None
        columns = ("first", "last", "type", "status", "value", "remark")
        headers = {
            "first": "首次打卡",
            "last": "最后打卡",
            "type": "日期类型",
            "status": "状态",
            "value": "奋斗值",
            "remark": "备注",
        }
        widths = {"first": 230, "last": 230, "type": 110, "status": 90, "value": 180, "remark": 680}
        table = ttk.Treeview(parent, columns=columns, show="tree headings", selectmode="browse", style="Detail.Treeview", takefocus=False)
        table.tag_configure("odd", background="#ffffff")
        table.tag_configure("even", background="#f8fbff")
        table.tag_configure("positive", background=POSITIVE_ROW_BG, foreground=POSITIVE_ROW_FG, font=("Microsoft YaHei UI", 10, "bold"))
        table.tag_configure("negative", background=NEGATIVE_ROW_BG, foreground=NEGATIVE_ROW_FG, font=("Microsoft YaHei UI", 10, "bold"))
        table.tag_configure("hover", background="#eaf1ff", foreground=INK)
        table.tag_configure("hover_positive", background="#c6ebd2", foreground=POSITIVE_ROW_FG, font=("Microsoft YaHei UI", 10, "bold"))
        table.tag_configure("hover_negative", background="#ffe4e8", foreground=NEGATIVE_ROW_FG, font=("Microsoft YaHei UI", 10, "bold"))

        table.heading("#0", text="考勤日期", anchor=tk.CENTER)
        table.column("#0", width=245, minwidth=225, anchor=tk.W, stretch=False)
        for key in columns:
            table.heading(key, text=headers[key], anchor=tk.CENTER)
            table.column(key, width=widths[key], minwidth=70, anchor=tk.CENTER, stretch=True)

        rest_icon_labels: list[tuple[str, tk.Label, str]] = []
        date_font = tkfont.Font(font=("Microsoft YaHei UI", 10))
        focus_sink = tk.Frame(parent, width=1, height=1, bg=PANEL, highlightthickness=0, takefocus=True)
        focus_sink.place(x=-20, y=-20)

        def position_rest_icons() -> None:
            for item, label, base_bg in rest_icon_labels:
                bbox = table.bbox(item, "#0")
                if not bbox:
                    label.place_forget()
                    continue
                x, y, _width, height = bbox
                icon_bg = DETAIL_SELECTED_BG if item in table.selection() else base_bg
                label.configure(bg=icon_bg)
                text_width = date_font.measure(str(table.item(item, "text")))
                icon_y = y + max(0, (height - self.rest_day_icon.height()) // 2)
                label.place(x=x + 8 + text_width + REST_DAY_ICON_GAP + REST_DAY_ICON_X_OFFSET, y=icon_y)

        def scroll_table(*args: object) -> None:
            table.yview(*args)
            table.after_idle(position_rest_icons)

        yscroll = ModernScrollbar(parent, orient=tk.VERTICAL, command=scroll_table)
        table.configure(yscrollcommand=lambda first, last: (yscroll.set(first, last), table.after_idle(position_rest_icons)))
        table.grid(row=0, column=0, sticky=tk.NSEW, padx=(1, 0), pady=(1, 0))
        yscroll.grid(row=0, column=1, sticky=tk.NS, padx=(6, 6), pady=8)
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        for row_index, row in enumerate(self.summary.rows):
            tags = ["even" if row_index % 2 else "odd"]
            if row.absence_minutes > 0 or row.leave_minutes > 0:
                tags.append("negative")
            elif row.applied_overtime_minutes > 0 or (row.overtime_minutes > 0 and not row.is_workday):
                tags.append("positive")
            item = table.insert(
                "",
                tk.END,
                text=format_detail_date(row.date),
                values=(
                    row.first_card,
                    row.last_card,
                    row.date_type,
                    row.status,
                    format_minutes(row.net_minutes),
                    row.remark,
                ),
                tags=tuple(tags),
            )
            if should_show_rest_icon(row.date_type):
                icon_bg = "#f8fbff" if "even" in tags else "#ffffff"
                label = tk.Label(
                    table,
                    image=self.rest_day_icon,
                    bg=icon_bg,
                    bd=0,
                    highlightthickness=0,
                    padx=0,
                    pady=0,
                    cursor="arrow",
                )
                rest_icon_labels.append((item, label, icon_bg))

        def on_mousewheel(event: tk.Event) -> str:
            table.yview_scroll(int(-1 * (event.delta / 120)), "units")
            table.after_idle(position_rest_icons)
            return "break"

        def bind_wheel(_event: tk.Event) -> None:
            table.bind_all("<MouseWheel>", on_mousewheel)

        def unbind_wheel(_event: tk.Event) -> None:
            table.unbind_all("<MouseWheel>")

        hover_state: dict[str, tuple[str, ...] | str] = {"item": "", "tags": ()}

        def clear_hover() -> None:
            item = str(hover_state["item"])
            if item:
                table.item(item, tags=hover_state["tags"])
                hover_state["item"] = ""
                hover_state["tags"] = ()

        def set_hover_item(item: str) -> None:
            if item == hover_state["item"]:
                return
            clear_hover()
            if not item:
                table.after_idle(position_rest_icons)
                return
            tags = tuple(table.item(item, "tags"))
            hover_state["item"] = item
            hover_state["tags"] = tags
            if "positive" in tags:
                hover_tag = "hover_positive"
            elif "negative" in tags:
                hover_tag = "hover_negative"
            else:
                hover_tag = "hover"
            table.item(item, tags=tags + (hover_tag,))
            table.after_idle(position_rest_icons)

        def on_table_motion(event: tk.Event) -> None:
            set_hover_item(table.identify_row(event.y))

        def select_item(item: str) -> None:
            if item:
                table.selection_set(item)
                table.focus(item)
                table.after_idle(position_rest_icons)

        def on_table_press(event: tk.Event) -> str | None:
            region = table.identify_region(event.x, event.y)
            if region == "separator":
                return None
            if region == "heading":
                table.state(["!focus"])
                focus_sink.focus_set()
                table.after_idle(lambda: (table.state(["!focus"]), focus_sink.focus_set()))
                return "break"
            item = table.identify_row(event.y)
            if item:
                select_item(item)
                return "break"
            return None

        def keep_table_unfocused(_event: tk.Event) -> None:
            table.state(["!focus"])
            parent.after_idle(lambda: (table.state(["!focus"]), focus_sink.focus_set()))

        table.bind("<MouseWheel>", on_mousewheel)
        table.bind("<Configure>", lambda _event: table.after_idle(position_rest_icons))
        table.bind("<Expose>", lambda _event: table.after_idle(position_rest_icons))
        table.bind("<Enter>", bind_wheel)
        table.bind("<Leave>", lambda event: (clear_hover(), unbind_wheel(event)))
        table.bind("<Motion>", on_table_motion)
        table.bind("<ButtonPress-1>", on_table_press)
        table.bind("<ButtonRelease-1>", lambda event: "break" if table.identify_region(event.x, event.y) == "heading" else None)
        table.bind("<FocusIn>", keep_table_unfocused)

        def bind_icon_events(item: str, label: tk.Label) -> None:
            label.bind("<MouseWheel>", on_mousewheel)
            label.bind("<Enter>", lambda event, row=item: (bind_wheel(event), set_hover_item(row)))
            label.bind("<Leave>", lambda event: (clear_hover(), unbind_wheel(event), table.after_idle(position_rest_icons)))
            label.bind("<ButtonPress-1>", lambda _event, row=item: (select_item(row), "break")[-1])

        for icon_item, icon_label, _icon_bg in rest_icon_labels:
            bind_icon_events(icon_item, icon_label)
        table.after_idle(position_rest_icons)


def animate_background(widgets: tuple[tk.Widget, ...], target: str, steps: int = 6, delay: int = 12) -> None:
    if not widgets:
        return
    try:
        start = widgets[0].winfo_rgb(str(widgets[0].cget("bg")))
        end = widgets[0].winfo_rgb(target)
    except tk.TclError:
        for widget in widgets:
            widget.configure(bg=target)
        return

    start_rgb = tuple(value // 256 for value in start)
    end_rgb = tuple(value // 256 for value in end)

    def step(index: int) -> None:
        ratio = index / steps
        color = "#%02x%02x%02x" % tuple(
            int(start_rgb[channel] + (end_rgb[channel] - start_rgb[channel]) * ratio)
            for channel in range(3)
        )
        for widget in widgets:
            try:
                widget.configure(bg=color)
            except tk.TclError:
                pass
        if index < steps:
            widgets[0].after(delay, lambda: step(index + 1))

    step(1)


def motion_button(parent: tk.Widget, hover: str = "#eef5ff", pressed: str = "#dbeafe", **kwargs: Any) -> tk.Button:
    normal = str(kwargs.get("bg", "#ffffff"))
    kwargs.setdefault("activebackground", pressed)
    kwargs.setdefault("relief", tk.FLAT)
    kwargs.setdefault("bd", 0)
    button = tk.Button(parent, **kwargs)

    def paint(color: str) -> None:
        animate_background((button,), color, steps=4, delay=10)

    def on_enter(_event: tk.Event) -> None:
        paint(hover)

    def on_leave(_event: tk.Event) -> None:
        paint(normal)

    def on_press(_event: tk.Event) -> None:
        paint(pressed)

    def on_release(event: tk.Event) -> None:
        inside = 0 <= event.x <= button.winfo_width() and 0 <= event.y <= button.winfo_height()
        paint(hover if inside else normal)

    button.bind("<Enter>", on_enter, add=True)
    button.bind("<Leave>", on_leave, add=True)
    button.bind("<ButtonPress-1>", on_press, add=True)
    button.bind("<ButtonRelease-1>", on_release, add=True)
    return button


class ModernScrollbar(tk.Canvas):
    def __init__(self, parent: tk.Widget, orient: str, command: Any) -> None:
        self.orient = orient
        self.command = command
        self.first = 0.0
        self.last = 1.0
        self.thumb_start = 0.0
        self.thumb_end = 1.0
        self.drag_offset = 0.0
        self.hovered = False
        self.pressed = False
        width = 16 if orient == tk.VERTICAL else 1
        height = 1 if orient == tk.VERTICAL else 16
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=PANEL,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.bind("<Configure>", lambda _event: self._redraw())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._jump_or_drag)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)

    def set(self, first: str, last: str) -> None:
        self.first = max(0.0, min(1.0, float(first)))
        self.last = max(self.first, min(1.0, float(last)))
        self._redraw()

    def _track_length(self) -> int:
        return max(1, self.winfo_height() if self.orient == tk.VERTICAL else self.winfo_width())

    def _redraw(self) -> None:
        self.delete("all")
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        pad = 3
        track_color = "#eef3f8"
        thumb_color = "#7f9bbd" if self.pressed else "#9fb2c9" if self.hovered else "#b8c6d8"
        active_color = "#6d86a8" if self.pressed else "#8ba3c0" if self.hovered else "#9fb2c9"

        if self.orient == tk.VERTICAL:
            length = max(1, height - pad * 2)
            thumb_len = max(34, int(length * (self.last - self.first)))
            max_start = pad + max(0, length - thumb_len)
            start = pad + int(max(0.0, min(1.0, self.first)) * length)
            start = min(start, max_start)
            end = min(height - pad, start + thumb_len)
            self.thumb_start, self.thumb_end = start, end
            self.create_rectangle(width // 2 - 3, pad, width // 2 + 3, height - pad, fill=track_color, outline=track_color)
            self.create_rectangle(width // 2 - 4, start, width // 2 + 4, end, fill=thumb_color, outline=active_color)
        else:
            length = max(1, width - pad * 2)
            thumb_len = max(34, int(length * (self.last - self.first)))
            max_start = pad + max(0, length - thumb_len)
            start = pad + int(max(0.0, min(1.0, self.first)) * length)
            start = min(start, max_start)
            end = min(width - pad, start + thumb_len)
            self.thumb_start, self.thumb_end = start, end
            self.create_rectangle(pad, height // 2 - 3, width - pad, height // 2 + 3, fill=track_color, outline=track_color)
            self.create_rectangle(start, height // 2 - 4, end, height // 2 + 4, fill=thumb_color, outline=active_color)

    def _jump_or_drag(self, event: tk.Event) -> None:
        self.pressed = True
        self._redraw()
        position = event.y if self.orient == tk.VERTICAL else event.x
        if self.thumb_start <= position <= self.thumb_end:
            self.drag_offset = position - self.thumb_start
        else:
            self.drag_offset = max(0.0, (self.thumb_end - self.thumb_start) / 2)
            self._move_thumb(position)

    def _drag(self, event: tk.Event) -> None:
        position = event.y if self.orient == tk.VERTICAL else event.x
        self._move_thumb(position)

    def _enter(self, _event: tk.Event) -> None:
        self.hovered = True
        self._redraw()

    def _leave(self, _event: tk.Event) -> None:
        self.hovered = False
        self.pressed = False
        self._redraw()

    def _release(self, _event: tk.Event) -> None:
        self.pressed = False
        self._redraw()

    def _move_thumb(self, position: float) -> None:
        pad = 3
        length = max(1, self._track_length() - pad * 2)
        thumb_len = max(34, int(length * (self.last - self.first)))
        movable = max(1, length - thumb_len)
        start = max(pad, min(pad + movable, position - self.drag_offset))
        fraction = (start - pad) / movable
        self.command("moveto", fraction)


class DatePicker(tk.Toplevel):
    def __init__(self, parent: tk.Tk, target: tk.StringVar, on_month_selected: Any | None = None) -> None:
        super().__init__(parent)
        self.parent_app = parent
        self.target = target
        self.on_month_selected = on_month_selected
        self.title("选择日期")
        self.resizable(False, False)
        self.configure(bg=PANEL)
        if ICON_ICO.exists():
            try:
                self.iconbitmap(default=str(ICON_ICO))
            except tk.TclError:
                pass
        try:
            current = datetime.strptime(target.get(), "%Y/%m/%d").date()
        except ValueError:
            current = date.today()
        self.year = current.year
        self.month = current.month
        body = tk.Frame(self, bg=PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        self.quick_frame = tk.Frame(body, bg=SOFT, highlightthickness=1, highlightbackground=LINE)
        self.quick_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        self._build_quick_panel()

        calendar_frame = tk.Frame(body, bg=PANEL)
        calendar_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.header = tk.Frame(calendar_frame, bg=PANEL)
        self.header.pack(fill=tk.X, pady=(0, 8))
        motion_button(
            self.header,
            text="<",
            command=self._prev_month,
            bg=SOFT,
            fg=INK,
            activebackground="#eaf1ff",
            relief=tk.FLAT,
            width=3,
            cursor="hand2",
        ).pack(side=tk.LEFT)
        self.title_var = tk.StringVar()
        ttk.Label(self.header, textvariable=self.title_var, style="Panel.TLabel", font=("Microsoft YaHei UI", 11, "bold")).pack(side=tk.LEFT, expand=True)
        motion_button(
            self.header,
            text=">",
            command=self._next_month,
            bg=SOFT,
            fg=INK,
            activebackground="#eaf1ff",
            relief=tk.FLAT,
            width=3,
            cursor="hand2",
        ).pack(side=tk.RIGHT)
        self.grid_frame = tk.Frame(calendar_frame, bg=PANEL)
        self.grid_frame.pack()
        self._render()
        self.transient(parent)
        self.grab_set()
        center_window(self)

    def _build_quick_panel(self) -> None:
        tk.Label(self.quick_frame, text="快速选择", bg=SOFT, fg=INK, font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W, padx=12, pady=(12, 8))
        year_row = tk.Frame(self.quick_frame, bg=SOFT)
        year_row.pack(fill=tk.X, padx=10)
        motion_button(
            year_row,
            text="<",
            command=lambda: self._change_quick_year(-1),
            bg="#ffffff",
            fg=INK,
            activebackground="#eaf1ff",
            relief=tk.FLAT,
            width=3,
            cursor="hand2",
        ).pack(side=tk.LEFT)
        self.quick_year_var = tk.StringVar(value=str(self.year))
        tk.Label(year_row, textvariable=self.quick_year_var, bg=SOFT, fg=INK, font=("Microsoft YaHei UI", 10, "bold"), width=6).pack(side=tk.LEFT, padx=4)
        motion_button(
            year_row,
            text=">",
            command=lambda: self._change_quick_year(1),
            bg="#ffffff",
            fg=INK,
            activebackground="#eaf1ff",
            relief=tk.FLAT,
            width=3,
            cursor="hand2",
        ).pack(side=tk.LEFT)

        self.month_buttons: list[tk.Button] = []
        month_box = tk.Frame(self.quick_frame, bg=SOFT)
        month_box.pack(fill=tk.X, padx=10, pady=(10, 12))
        for month in range(1, 13):
            button = motion_button(
                month_box,
                text=f"{month:02d} 月",
                command=lambda value=month: self._select_month(value),
                bg="#ffffff",
                fg=INK,
                activebackground="#dbeafe",
                relief=tk.FLAT,
                font=("Microsoft YaHei UI", 9),
                width=10,
                cursor="hand2",
            )
            button.pack(fill=tk.X, pady=1)
            self.month_buttons.append(button)

    def _change_quick_year(self, delta: int) -> None:
        self.year += delta
        self.quick_year_var.set(str(self.year))
        self._render()

    def _select_month(self, month: int) -> None:
        self.month = month
        self.quick_year_var.set(str(self.year))
        first_day = date(self.year, self.month, 1)
        last_day = date(self.year, self.month, calendar.monthrange(self.year, self.month)[1])
        if hasattr(self.parent_app, "start_var") and hasattr(self.parent_app, "end_var"):
            self.parent_app.start_var.set(first_day.strftime("%Y/%m/%d"))
            self.parent_app.end_var.set(last_day.strftime("%Y/%m/%d"))
        else:
            self.target.set(first_day.strftime("%Y/%m/%d"))
        self.destroy()
        if self.on_month_selected:
            self.parent_app.after_idle(self.on_month_selected)

    def _render(self) -> None:
        for child in self.grid_frame.winfo_children():
            child.destroy()
        self.title_var.set(f"{self.year} 年 {self.month:02d} 月")
        for col, text in enumerate(["一", "二", "三", "四", "五", "六", "日"]):
            tk.Label(self.grid_frame, text=text, bg=PANEL, fg=MUTED, font=("Microsoft YaHei UI", 9), width=4).grid(row=0, column=col, padx=1, pady=(0, 4))
        month = calendar.monthcalendar(self.year, self.month)
        for row_index, week in enumerate(month, start=1):
            for col, day in enumerate(week):
                if day == 0:
                    tk.Label(self.grid_frame, text="", bg=PANEL, width=4).grid(row=row_index, column=col, padx=1, pady=1)
                    continue
                motion_button(
                    self.grid_frame,
                    text=str(day),
                    command=lambda value=day: self._select(value),
                    bg="#ffffff",
                    fg=INK,
                    activebackground="#eaf1ff",
                    relief=tk.FLAT,
                    font=("Microsoft YaHei UI", 9),
                    width=4,
                    cursor="hand2",
                ).grid(row=row_index, column=col, padx=1, pady=1)

    def _select(self, day: int) -> None:
        self.target.set(date(self.year, self.month, day).strftime("%Y/%m/%d"))
        self.destroy()

    def _prev_month(self) -> None:
        self.month -= 1
        if self.month == 0:
            self.month = 12
            self.year -= 1
            self.quick_year_var.set(str(self.year))
        self._render()

    def _next_month(self) -> None:
        self.month += 1
        if self.month == 13:
            self.month = 1
            self.year += 1
            self.quick_year_var.set(str(self.year))
        self._render()


class FileTime(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


class Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", FileTime),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def load_saved_credentials() -> tuple[str, str]:
    if sys.platform != "win32":
        return "", ""
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi32.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(Credential))]
        advapi32.CredReadW.restype = wintypes.BOOL
        advapi32.CredFree.argtypes = [ctypes.c_void_p]
        advapi32.CredFree.restype = None

        credential_ptr = ctypes.POINTER(Credential)()
        if not advapi32.CredReadW(CREDENTIAL_TARGET, 1, 0, ctypes.byref(credential_ptr)):
            return "", ""
        try:
            credential = credential_ptr.contents
            username = credential.UserName or ""
            password_bytes = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            password = password_bytes.decode("utf-16-le") if password_bytes else ""
            return username, password
        finally:
            advapi32.CredFree(credential_ptr)
    except Exception:
        return "", ""


def save_credentials(username: str, password: str) -> None:
    if sys.platform != "win32":
        return
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi32.CredWriteW.argtypes = [ctypes.POINTER(Credential), wintypes.DWORD]
        advapi32.CredWriteW.restype = wintypes.BOOL

        password_bytes = password.encode("utf-16-le")
        blob = ctypes.create_string_buffer(password_bytes)
        credential = Credential()
        credential.Type = 1
        credential.TargetName = CREDENTIAL_TARGET
        credential.CredentialBlobSize = len(password_bytes)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_byte))
        credential.Persist = 2
        credential.UserName = username
        advapi32.CredWriteW(ctypes.byref(credential), 0)
    except Exception:
        pass


def disable_ime_for_widget(entry: tk.Widget) -> None:
    if sys.platform != "win32":
        return
    try:
        imm32 = ctypes.WinDLL("imm32", use_last_error=True)
        imm32.ImmAssociateContext.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        imm32.ImmAssociateContext.restype = ctypes.c_void_p
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetKeyboardLayout.argtypes = [ctypes.c_uint]
        user32.GetKeyboardLayout.restype = ctypes.c_void_p
        user32.LoadKeyboardLayoutW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint]
        user32.LoadKeyboardLayoutW.restype = ctypes.c_void_p
        user32.ActivateKeyboardLayout.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        user32.ActivateKeyboardLayout.restype = ctypes.c_void_p
    except Exception:
        return

    original_context: dict[str, int | None] = {"value": None}
    original_layout: dict[str, int | None] = {"value": None}

    def disable(_event: tk.Event | None = None) -> None:
        try:
            current_layout = user32.GetKeyboardLayout(0)
            if original_layout["value"] is None and current_layout:
                original_layout["value"] = int(current_layout)
            english_layout = user32.LoadKeyboardLayoutW("00000409", 1)
            if english_layout:
                user32.ActivateKeyboardLayout(ctypes.c_void_p(int(english_layout)), 0)
            old_context = imm32.ImmAssociateContext(ctypes.c_void_p(entry.winfo_id()), ctypes.c_void_p(0))
            if original_context["value"] is None and old_context:
                original_context["value"] = int(old_context)
        except Exception:
            pass

    def restore(_event: tk.Event | None = None) -> None:
        value = original_context["value"]
        if value:
            try:
                imm32.ImmAssociateContext(ctypes.c_void_p(entry.winfo_id()), ctypes.c_void_p(value))
            except Exception:
                pass
        layout = original_layout["value"]
        if layout:
            try:
                user32.ActivateKeyboardLayout(ctypes.c_void_p(layout), 0)
            except Exception:
                pass

    entry.bind("<FocusIn>", disable, add=True)
    entry.bind("<FocusOut>", restore, add=True)
    entry.after_idle(disable)


def install_ascii_password_input(entry: tk.Entry) -> None:
    def on_key(event: tk.Event) -> str | None:
        if event.keysym in {"BackSpace", "Delete", "Left", "Right", "Home", "End", "Tab", "Return"}:
            return None
        char = ascii_char_from_event(event)
        if not char:
            return None
        if entry.selection_present():
            entry.delete(tk.SEL_FIRST, tk.SEL_LAST)
        entry.insert(tk.INSERT, char)
        return "break"

    entry.bind("<KeyPress>", on_key, add=False)


def ascii_char_from_event(event: tk.Event) -> str:
    keysym = str(event.keysym)
    state = int(event.state)
    shifted = bool(state & 0x0001)
    if len(keysym) == 1 and 32 <= ord(keysym) <= 126:
        return keysym.upper() if shifted and keysym.isalpha() else keysym
    if keysym.startswith("KP_") and keysym[3:].isdigit():
        return keysym[3:]
    normal = {
        "space": " ",
        "minus": "-",
        "equal": "=",
        "bracketleft": "[",
        "bracketright": "]",
        "backslash": "\\",
        "semicolon": ";",
        "apostrophe": "'",
        "comma": ",",
        "period": ".",
        "slash": "/",
        "grave": "`",
    }
    shifted_map = {
        "1": "!",
        "2": "@",
        "3": "#",
        "4": "$",
        "5": "%",
        "6": "^",
        "7": "&",
        "8": "*",
        "9": "(",
        "0": ")",
        "minus": "_",
        "equal": "+",
        "bracketleft": "{",
        "bracketright": "}",
        "backslash": "|",
        "semicolon": ":",
        "apostrophe": '"',
        "comma": "<",
        "period": ">",
        "slash": "?",
        "grave": "~",
    }
    if shifted and keysym in shifted_map:
        return shifted_map[keysym]
    return normal.get(keysym, "")


def format_release_date(value: str) -> str:
    if not value:
        return "未知发布时间"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y/%m/%d")
    except ValueError:
        return value[:10] or "未知发布时间"


def format_download_progress(written: int, total: int) -> str:
    if total > 0:
        percent = min(100, int(written * 100 / total))
        return f"正在下载更新... {percent}%"
    size_mb = written / 1024 / 1024
    return f"正在下载更新... {size_mb:.1f} MB"


def row_background(tags: list[str] | tuple[str, ...], selected: bool = False) -> str:
    if selected:
        return DETAIL_SELECTED_BG
    if "hover_negative" in tags:
        return "#ffe4e8"
    if "hover_positive" in tags:
        return "#c6ebd2"
    if "hover" in tags:
        return "#eaf1ff"
    if "negative" in tags:
        return NEGATIVE_ROW_BG
    if "positive" in tags:
        return POSITIVE_ROW_BG
    if "even" in tags:
        return "#f8fbff"
    return "#ffffff"

def create_rest_day_icon() -> tk.PhotoImage:
    if REST_DAY_ICON_PNG.exists():
        try:
            return tk.PhotoImage(file=str(REST_DAY_ICON_PNG))
        except tk.TclError:
            pass
    image = tk.PhotoImage(width=21, height=22)
    try:
        for y in range(image.height()):
            for x in range(image.width()):
                image.transparency_set(x, y, True)
    except tk.TclError:
        pass
    for y, row in enumerate(REST_DAY_ICON_PATTERN, start=1):
        for x, point in enumerate(row, start=1):
            if point == "#":
                image.put(REST_DAY_ICON_COLOR, (x + 1, y + 1))
                try:
                    image.transparency_set(x + 1, y + 1, False)
                except tk.TclError:
                    pass
    return image


def format_detail_date(value: str) -> str:
    weekdays = ("\u661f\u671f\u4e00", "\u661f\u671f\u4e8c", "\u661f\u671f\u4e09", "\u661f\u671f\u56db", "\u661f\u671f\u4e94", "\u661f\u671f\u516d", "\u661f\u671f\u65e5")
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(value, fmt)
            return f"{parsed.strftime('%Y-%m-%d')} {weekdays[parsed.weekday()]}"
        except ValueError:
            continue
    return value.replace("/", "-")


def should_show_rest_icon(date_type: str) -> bool:
    return bool(date_type and date_type.strip() != "\u5de5\u4f5c\u65e5")


def validate_date_range(start_date: str, end_date: str) -> bool:
    try:
        start = datetime.strptime(start_date, "%Y/%m/%d")
        end = datetime.strptime(end_date, "%Y/%m/%d")
    except ValueError:
        messagebox.showwarning("格式错误", "日期请使用 YYYY/MM/DD，或点击日期框选择。")
        return False
    if end < start:
        messagebox.showwarning("日期错误", "结束日期不能早于开始日期。")
        return False
    return True


def enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def center_window(window: tk.Toplevel | tk.Tk) -> None:
    window.update_idletasks()
    width = window.winfo_width()
    height = window.winfo_height()
    if width <= 1 or height <= 1:
        geometry = window.geometry().split("+")[0]
        width, height = [int(part) for part in geometry.split("x")]

    left, top, right, bottom = get_work_area(window)
    outer_width = max(width, window.winfo_rootx() - window.winfo_x() + width)
    outer_height = max(height, window.winfo_rooty() - window.winfo_y() + height)
    x = left + max(0, (right - left - outer_width) // 2)
    y = top + max(0, (bottom - top - outer_height) // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


def get_work_area(window: tk.Toplevel | tk.Tk) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    try:
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    return 0, 0, window.winfo_screenwidth(), window.winfo_screenheight()


def current_month_range() -> tuple[str, str]:
    today = date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    start = today.replace(day=1)
    end = today.replace(day=last_day)
    return start.strftime("%Y/%m/%d"), end.strftime("%Y/%m/%d")


def load_logo_image(size: int) -> tk.PhotoImage:
    if ICON_PNG.exists():
        try:
            image = tk.PhotoImage(file=str(ICON_PNG))
            if image.width() > size:
                factor = max(1, round(image.width() / size))
                return image.subsample(factor, factor)
            if image.width() < size:
                factor = max(1, size // image.width())
                return image.zoom(factor, factor)
            return image
        except tk.TclError:
            pass
    return make_logo_image(size)


def make_logo_image(size: int) -> tk.PhotoImage:
    image = tk.PhotoImage(width=size, height=size)
    cx = size / 2
    cy = size / 2
    radius = size * 0.44
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            dist = (dx * dx + dy * dy) ** 0.5
            if dist <= radius:
                mix = (x + y) / (size * 2)
                r = int(37 + 20 * mix)
                g = int(99 + 85 * mix)
                b = int(235 - 35 * mix)
                if dist > radius - 1.5:
                    r, g, b = 20, 184, 166
                image.put(f"#{r:02x}{g:02x}{b:02x}", (x, y))
    for x, y in [(20, 10), (29, 10), (24, 22), (33, 22), (18, 40), (22, 27), (14, 27)]:
        draw_disc(image, x * size // 48, y * size // 48, max(1, size // 18), "#ffffff")
    return image


def draw_disc(image: tk.PhotoImage, cx: int, cy: int, radius: int, color: str) -> None:
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if 0 <= x < image.width() and 0 <= y < image.height() and (x - cx) ** 2 + (y - cy) ** 2 <= radius**2:
                image.put(color, (x, y))


def main() -> int:
    app = AttendanceApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
