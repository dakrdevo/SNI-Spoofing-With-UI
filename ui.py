import asyncio
import json
import os
import socket
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import time
import math

from utils.network_tools import get_default_interface_ipv4


def get_exe_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(get_exe_dir(), 'config.json')
CONFIGS_DIR = os.path.join(get_exe_dir(), 'configs')

COLORS = {
    "bg": "#0a0a0f",
    "surface": "#111118",
    "surface2": "#181820",
    "surface3": "#1e1e28",
    "surface4": "#242430",
    "border": "#252530",
    "border_bright": "#3a2545",
    "accent": "#e040a0",
    "accent_hover": "#c0307a",
    "accent_dim": "#6a1545",
    "accent2": "#ff7dd4",
    "accent3": "#ff3090",
    "success": "#20c55a",
    "error": "#ef4444",
    "warning": "#f59e0b",
    "text": "#f0e8f4",
    "text_muted": "#584868",
    "text_dim": "#8a7898",
    "glow": "#e040a033",
    "glow2": "#e040a011",
}

ADVANCED_KEYS = [
    ("fragment", "fragment", False, "bool"),
    ("FRAGMENT_STRATEGY", "Fragment Strategy", "sni_split", "str"),
    ("FRAGMENT_DELAY", "Fragment Delay", 0.1, "float"),
    ("USE_TTL_TRICK", "Use TTL Trick", False, "bool"),
    ("FAKE_SNI_METHOD", "Fake SNI Method", "prefix_fake", "str"),
    ("SCANNER_ENABLED", "Scanner Enabled", False, "bool"),
    ("SCANNER_COUNT", "Scanner Count", 100, "int"),
    ("SCANNER_CONCURRENCY", "Scanner Concurrency", 16, "int"),
    ("SCANNER_TIMEOUT", "Scanner Timeout", 4.0, "float"),
    ("SCANNER_TEST_DOWNLOAD", "Scanner Test Download", False, "bool"),
    ("SCANNER_RESCAN_INTERVAL", "Rescan Interval", 0, "int"),
    ("SCANNER_CACHE", "Scanner Cache", "", "str"),
    ("SCANNER_TOP_N", "Top N Results", 10, "int"),
    ("SCANNER_CUSTOM_RANGES", "Custom Ranges (comma separated)", "", "list"),
    ("SNI_DOMAINS", "SNI Domains (comma separated)", "", "list"),
]


class AnimatedDot(tk.Canvas):
    def __init__(self, parent, size=10, bg_color=None, **kwargs):
        bg = bg_color or COLORS["surface"]
        super().__init__(parent, width=size, height=size, bg=bg,
                         highlightthickness=0, **kwargs)
        self.size = size
        self._color = COLORS["text_muted"]
        self._pulse = 0
        self._animating = False
        self._ring_alpha = 0.0
        self._ring_growing = True
        self._draw()

    def _draw(self):
        self.delete("all")
        s = self.size
        pad = 2
        if self._animating and self._ring_alpha > 0:
            ring_pad = max(0, pad - 2)
            ra = int(self._ring_alpha * 180)
            rc = int(int(COLORS["accent"][1:3], 16))
            gc = int(int(COLORS["accent"][3:5], 16))
            bc = int(int(COLORS["accent"][5:7], 16))
            ring_color = f"#{min(255,rc):02x}{min(255,gc):02x}{min(255,bc):02x}"
            self.create_oval(ring_pad, ring_pad, s - ring_pad, s - ring_pad,
                             fill="", outline=ring_color, width=1)
        self.create_oval(pad, pad, s - pad, s - pad, fill=self._color, outline="")

    def set_color(self, color):
        self._color = color
        self._draw()

    def start_pulse(self, color):
        self._color = color
        self._animating = True
        self._pulse_step()

    def _pulse_step(self):
        if not self._animating:
            return
        self._pulse = (self._pulse + 1) % 40
        t = self._pulse / 40.0
        wave = 0.5 + 0.5 * math.sin(t * 2 * math.pi)
        alpha = 0.35 + 0.65 * wave
        r = int(int(COLORS["accent"][1:3], 16) * alpha)
        g = int(int(COLORS["accent"][3:5], 16) * alpha)
        b = int(int(COLORS["accent"][5:7], 16) * alpha)
        r = max(0, min(255, r))
        g = max(0, min(255, g))
        b = max(0, min(255, b))
        self._color = f"#{r:02x}{g:02x}{b:02x}"
        if self._ring_growing:
            self._ring_alpha = min(1.0, self._ring_alpha + 0.08)
            if self._ring_alpha >= 1.0:
                self._ring_growing = False
        else:
            self._ring_alpha = max(0.0, self._ring_alpha - 0.06)
            if self._ring_alpha <= 0.0:
                self._ring_growing = True
        self._draw()
        self.after(50, self._pulse_step)

    def stop_pulse(self, color):
        self._animating = False
        self._ring_alpha = 0.0
        self._color = color
        self._draw()


class GlowButton(tk.Frame):
    def __init__(self, parent, text, command=None, style="primary", **kwargs):
        bg = COLORS["surface2"]
        super().__init__(parent, bg=bg, **kwargs)
        self._cmd = command
        self._style = style
        self._hover = False
        self._press_anim = 0
        self._animating = False

        if style == "primary":
            self._fg = "white"
            self._bg = COLORS["accent"]
            self._bg_hover = COLORS["accent_hover"]
            self._bg_press = COLORS["accent3"]
        else:
            self._fg = COLORS["text_dim"]
            self._bg = COLORS["surface3"]
            self._bg_hover = COLORS["surface4"]
            self._bg_press = COLORS["border"]

        self._canvas = tk.Canvas(self, height=38, bg=COLORS["surface2"],
                                 highlightthickness=0, cursor="hand2")
        self._canvas.pack(fill=tk.X)
        self._text = text
        self._font = ("Segoe UI", 10, "bold") if style == "primary" else ("Segoe UI", 10)
        self._draw(self._bg)

        self._canvas.bind("<Enter>", self._on_enter)
        self._canvas.bind("<Leave>", self._on_leave)
        self._canvas.bind("<Button-1>", self._on_click)
        self._canvas.bind("<Configure>", lambda e: self._draw(self._current_bg()))

    def _current_bg(self):
        if self._hover:
            return self._bg_hover
        return self._bg

    def _draw(self, bg):
        self._canvas.delete("all")
        w = self._canvas.winfo_width() or 100
        h = self._canvas.winfo_height() or 38
        r = 6
        self._canvas.create_rectangle(0, 0, w, h, fill=bg, outline="", width=0)
        self._canvas.create_text(w // 2, h // 2, text=self._text,
                                 font=self._font, fill=self._fg)

    def _on_enter(self, e):
        self._hover = True
        self._draw(self._bg_hover)

    def _on_leave(self, e):
        self._hover = False
        self._draw(self._bg)

    def _on_click(self, e):
        self._draw(self._bg_press)
        self.after(120, lambda: self._draw(self._bg_hover if self._hover else self._bg))
        if self._cmd:
            self._cmd()

    def config_text(self, text):
        self._text = text
        self._draw(self._current_bg())

    def config_style(self, style):
        self._style = style
        if style == "primary":
            self._fg = "white"
            self._bg = COLORS["accent"]
            self._bg_hover = COLORS["accent_hover"]
            self._bg_press = COLORS["accent3"]
        elif style == "danger":
            self._fg = "white"
            self._bg = COLORS["error"]
            self._bg_hover = "#c53030"
            self._bg_press = "#a52020"
        else:
            self._fg = COLORS["text_dim"]
            self._bg = COLORS["surface3"]
            self._bg_hover = COLORS["surface4"]
            self._bg_press = COLORS["border"]
        self._draw(self._current_bg())

    def set_state(self, state):
        if state == tk.DISABLED:
            self._canvas.config(cursor="")
            self._fg = COLORS["text_muted"]
            self._draw(COLORS["surface2"])
        else:
            self._canvas.config(cursor="hand2")
            if self._style == "primary":
                self._fg = "white"
            else:
                self._fg = COLORS["text_dim"]
            self._draw(self._current_bg())


class StatusBadge(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=COLORS["surface"], **kwargs)
        self._outer = tk.Frame(self, bg=COLORS["surface3"], padx=10, pady=4)
        self._outer.pack()
        self.dot = AnimatedDot(self._outer, size=9, bg_color=COLORS["surface3"])
        self.dot.pack(side=tk.LEFT, padx=(0, 7))
        self.label = tk.Label(self._outer, text="idle", font=("Segoe UI", 8, "bold"),
                              fg=COLORS["text_muted"], bg=COLORS["surface3"])
        self.label.pack(side=tk.LEFT)

    def set_state(self, state):
        states = {
            "idle": (COLORS["text_muted"], "idle", None),
            "connecting": (COLORS["warning"], "connecting...", COLORS["warning"]),
            "running": (COLORS["success"], "running", None),
            "error": (COLORS["error"], "error", None),
        }
        color, text, pulse = states.get(state, states["idle"])
        self.dot.stop_pulse(color)
        if pulse:
            self.dot.start_pulse(pulse)
        self.label.config(text=text, fg=color)


class StyledEntry(tk.Frame):
    def __init__(self, parent, label, value="", **kwargs):
        super().__init__(parent, bg=COLORS["surface"], **kwargs)
        self.label_widget = tk.Label(self, text=label, font=("Segoe UI", 7, "bold"),
                                     fg=COLORS["text_muted"], bg=COLORS["surface"],
                                     anchor="w")
        self.label_widget.pack(anchor="w", padx=10, pady=(8, 3))

        self._border_frame = tk.Frame(self, bg=COLORS["border"], padx=1, pady=1)
        self._border_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        inner = tk.Frame(self._border_frame, bg=COLORS["surface2"])
        inner.pack(fill=tk.X)

        self.entry = tk.Entry(inner, font=("Segoe UI", 10), fg=COLORS["text"],
                              bg=COLORS["surface2"], insertbackground=COLORS["accent"],
                              relief=tk.FLAT, bd=5, width=30)
        self.entry.pack(fill=tk.X, padx=2)
        if value:
            self.entry.insert(0, str(value))

        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)

    def _on_focus_in(self, e):
        self._border_frame.config(bg=COLORS["accent"])

    def _on_focus_out(self, e):
        self._border_frame.config(bg=COLORS["border"])

    def get(self):
        return self.entry.get().strip()

    def set(self, value):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, str(value))

    def disable(self):
        self.entry.config(state=tk.DISABLED, fg=COLORS["text_muted"])

    def enable(self):
        self.entry.config(state=tk.NORMAL, fg=COLORS["text"])


class PinkCheckbox(tk.Frame):
    def __init__(self, parent, label, var=None, command=None, bg=None, **kwargs):
        _bg = bg or COLORS["surface2"]
        super().__init__(parent, bg=_bg, **kwargs)
        self.var = var if var is not None else tk.BooleanVar()
        self._cmd = command
        self._bg = _bg

        self._box = tk.Canvas(self, width=15, height=15, bg=_bg,
                              highlightthickness=0, cursor="hand2")
        self._box.pack(side=tk.LEFT, padx=(0, 6))
        self._lbl = tk.Label(self, text=label, font=("Segoe UI", 9),
                             fg=COLORS["text_dim"], bg=_bg, cursor="hand2")
        self._lbl.pack(side=tk.LEFT)

        self._box.bind("<Button-1>", self._toggle)
        self._lbl.bind("<Button-1>", self._toggle)
        self.var.trace_add("write", lambda *a: self._redraw())
        self._redraw()

    def _toggle(self, e=None):
        self.var.set(not self.var.get())
        if self._cmd:
            self._cmd()

    def _redraw(self):
        self._box.delete("all")
        if self.var.get():
            self._box.create_rectangle(1, 1, 14, 14, fill=COLORS["accent"],
                                       outline=COLORS["accent"], width=1)
            self._box.create_line(3, 7, 6, 11, fill="white", width=2)
            self._box.create_line(6, 11, 12, 3, fill="white", width=2)
        else:
            self._box.create_rectangle(1, 1, 14, 14, fill=COLORS["surface"],
                                       outline=COLORS["border"], width=1)


class LogPanel(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=COLORS["surface"], **kwargs)
        self._pulse_phase = 0
        self._pulse_active = False

        header = tk.Frame(self, bg=COLORS["surface"])
        header.pack(fill=tk.X, padx=14, pady=(12, 6))

        dot_canvas = tk.Canvas(header, width=8, height=8, bg=COLORS["surface"],
                               highlightthickness=0)
        dot_canvas.pack(side=tk.LEFT, padx=(0, 8), pady=2)
        dot_canvas.create_oval(1, 1, 7, 7, fill=COLORS["accent"], outline="")

        tk.Label(header, text="لاگ", font=("Segoe UI", 9, "bold"),
                 fg=COLORS["accent2"], bg=COLORS["surface"]).pack(side=tk.LEFT)

        self.clear_btn = tk.Label(header, text="پاک کردن", font=("Segoe UI", 8),
                                  fg=COLORS["text_muted"], bg=COLORS["surface"],
                                  cursor="hand2")
        self.clear_btn.pack(side=tk.RIGHT)
        self.clear_btn.bind("<Button-1>", lambda e: self.clear())
        self.clear_btn.bind("<Enter>", lambda e: self.clear_btn.config(fg=COLORS["accent"]))
        self.clear_btn.bind("<Leave>", lambda e: self.clear_btn.config(fg=COLORS["text_muted"]))

        border_outer = tk.Frame(self, bg=COLORS["border"], padx=1, pady=1)
        border_outer.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        inner = tk.Frame(border_outer, bg="#060610")
        inner.pack(fill=tk.BOTH, expand=True)

        self.text = tk.Text(inner, font=("Cascadia Code", 8), fg=COLORS["text_dim"],
                            bg="#060610", relief=tk.FLAT, bd=6, wrap=tk.WORD,
                            state=tk.DISABLED, insertbackground=COLORS["accent"],
                            selectbackground=COLORS["accent_dim"])
        scroll = tk.Scrollbar(inner, command=self.text.yview, bg=COLORS["surface2"],
                              troughcolor="#060610", width=5, relief=tk.FLAT,
                              activebackground=COLORS["accent_dim"])
        self.text.config(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.pack(fill=tk.BOTH, expand=True)

        self.text.tag_config("info", foreground=COLORS["text_dim"])
        self.text.tag_config("success", foreground=COLORS["success"])
        self.text.tag_config("error", foreground=COLORS["error"])
        self.text.tag_config("warning", foreground=COLORS["warning"])
        self.text.tag_config("time", foreground=COLORS["accent_dim"])

    def log(self, message, level="info"):
        self.text.config(state=tk.NORMAL)
        ts = time.strftime("%H:%M:%S")
        self.text.insert(tk.END, f"[{ts}] ", "time")
        self.text.insert(tk.END, message + "\n", level)
        self.text.see(tk.END)
        self.text.config(state=tk.DISABLED)

    def clear(self):
        self.text.config(state=tk.NORMAL)
        self.text.delete(1.0, tk.END)
        self.text.config(state=tk.DISABLED)


class StatCard(tk.Frame):
    def __init__(self, parent, label, value="0", **kwargs):
        super().__init__(parent, bg=COLORS["surface2"], **kwargs)
        self.configure(padx=12, pady=10)

        self._label_text = label
        tk.Label(self, text=label, font=("Segoe UI", 7),
                 fg=COLORS["text_muted"], bg=COLORS["surface2"]).pack(anchor="w")

        self._val_frame = tk.Frame(self, bg=COLORS["surface2"])
        self._val_frame.pack(anchor="w", fill=tk.X)

        self.value_lbl = tk.Label(self._val_frame, text=value,
                                  font=("Segoe UI", 14, "bold"),
                                  fg=COLORS["accent2"], bg=COLORS["surface2"])
        self.value_lbl.pack(side=tk.LEFT, anchor="w")

        self._accent_line = tk.Frame(self, bg=COLORS["accent_dim"], height=1)
        self._accent_line.pack(fill=tk.X, pady=(6, 0))

    def set_value(self, val):
        self.value_lbl.config(text=str(val))


class PlusMenu(tk.Frame):
    def __init__(self, parent, on_import, on_show_configs, **kwargs):
        super().__init__(parent, bg=COLORS["surface"], **kwargs)
        self._on_import = on_import
        self._on_show_configs = on_show_configs
        self._popup = None
        self._rotate = 0
        self._rotating = False

        self._btn_canvas = tk.Canvas(self, width=28, height=28, bg=COLORS["surface"],
                                     highlightthickness=0, cursor="hand2")
        self._btn_canvas.pack(side=tk.LEFT)
        self._draw_btn(False)

        self._btn_canvas.bind("<Button-1>", self._toggle)
        self._btn_canvas.bind("<Enter>", lambda e: self._draw_btn(True))
        self._btn_canvas.bind("<Leave>", lambda e: self._draw_btn(self._popup is not None))

    def _draw_btn(self, hovered):
        self._btn_canvas.delete("all")
        c = COLORS["accent2"] if hovered else COLORS["accent"]
        bg = COLORS["surface3"] if hovered else COLORS["surface2"]
        self._btn_canvas.create_rectangle(0, 0, 28, 28, fill=bg, outline="", width=0)
        self._btn_canvas.create_text(14, 14, text="+", font=("Segoe UI", 14, "bold"),
                                     fill=c)

    def _toggle(self, e=None):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            self._draw_btn(False)
            return
        self._show_popup()

    def _show_popup(self):
        self._popup = tk.Toplevel(self)
        self._popup.overrideredirect(True)
        self._popup.configure(bg=COLORS["border"])
        self._popup.attributes("-alpha", 0.0)

        self.update_idletasks()
        bx = self._btn_canvas.winfo_rootx()
        by = self._btn_canvas.winfo_rooty() + self._btn_canvas.winfo_height() + 6

        outer = tk.Frame(self._popup, bg=COLORS["border"], padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(outer, bg=COLORS["surface3"])
        inner.pack(fill=tk.BOTH, expand=True)

        items = [
            ("  وارد کردن کانفیگ از JSON", self._do_import),
            ("  کانفیگ‌های ذخیره شده", self._do_configs),
        ]
        for text, cmd in items:
            item_frame = tk.Frame(inner, bg=COLORS["surface3"])
            item_frame.pack(fill=tk.X)

            indicator = tk.Frame(item_frame, bg=COLORS["surface3"], width=3)
            indicator.pack(side=tk.LEFT, fill=tk.Y)

            item = tk.Label(item_frame, text=text, font=("Segoe UI", 9),
                            fg=COLORS["text_dim"], bg=COLORS["surface3"],
                            padx=12, pady=9, anchor="w", cursor="hand2")
            item.pack(side=tk.LEFT, fill=tk.X, expand=True)

            def _bind(w, ind, c):
                w.bind("<Enter>", lambda e: (w.config(bg=COLORS["surface2"], fg=COLORS["accent2"]),
                                             ind.config(bg=COLORS["accent"])))
                w.bind("<Leave>", lambda e: (w.config(bg=COLORS["surface3"], fg=COLORS["text_dim"]),
                                             ind.config(bg=COLORS["surface3"])))
                w.bind("<Button-1>", lambda e: self._run(c))
                ind.bind("<Button-1>", lambda e: self._run(c))
            _bind(item, indicator, cmd)

        sep = tk.Frame(inner, bg=COLORS["border"], height=1)
        sep.pack(fill=tk.X, padx=8, pady=0)

        self._popup.geometry(f"200x{len(items)*38+6}+{bx}+{by}")
        self._popup.bind("<FocusOut>", lambda e: self._close_popup())
        self._popup.focus_set()

        self._fade_in(0.0)

    def _fade_in(self, alpha):
        if self._popup and self._popup.winfo_exists():
            alpha = min(1.0, alpha + 0.12)
            self._popup.attributes("-alpha", alpha)
            if alpha < 1.0:
                self._popup.after(16, lambda: self._fade_in(alpha))

    def _close_popup(self):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            self._draw_btn(False)

    def _run(self, cmd):
        self._close_popup()
        cmd()

    def _do_import(self):
        self._on_import()

    def _do_configs(self):
        self._on_show_configs()


class AboutWindow(tk.Toplevel):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.title("اطلاعات سازنده")
        self.configure(bg=COLORS["bg"])
        self.geometry("450x380")
        self.resizable(False, False)
        self.attributes("-alpha", 0.0)
        self._build()
        self.update_idletasks()
        self.after(50, lambda: self._fade_in(0.0))

    def _fade_in(self, alpha):
        alpha = min(1.0, alpha + 0.1)
        self.attributes("-alpha", alpha)
        if alpha < 1.0:
            self.after(16, lambda: self._fade_in(alpha))

    def _build(self):
        accent_bar = tk.Frame(self, bg=COLORS["accent"], height=2)
        accent_bar.pack(fill=tk.X)

        header = tk.Frame(self, bg=COLORS["surface"], padx=18, pady=14)
        header.pack(fill=tk.X)
        tk.Label(header, text="درباره SNI Spoofer", font=("Segoe UI", 11, "bold"),
                 fg=COLORS["text"], bg=COLORS["surface"]).pack(side=tk.LEFT)
        tk.Frame(self, bg=COLORS["border"], height=1).pack(fill=tk.X)

        content = tk.Frame(self, bg=COLORS["bg"])
        content.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)

        title = tk.Label(content, text="SNI Spoofer v2.0", font=("Segoe UI", 12, "bold"),
                        fg=COLORS["accent2"], bg=COLORS["bg"])
        title.pack(anchor="w", pady=(0, 12))

        sep1 = tk.Frame(content, bg=COLORS["border"], height=1)
        sep1.pack(fill=tk.X, pady=8)

        creators_title = tk.Label(content, text="سازندگان", font=("Segoe UI", 9, "bold"),
                                 fg=COLORS["accent"], bg=COLORS["bg"])
        creators_title.pack(anchor="w", pady=(8, 6))

        creator1_frame = tk.Frame(content, bg=COLORS["surface2"], padx=10, pady=8)
        creator1_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Label(creator1_frame, text="نسخه اصلی", font=("Segoe UI", 8, "bold"),
                fg=COLORS["text_muted"], bg=COLORS["surface2"]).pack(anchor="w")
        link1 = tk.Label(creator1_frame, text="patterniha/SNI-Spoofing", font=("Segoe UI", 8),
                        fg=COLORS["accent2"], bg=COLORS["surface2"], cursor="hand2")
        link1.pack(anchor="w")
        link1.bind("<Button-1>", lambda e: self._open_url("https://github.com/patterniha/SNI-Spoofing"))
        link1.bind("<Enter>", lambda e: link1.config(fg=COLORS["accent"]))
        link1.bind("<Leave>", lambda e: link1.config(fg=COLORS["accent2"]))

        creator2_frame = tk.Frame(content, bg=COLORS["surface2"], padx=10, pady=8)
        creator2_frame.pack(fill=tk.X, pady=(0, 5))
        tk.Label(creator2_frame, text="نسخه ارتقا یافته (UI)", font=("Segoe UI", 8, "bold"),
                fg=COLORS["text_muted"], bg=COLORS["surface2"]).pack(anchor="w")
        link2 = tk.Label(creator2_frame, text="dakrdevo/SNI-Spoofing-With-UI", font=("Segoe UI", 8),
                        fg=COLORS["accent2"], bg=COLORS["surface2"], cursor="hand2")
        link2.pack(anchor="w")
        link2.bind("<Button-1>", lambda e: self._open_url("https://github.com/dakrdevo/SNI-Spoofing-With-UI"))
        link2.bind("<Enter>", lambda e: link2.config(fg=COLORS["accent"]))
        link2.bind("<Leave>", lambda e: link2.config(fg=COLORS["accent2"]))

        sep2 = tk.Frame(content, bg=COLORS["border"], height=1)
        sep2.pack(fill=tk.X, pady=8)

        support_title = tk.Label(content, text="حمایت مالی", font=("Segoe UI", 9, "bold"),
                               fg=COLORS["accent"], bg=COLORS["bg"])
        support_title.pack(anchor="w", pady=(8, 4))

        support_frame = tk.Frame(content, bg=COLORS["surface2"], padx=10, pady=8)
        support_frame.pack(fill=tk.X)
        tk.Label(support_frame, text="آدرس Tron (TRX):", font=("Segoe UI", 8),
                fg=COLORS["text_muted"], bg=COLORS["surface2"]).pack(anchor="w")
        addr = tk.Label(support_frame, text="TAmPkwnab6SBno2MNT4Q6SS4ewbAcGz2Xc", font=("Cascadia Code", 7),
                       fg=COLORS["accent2"], bg=COLORS["surface3"], padx=6, pady=4, relief=tk.FLAT,
                       selectcolor=COLORS["accent_dim"])
        addr.pack(anchor="w", pady=(4, 0), fill=tk.X)
        addr.config(state=tk.NORMAL)

    def _open_url(self, url):
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("خطا", f"باز کردن لینک ناموفق:\n{e}", parent=self)


class ConfigsWindow(tk.Toplevel):
    def __init__(self, parent, on_load, **kwargs):
        super().__init__(parent, **kwargs)
        self.title("کانفیگ‌های ذخیره شده")
        self.configure(bg=COLORS["bg"])
        self.geometry("440x340")
        self.resizable(False, False)
        self._on_load = on_load
        self.attributes("-alpha", 0.0)
        self._build()
        self._fade_in(0.0)

    def _fade_in(self, alpha):
        alpha = min(1.0, alpha + 0.1)
        self.attributes("-alpha", alpha)
        if alpha < 1.0:
            self.after(16, lambda: self._fade_in(alpha))

    def _build(self):
        accent_bar = tk.Frame(self, bg=COLORS["accent"], height=2)
        accent_bar.pack(fill=tk.X)

        header = tk.Frame(self, bg=COLORS["surface"], padx=18, pady=12)
        header.pack(fill=tk.X)
        tk.Label(header, text="کانفیگ‌های ذخیره شده", font=("Segoe UI", 10, "bold"),
                 fg=COLORS["text"], bg=COLORS["surface"]).pack(side=tk.LEFT)
        tk.Frame(self, bg=COLORS["border"], height=1).pack(fill=tk.X)

        frame = tk.Frame(self, bg=COLORS["bg"])
        frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=14)

        configs = self._scan_configs()
        if not configs:
            no_cfg = tk.Frame(frame, bg=COLORS["surface2"], padx=20, pady=20)
            no_cfg.pack(fill=tk.X)
            tk.Label(no_cfg, text="هیچ کانفیگی یافت نشد", font=("Segoe UI", 9),
                     fg=COLORS["text_muted"], bg=COLORS["surface2"]).pack()
            return

        for path, name in configs:
            row = tk.Frame(frame, bg=COLORS["surface2"])
            row.pack(fill=tk.X, pady=(0, 5))

            left_bar = tk.Frame(row, bg=COLORS["accent_dim"], width=3)
            left_bar.pack(side=tk.LEFT, fill=tk.Y)

            tk.Label(row, text=name, font=("Segoe UI", 9),
                     fg=COLORS["text_dim"], bg=COLORS["surface2"],
                     padx=12, pady=8).pack(side=tk.LEFT, fill=tk.X, expand=True)

            load_btn = tk.Label(row, text="بارگذاری", font=("Segoe UI", 8, "bold"),
                                fg=COLORS["accent"], bg=COLORS["surface2"],
                                padx=14, pady=8, cursor="hand2")
            load_btn.pack(side=tk.RIGHT)
            load_btn.bind("<Button-1>", lambda e, p=path: self._load(p))
            load_btn.bind("<Enter>", lambda e, w=load_btn, b=left_bar: (
                w.config(fg=COLORS["accent2"], bg=COLORS["surface3"]),
                b.config(bg=COLORS["accent"])
            ))
            load_btn.bind("<Leave>", lambda e, w=load_btn, b=left_bar: (
                w.config(fg=COLORS["accent"], bg=COLORS["surface2"]),
                b.config(bg=COLORS["accent_dim"])
            ))

    def _scan_configs(self):
        results = []
        dirs_to_check = [get_exe_dir(), CONFIGS_DIR]
        for d in dirs_to_check:
            if not os.path.isdir(d):
                continue
            for f in os.listdir(d):
                if f.endswith(".json") and f != "config.json":
                    filepath = os.path.join(d, f)
                    display_name = self._format_config_name(f)
                    results.append((filepath, display_name))
        return sorted(results, key=lambda x: x[1], reverse=True)

    def _format_config_name(self, filename):
        base = filename.replace(".json", "")
        if base.startswith("config_"):
            parts = base.split("_")
            if len(parts) >= 3:
                num = parts[1]
                ts = "_".join(parts[2:])
                try:
                    dt = time.strptime(ts, "%Y%m%d_%H%M%S")
                    display_ts = time.strftime("%Y-%m-%d %H:%M:%S", dt)
                    return f"Config {num} - {display_ts}"
                except:
                    return filename
        return filename

    def _load(self, path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            self._on_load(data)
            self.destroy()
        except Exception as e:
            messagebox.showerror("خطا", f"بارگذاری کانفیگ با خطا مواجه شد:\n{e}", parent=self)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SNI Spoofer")
        self.geometry("860x700")
        self.minsize(740, 620)
        self.configure(bg=COLORS["bg"])
        self.resizable(True, True)

        try:
            self.iconbitmap(default="")
        except Exception:
            pass

        self._config = self._load_config()
        self._running = False
        self._proxy_thread = None
        self._conn_count = 0
        self._start_time = None
        self._adv_visible = False
        self._hdr_phase = 0
        self._particle_phase = 0

        self._adv_vars = {}
        self._adv_entry_widgets = {}
        self._adv_check_widgets = {}
        self._save_disabled = False

        self._build_ui()
        self._check_interface()
        self._animate_header()
        self._animate_particles()

    def _load_config(self):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        except Exception:
            return {
                "LISTEN_HOST": "0.0.0.0",
                "LISTEN_PORT": 40443,
                "CONNECT_IP": "188.114.98.0",
                "CONNECT_PORT": 443,
                "FAKE_SNI": "auth.vercel.com"
            }

    def _save_config(self):
        try:
            cfg = {
                "LISTEN_HOST": self.entry_listen_host.get(),
                "LISTEN_PORT": int(self.entry_listen_port.get()),
                "CONNECT_IP": self.entry_connect_ip.get(),
                "CONNECT_PORT": int(self.entry_connect_port.get()),
                "FAKE_SNI": self.entry_fake_sni.get(),
            }
            for key, lbl, default, typ in ADVANCED_KEYS:
                if key in self._adv_vars and self._adv_vars[key].get():
                    if typ == "bool":
                        if key in self._adv_entry_widgets:
                            cfg[key] = self._adv_entry_widgets[key].get()
                        else:
                            cfg[key] = True
                    elif key in self._adv_entry_widgets:
                        raw = self._adv_entry_widgets[key].get()
                        if typ == "int":
                            cfg[key] = int(raw) if raw else default
                        elif typ == "float":
                            cfg[key] = float(raw) if raw else default
                        elif typ == "list":
                            cfg[key] = [x.strip() for x in raw.split(",") if x.strip()]
                        else:
                            cfg[key] = raw
            with open(CONFIG_PATH, 'w') as f:
                json.dump(cfg, f, indent=2)
            self._config = cfg
            self._auto_save_config_to_history(cfg)
            self.log_panel.log("کانفیگ ذخیره شد.", "success")
            return cfg
        except Exception as e:
            self.log_panel.log(f"خطا در ذخیره: {e}", "error")
            return None

    def _apply_config(self, data):
        if "LISTEN_HOST" in data:
            self.entry_listen_host.set(data["LISTEN_HOST"])
        if "LISTEN_PORT" in data:
            self.entry_listen_port.set(str(data["LISTEN_PORT"]))
        if "CONNECT_IP" in data:
            self.entry_connect_ip.set(data["CONNECT_IP"])
        if "CONNECT_PORT" in data:
            self.entry_connect_port.set(str(data["CONNECT_PORT"]))
        if "FAKE_SNI" in data:
            self.entry_fake_sni.set(data["FAKE_SNI"])

        has_adv = False
        for key, lbl, default, typ in ADVANCED_KEYS:
            if key in data:
                has_adv = True
                val = data[key]
                if typ == "bool":
                    if key in self._adv_vars:
                        self._adv_vars[key].set(True)
                    if key in self._adv_entry_widgets:
                        self._adv_entry_widgets[key].set(bool(val))
                elif key in self._adv_entry_widgets:
                    if typ == "list":
                        self._adv_entry_widgets[key].set(", ".join(val) if isinstance(val, list) else str(val))
                    else:
                        self._adv_entry_widgets[key].set(str(val))
                    if key in self._adv_vars:
                        self._adv_vars[key].set(True)

        if has_adv and not self._adv_visible:
            self._toggle_advanced()

        self._auto_save_config_to_history(data)
        self.log_panel.log("کانفیگ از فایل بارگذاری شد.", "success")

    def _auto_save_config_to_history(self, cfg):
        try:
            if not os.path.isdir(CONFIGS_DIR):
                os.makedirs(CONFIGS_DIR)

            existing = [f for f in os.listdir(CONFIGS_DIR) if f.endswith(".json")]
            count = len(existing) + 1

            ts = time.strftime("%Y%m%d_%H%M%S")
            filename = f"config_{count}_{ts}.json"
            filepath = os.path.join(CONFIGS_DIR, filename)
            while os.path.exists(filepath):
                count += 1
                filename = f"config_{count}_{ts}.json"
                filepath = os.path.join(CONFIGS_DIR, filename)

            with open(filepath, 'w') as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    def _import_config(self):
        path = filedialog.askopenfilename(
            title="انتخاب فایل کانفیگ JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            self._apply_config(data)
        except Exception as e:
            messagebox.showerror("خطا", f"بارگذاری ناموفق:\n{e}")

    def _check_interface(self):
        ip = get_default_interface_ipv4(self._config.get("CONNECT_IP", "8.8.8.8"))
        if ip:
            self.iface_label.config(text=f"رابط شبکه: {ip} (IPv4)", fg=COLORS["success"])
        else:
            self.iface_label.config(text="رابط شبکه: یافت نشد (IPv4)", fg=COLORS["error"])

    def _animate_header(self):
        self._hdr_phase = (self._hdr_phase + 1) % 160
        t = self._hdr_phase / 160.0
        base = int(18 + 16 * (0.5 + 0.5 * math.sin(t * 2 * math.pi)))
        r = min(255, base + 180)
        g = 0
        b = min(255, base // 2 + 50)
        color = f"#{r:02x}{g:02x}{b:02x}"
        try:
            self._header_accent_bar.config(bg=color)
        except Exception:
            pass
        self.after(70, self._animate_header)

    def _animate_particles(self):
        self._particle_phase = (self._particle_phase + 1) % 200
        t = self._particle_phase / 200.0
        try:
            self._header_canvas.delete("particles")
            w = self._header_canvas.winfo_width()
            if w > 1:
                for i in range(5):
                    px = (w * (i * 0.2 + 0.05 + 0.03 * math.sin(t * 2 * math.pi + i))) % w
                    py = 4 + 3 * math.sin(t * 2 * math.pi * 1.3 + i * 1.1)
                    alpha = int(80 + 60 * math.sin(t * 2 * math.pi + i))
                    self._header_canvas.create_oval(
                        px - 1, py - 1, px + 1, py + 1,
                        fill=COLORS["accent"], outline="", tags="particles"
                    )
        except Exception:
            pass
        self.after(60, self._animate_particles)

    def _build_ui(self):
        self._build_header()
        self._build_body()

    def _build_header(self):
        outer = tk.Frame(self, bg=COLORS["surface"])
        outer.pack(fill=tk.X)

        self._header_accent_bar = tk.Frame(outer, bg=COLORS["accent"], height=2)
        self._header_accent_bar.pack(fill=tk.X, side=tk.TOP)

        self._header_canvas = tk.Canvas(outer, height=8, bg=COLORS["surface"],
                                        highlightthickness=0)
        self._header_canvas.pack(fill=tk.X)

        tk.Frame(outer, bg=COLORS["border"], height=1).pack(fill=tk.X, side=tk.BOTTOM)

        inner = tk.Frame(outer, bg=COLORS["surface"], padx=22, pady=12)
        inner.pack(fill=tk.X)

        left = tk.Frame(inner, bg=COLORS["surface"])
        left.pack(side=tk.LEFT)

        title_frame = tk.Frame(left, bg=COLORS["surface"])
        title_frame.pack(side=tk.LEFT)

        tk.Label(title_frame, text="SNI", font=("Segoe UI", 15, "bold"),
                 fg=COLORS["accent2"], bg=COLORS["surface"]).pack(side=tk.LEFT)
        tk.Label(title_frame, text=" Spoofer", font=("Segoe UI", 15, "bold"),
                 fg=COLORS["text"], bg=COLORS["surface"]).pack(side=tk.LEFT)
        tk.Label(title_frame, text="  v2.0", font=("Segoe UI", 9),
                 fg=COLORS["text_muted"], bg=COLORS["surface"]).pack(side=tk.LEFT, pady=(5, 0))

        right = tk.Frame(inner, bg=COLORS["surface"])
        right.pack(side=tk.RIGHT)

        about_btn = tk.Canvas(right, width=24, height=24, bg=COLORS["surface"],
                             highlightthickness=0, cursor="hand2")
        about_btn.pack(side=tk.RIGHT, padx=(0, 14))
        about_btn.create_text(12, 12, text="?", font=("Segoe UI", 14, "bold"),
                            fill=COLORS["text_muted"])
        about_btn.bind("<Button-1>", lambda e: self._open_github())
        about_btn.bind("<Enter>", lambda e: (about_btn.delete("all"),
                                            about_btn.create_text(12, 12, text="?", font=("Segoe UI", 14, "bold"),
                                                                fill=COLORS["accent"])))
        about_btn.bind("<Leave>", lambda e: (about_btn.delete("all"),
                                            about_btn.create_text(12, 12, text="?", font=("Segoe UI", 14, "bold"),
                                                               fill=COLORS["text_muted"])))

        self.status_badge = StatusBadge(right)
        self.status_badge.pack(side=tk.RIGHT, padx=(16, 0))

        self.iface_label = tk.Label(right, text="در حال بررسی...", font=("Segoe UI", 8),
                                    fg=COLORS["text_muted"], bg=COLORS["surface"])
        self.iface_label.pack(side=tk.RIGHT)

    def _build_body(self):
        body = tk.Frame(self, bg=COLORS["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)

        left_col = tk.Frame(body, bg=COLORS["bg"])
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        right_col = tk.Frame(body, bg=COLORS["bg"], width=320)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH)
        right_col.pack_propagate(False)

        self._build_config_panel(left_col)
        self._build_controls(left_col)
        self._build_stats(right_col)
        self._build_log(right_col)

    def _build_config_panel(self, parent):
        self._config_outer = tk.Frame(parent, bg=COLORS["surface"])
        self._config_outer.pack(fill=tk.X, pady=(0, 10))

        top_accent = tk.Frame(self._config_outer, bg=COLORS["accent_dim"], height=1)
        top_accent.pack(fill=tk.X)

        hdr = tk.Frame(self._config_outer, bg=COLORS["surface"], padx=16, pady=12)
        hdr.pack(fill=tk.X)

        hdr_left = tk.Frame(hdr, bg=COLORS["surface"])
        hdr_left.pack(side=tk.LEFT)

        tk.Label(hdr_left, text="تنظیمات اتصال", font=("Segoe UI", 10, "bold"),
                 fg=COLORS["text"], bg=COLORS["surface"]).pack(side=tk.LEFT)

        self._plus_menu = PlusMenu(hdr, on_import=self._import_config,
                                   on_show_configs=self._show_configs)
        self._plus_menu.pack(side=tk.RIGHT)

        tk.Frame(self._config_outer, bg=COLORS["border"], height=1).pack(fill=tk.X)

        grid = tk.Frame(self._config_outer, bg=COLORS["surface"], padx=14, pady=10)
        grid.pack(fill=tk.X)

        row1 = tk.Frame(grid, bg=COLORS["surface"])
        row1.pack(fill=tk.X, pady=(0, 4))

        self.entry_listen_host = StyledEntry(row1, "listen host",
                                             value=self._config.get("LISTEN_HOST", "0.0.0.0"))
        self.entry_listen_host.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.entry_listen_port = StyledEntry(row1, "listen port",
                                             value=self._config.get("LISTEN_PORT", 40443))
        self.entry_listen_port.pack(side=tk.LEFT, fill=tk.X, expand=True)

        row2 = tk.Frame(grid, bg=COLORS["surface"])
        row2.pack(fill=tk.X, pady=(0, 4))

        self.entry_connect_ip = StyledEntry(row2, "target IP",
                                            value=self._config.get("CONNECT_IP", "188.114.98.0"))
        self.entry_connect_ip.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.entry_connect_port = StyledEntry(row2, "target port",
                                              value=self._config.get("CONNECT_PORT", 443))
        self.entry_connect_port.pack(side=tk.LEFT, fill=tk.X, expand=True)

        row3 = tk.Frame(grid, bg=COLORS["surface"])
        row3.pack(fill=tk.X, pady=(0, 4))

        self.entry_fake_sni = StyledEntry(row3, "فیک SNI",
                                          value=self._config.get("FAKE_SNI", "auth.vercel.com"))
        self.entry_fake_sni.pack(fill=tk.X)

        self._build_advanced_section(grid)

    def _build_advanced_section(self, parent):
        self._adv_toggle_row = tk.Frame(parent, bg=COLORS["surface"])
        self._adv_toggle_row.pack(fill=tk.X, pady=(10, 2))

        toggle_canvas = tk.Canvas(self._adv_toggle_row, width=16, height=16,
                                  bg=COLORS["surface"], highlightthickness=0,
                                  cursor="hand2")
        toggle_canvas.pack(side=tk.LEFT, padx=(4, 6))
        self._adv_arrow_canvas = toggle_canvas

        toggle_lbl = tk.Label(self._adv_toggle_row, text="تنظیمات پیشرفته",
                              font=("Segoe UI", 8), fg=COLORS["text_muted"],
                              bg=COLORS["surface"], cursor="hand2")
        toggle_lbl.pack(side=tk.LEFT)
        self._adv_toggle_lbl = toggle_lbl

        self._adv_sep = tk.Frame(self._adv_toggle_row, bg=COLORS["border"], height=1)
        self._adv_sep.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 4))

        self._draw_adv_arrow(False)

        toggle_canvas.bind("<Button-1>", lambda e: self._toggle_advanced())
        toggle_lbl.bind("<Button-1>", lambda e: self._toggle_advanced())
        toggle_canvas.bind("<Enter>", lambda e: toggle_lbl.config(fg=COLORS["accent"]))
        toggle_canvas.bind("<Leave>", lambda e: toggle_lbl.config(
            fg=COLORS["accent"] if self._adv_visible else COLORS["text_muted"]))
        toggle_lbl.bind("<Enter>", lambda e: toggle_lbl.config(fg=COLORS["accent"]))
        toggle_lbl.bind("<Leave>", lambda e: toggle_lbl.config(
            fg=COLORS["accent"] if self._adv_visible else COLORS["text_muted"]))

        self._adv_frame = tk.Frame(parent, bg=COLORS["surface"])

        for key, lbl, default, typ in ADVANCED_KEYS:
            row = tk.Frame(self._adv_frame, bg=COLORS["surface2"])
            row.pack(fill=tk.X, pady=(0, 3))

            left_indicator = tk.Frame(row, bg=COLORS["accent_dim"], width=2)
            left_indicator.pack(side=tk.LEFT, fill=tk.Y)

            inner_row = tk.Frame(row, bg=COLORS["surface2"], padx=8, pady=5)
            inner_row.pack(fill=tk.X, expand=True)

            enabled_var = tk.BooleanVar(value=key in self._config)
            self._adv_vars[key] = enabled_var

            if typ == "bool":
                def _make_bool_cb(k, dv, r=inner_row):
                    val_var = tk.BooleanVar(value=self._config.get(k, dv))
                    self._adv_entry_widgets[k] = val_var

                    chk = PinkCheckbox(r, lbl, var=enabled_var, bg=COLORS["surface2"])
                    chk.pack(side=tk.LEFT, padx=(0, 10))
                    val_chk = PinkCheckbox(r, "فعال", var=val_var, bg=COLORS["surface2"])
                    val_chk.pack(side=tk.LEFT)
                    self._adv_check_widgets[k] = val_chk

                _make_bool_cb(key, default)
            else:
                chk = PinkCheckbox(inner_row, lbl, var=enabled_var, bg=COLORS["surface2"])
                chk.pack(side=tk.LEFT, padx=(0, 10))

                existing = self._config.get(key, default)
                if typ == "list":
                    existing = ", ".join(existing) if isinstance(existing, list) else str(existing)
                else:
                    existing = str(existing)

                ent_frame = tk.Frame(inner_row, bg=COLORS["border"], padx=1, pady=1)
                ent_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

                ent = tk.Entry(ent_frame, font=("Segoe UI", 9), fg=COLORS["text"],
                               bg=COLORS["surface3"], insertbackground=COLORS["accent"],
                               relief=tk.FLAT, bd=3)
                ent.insert(0, existing)
                ent.pack(fill=tk.X)
                ent.bind("<FocusIn>", lambda e, f=ent_frame: f.config(bg=COLORS["accent"]))
                ent.bind("<FocusOut>", lambda e, f=ent_frame: f.config(bg=COLORS["border"]))

                class _EntryWrapper:
                    def __init__(self, entry):
                        self._e = entry

                    def get(self):
                        return self._e.get().strip()

                    def set(self, v):
                        self._e.delete(0, tk.END)
                        self._e.insert(0, str(v))

                self._adv_entry_widgets[key] = _EntryWrapper(ent)

    def _draw_adv_arrow(self, expanded):
        c = self._adv_arrow_canvas
        c.delete("all")
        color = COLORS["accent"] if expanded else COLORS["text_muted"]
        if expanded:
            c.create_line(3, 5, 8, 11, fill=color, width=2)
            c.create_line(8, 11, 13, 5, fill=color, width=2)
        else:
            c.create_line(5, 3, 11, 8, fill=color, width=2)
            c.create_line(11, 8, 5, 13, fill=color, width=2)

    def _toggle_advanced(self):
        self._adv_visible = not self._adv_visible
        if self._adv_visible:
            self._adv_frame.pack(fill=tk.X, pady=(4, 4))
            self._adv_toggle_lbl.config(fg=COLORS["accent"])
            self._draw_adv_arrow(True)
        else:
            self._adv_frame.pack_forget()
            self._adv_toggle_lbl.config(fg=COLORS["text_muted"])
            self._draw_adv_arrow(False)

    def _open_github(self):
        import subprocess
        url = "https://github.com/dakrdevo/SNI-Spoofing-With-UI"
        try:
            subprocess.Popen(["cmd", "/c", "start", "chrome", url], shell=False)
        except Exception:
            import webbrowser
            webbrowser.open(url)

    def _show_configs(self):
        ConfigsWindow(self, on_load=self._apply_config)

    def _build_controls(self, parent):
        panel = tk.Frame(parent, bg=COLORS["surface"], padx=16, pady=14)
        panel.pack(fill=tk.X)

        btn_frame = tk.Frame(panel, bg=COLORS["surface"])
        btn_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._toggle_btn_canvas = tk.Canvas(btn_frame, width=110, height=40,
                                            bg=COLORS["surface"], highlightthickness=0,
                                            cursor="hand2")
        self._toggle_btn_canvas.pack(side=tk.LEFT)
        self._draw_toggle_btn("start")
        self._toggle_btn_canvas.bind("<Button-1>", lambda e: self._toggle())
        self._toggle_btn_canvas.bind("<Enter>", lambda e: self._on_toggle_hover(True))
        self._toggle_btn_canvas.bind("<Leave>", lambda e: self._on_toggle_hover(False))
        self._toggle_hover = False

        self._save_btn_canvas = tk.Canvas(btn_frame, width=110, height=40,
                                          bg=COLORS["surface"], highlightthickness=0,
                                          cursor="hand2")
        self._save_btn_canvas.pack(side=tk.LEFT, padx=(10, 0))
        self._draw_save_btn(False)
        self._save_btn_canvas.bind("<Button-1>", lambda e: self._save_config())
        self._save_btn_canvas.bind("<Enter>", lambda e: self._draw_save_btn(True))
        self._save_btn_canvas.bind("<Leave>", lambda e: self._draw_save_btn(False))

        self.uptime_label = tk.Label(panel, text="", font=("Segoe UI", 8),
                                     fg=COLORS["text_muted"], bg=COLORS["surface"])
        self.uptime_label.pack(side=tk.RIGHT)

    def _draw_toggle_btn(self, mode):
        c = self._toggle_btn_canvas
        c.delete("all")
        if mode == "start":
            bg = COLORS["accent"]
            text = "  شروع"
        else:
            bg = COLORS["error"]
            text = "  توقف"
        c.create_rectangle(0, 0, 110, 40, fill=bg, outline="", width=0)
        c.create_text(55, 20, text=text, font=("Segoe UI", 10, "bold"), fill="white")

    def _on_toggle_hover(self, hovered):
        self._toggle_hover = hovered
        c = self._toggle_btn_canvas
        c.delete("all")
        if self._running:
            bg = "#c53030" if hovered else COLORS["error"]
            text = "  توقف"
        else:
            bg = COLORS["accent_hover"] if hovered else COLORS["accent"]
            text = "  شروع"
        c.create_rectangle(0, 0, 110, 40, fill=bg, outline="", width=0)
        c.create_text(55, 20, text=text, font=("Segoe UI", 10, "bold"), fill="white")

    def _draw_save_btn(self, hovered):
        c = self._save_btn_canvas
        c.delete("all")
        if self._save_disabled:
            bg = COLORS["surface2"]
            fg = COLORS["text_muted"]
        else:
            bg = COLORS["surface4"] if hovered else COLORS["surface3"]
            fg = COLORS["text"] if hovered else COLORS["text_dim"]
        c.create_rectangle(0, 0, 110, 40, fill=bg, outline=COLORS["border"], width=1)
        c.create_text(55, 20, text="ذخیره کانفیگ", font=("Segoe UI", 9), fill=fg)

    def _build_stats(self, parent):
        panel = tk.Frame(parent, bg=COLORS["surface"])
        panel.pack(fill=tk.X, pady=(0, 10))

        top_accent = tk.Frame(panel, bg=COLORS["accent_dim"], height=1)
        top_accent.pack(fill=tk.X)

        hdr = tk.Frame(panel, bg=COLORS["surface"], padx=16, pady=12)
        hdr.pack(fill=tk.X)

        dot = tk.Canvas(hdr, width=8, height=8, bg=COLORS["surface"], highlightthickness=0)
        dot.pack(side=tk.LEFT, padx=(0, 8))
        dot.create_oval(1, 1, 7, 7, fill=COLORS["accent_dim"], outline="")

        tk.Label(hdr, text="آمار", font=("Segoe UI", 10, "bold"),
                 fg=COLORS["text"], bg=COLORS["surface"]).pack(side=tk.LEFT)

        tk.Frame(panel, bg=COLORS["border"], height=1).pack(fill=tk.X)

        cards_frame = tk.Frame(panel, bg=COLORS["surface"], padx=10, pady=10)
        cards_frame.pack(fill=tk.X)
        cards_frame.columnconfigure(0, weight=1)
        cards_frame.columnconfigure(1, weight=1)

        self.stat_conns = StatCard(cards_frame, "اتصالات موفق", "0")
        self.stat_conns.grid(row=0, column=0, sticky="ew", padx=(2, 2), pady=(0, 5))

        self.stat_uptime = StatCard(cards_frame, "آپ‌تایم", "00:00")
        self.stat_uptime.grid(row=0, column=1, sticky="ew", padx=(2, 2), pady=(0, 5))

        self.stat_port = StatCard(cards_frame, "پورت فعال", "-")
        self.stat_port.grid(row=1, column=0, sticky="ew", padx=(2, 2), pady=(0, 8))

        self.stat_ip = StatCard(cards_frame, "هدف", "-")
        self.stat_ip.grid(row=1, column=1, sticky="ew", padx=(2, 2), pady=(0, 8))

    def _build_log(self, parent):
        self.log_panel = LogPanel(parent)
        self.log_panel.pack(fill=tk.BOTH, expand=True)
        self.log_panel.log("آماده. تنظیمات را بررسی کنید و شروع کنید.", "info")

    def _toggle(self):
        if not self._running:
            self._start()
        else:
            self._stop()

    def _start(self):
        cfg = self._save_config()
        if not cfg:
            return

        self._running = True
        self._conn_count = 0
        self._start_time = time.time()

        self.status_badge.set_state("connecting")
        self._draw_toggle_btn("stop")
        self.stat_port.set_value(str(cfg["LISTEN_PORT"]))
        self.stat_ip.set_value(cfg["CONNECT_IP"])
        self.log_panel.log(f"در حال گوش دادن روی {cfg['LISTEN_HOST']}:{cfg['LISTEN_PORT']}", "info")
        self.log_panel.log(f"-> {cfg['CONNECT_IP']}:{cfg['CONNECT_PORT']} فیک SNI: {cfg['FAKE_SNI']}", "info")

        self._disable_entries()
        self._proxy_thread = threading.Thread(target=self._run_proxy, daemon=True)
        self._proxy_thread.start()
        self._update_uptime()

        self.after(500, lambda: self.status_badge.set_state("running") if self._running else None)
        self.log_panel.log("پراکسی شروع شد.", "success")

    def _stop(self):
        self._running = False
        self.status_badge.set_state("idle")
        self._draw_toggle_btn("start")
        self.uptime_label.config(text="")
        self.stat_port.set_value("-")
        self.stat_ip.set_value("-")
        self.stat_uptime.set_value("00:00")
        self._enable_entries()
        self.log_panel.log("پراکسی متوقف شد.", "warning")

    def _run_proxy(self):
        try:
            import fake_tcp as ftcp
            import utils.packet_templates as pt

            from fake_tcp import FakeInjectiveConnection, FakeTcpInjector
            from utils.packet_templates import ClientHelloMaker
            from utils.network_tools import get_default_interface_ipv4

            cfg = self._config
            listen_host = cfg["LISTEN_HOST"]
            listen_port = cfg["LISTEN_PORT"]
            fake_sni = cfg["FAKE_SNI"].encode()
            connect_ip = cfg["CONNECT_IP"]
            connect_port = cfg["CONNECT_PORT"]
            interface_ipv4 = get_default_interface_ipv4(connect_ip)

            fake_injective_connections = {}

            w_filter = (
                "tcp and ("
                f"(ip.SrcAddr == {interface_ipv4} and ip.DstAddr == {connect_ip})"
                " or "
                f"(ip.SrcAddr == {connect_ip} and ip.DstAddr == {interface_ipv4})"
                ")"
            )

            fake_tcp_injector = FakeTcpInjector(w_filter, fake_injective_connections)
            inj_thread = threading.Thread(target=fake_tcp_injector.run, daemon=True)
            inj_thread.start()

            async def relay(s1, s2, peer_task, prefix):
                loop = asyncio.get_running_loop()
                while True:
                    try:
                        data = await loop.sock_recv(s1, 65575)
                        if not data:
                            raise ValueError("eof")
                        if prefix:
                            data = prefix + data
                            prefix = b""
                        await loop.sock_sendall(s2, data)
                    except Exception:
                        s1.close()
                        s2.close()
                        peer_task.cancel()
                        return

            async def handle(incoming_sock):
                loop = asyncio.get_running_loop()
                fake_data = ClientHelloMaker.get_client_hello_with(
                    os.urandom(32), os.urandom(32), fake_sni, os.urandom(32))
                outgoing_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                outgoing_sock.setblocking(False)
                outgoing_sock.bind((interface_ipv4, 0))
                outgoing_sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                src_port = outgoing_sock.getsockname()[1]
                fic = FakeInjectiveConnection(
                    outgoing_sock, interface_ipv4, connect_ip,
                    src_port, connect_port, fake_data, "wrong_seq", incoming_sock)
                fake_injective_connections[fic.id] = fic
                try:
                    await loop.sock_connect(outgoing_sock, (connect_ip, connect_port))
                except Exception:
                    fic.monitor = False
                    del fake_injective_connections[fic.id]
                    outgoing_sock.close()
                    incoming_sock.close()
                    return
                try:
                    await asyncio.wait_for(fic.t2a_event.wait(), 2)
                    if fic.t2a_msg != "fake_data_ack_recv":
                        raise ValueError(fic.t2a_msg)
                except Exception:
                    fic.monitor = False
                    if fic.id in fake_injective_connections:
                        del fake_injective_connections[fic.id]
                    outgoing_sock.close()
                    incoming_sock.close()
                    return
                fic.monitor = False
                if fic.id in fake_injective_connections:
                    del fake_injective_connections[fic.id]
                self._conn_count += 1
                self.after(0, lambda: self.stat_conns.set_value(str(self._conn_count)))
                self.after(0, lambda: self.log_panel.log(f"اتصال جدید #{self._conn_count}", "success"))
                oti = asyncio.create_task(relay(outgoing_sock, incoming_sock, asyncio.current_task(), b""))
                await relay(incoming_sock, outgoing_sock, oti, b"")

            async def run_server():
                mother = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                mother.setblocking(False)
                mother.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                mother.bind((listen_host, listen_port))
                mother.listen()
                loop = asyncio.get_running_loop()
                while self._running:
                    try:
                        incoming, _ = await asyncio.wait_for(loop.sock_accept(mother), timeout=1)
                        incoming.setblocking(False)
                        asyncio.create_task(handle(incoming))
                    except asyncio.TimeoutError:
                        continue
                    except Exception:
                        break
                mother.close()

            asyncio.run(run_server())
        except Exception as e:
            self.after(0, lambda: self.log_panel.log(f"خطای پراکسی: {e}", "error"))
            self.after(0, self._stop)

    def _update_uptime(self):
        if not self._running:
            return
        if self._start_time:
            elapsed = int(time.time() - self._start_time)
            m, s = divmod(elapsed, 60)
            h, m = divmod(m, 60)
            uptime_str = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
            self.uptime_label.config(text=f"آپ‌تایم: {uptime_str}")
            self.stat_uptime.set_value(uptime_str)
        self.after(1000, self._update_uptime)

    def _all_entries(self):
        return [self.entry_listen_host, self.entry_listen_port,
                self.entry_connect_ip, self.entry_connect_port, self.entry_fake_sni]

    def _disable_entries(self):
        for e in self._all_entries():
            e.disable()
        self._save_disabled = True
        self._draw_save_btn(False)

    def _enable_entries(self):
        for e in self._all_entries():
            e.enable()
        self._save_disabled = False
        self._draw_save_btn(False)


if __name__ == "__main__":
    app = App()
    app.mainloop()
