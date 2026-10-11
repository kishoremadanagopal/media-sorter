"""The Media Sorter window: a 4-step wizard.

  Step 1  Source folder      pick the folder, see how many photos/videos it has
  Step 2  Save location      where to create the new folder and its name
  Step 3  Sort options       date / location / both, folder order, copy or move
  Step 4  Sort & finish      progress, then a summary with a folder preview
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw

import webbrowser

from . import APP_NAME, AUTHOR, DESCRIPTION, GITHUB_URL, __version__
from .engine import (Sorter, SortOptions, folder_name_problem, folder_tree_text,
                     is_inside, scan)
from .geocode import Geocoder

# ----------------------------------------------------------------------------- look
ACCENT = "#1D5FC8"
ACCENT_HOVER = "#164A9C"
TEXT = "#17202B"
MUTED = "#59636E"
BORDER = "#C9D0D8"
LINE = "#E3E7EC"
SIDEBAR_BG = "#F6F7F9"
CURRENT_ROW = "#E8EDF4"
CARD_BG = "#FAFBFC"
SELECTED_BG = "#F2F6FC"
DISABLED_BG = "#EEF1F4"
DISABLED_TEXT = "#737D88"
SUCCESS = "#1E7B4F"
SUCCESS_BG = "#E4F3EC"
WARN = "#9A4A00"
ERROR = "#B42318"
WHITE = "#FFFFFF"

IS_WINDOWS = sys.platform == "win32"
UI_FAMILY = "Segoe UI" if IS_WINDOWS else "DejaVu Sans"
MONO_FAMILY = "Consolas" if IS_WINDOWS else "DejaVu Sans Mono"
ORDER_DATE_FIRST = "Date → Location"
ORDER_LOCATION_FIRST = "Location → Date"


def resource_path(*parts: str) -> Path:
    base = getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)
    return Path(base, *parts)


def default_save_location() -> str:
    pictures = Path.home() / "Pictures"
    return str(pictures if pictures.is_dir() else Path.home())


def open_path(path: Path):
    try:
        if IS_WINDOWS:
            os.startfile(str(path))  # noqa: S606 - opens Explorer / default app
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:
        messagebox.showerror(APP_NAME, f"Couldn't open:\n{path}\n\n{exc}")


# ----------------------------------------------------------------------------- icons
_ICON_CACHE: dict[tuple[str, str, int], ctk.CTkImage] = {}


def make_icon(kind: str, color: str = ACCENT, size: int = 26) -> ctk.CTkImage:
    """Small line icons drawn with Pillow. Each icon is created once and kept, so an icon
    a widget still shows can never be thrown away while it's on screen."""
    key = (kind, color, size)
    if key not in _ICON_CACHE:
        _ICON_CACHE[key] = _draw_icon(kind, color, size)
    return _ICON_CACHE[key]


def _draw_icon(kind: str, color: str, size: int) -> ctk.CTkImage:
    s = 4 * size
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = max(6, s // 11)
    if kind == "calendar":
        d.rounded_rectangle((s * .12, s * .2, s * .88, s * .9), radius=s * .1, outline=color, width=w)
        d.line((s * .12, s * .42, s * .88, s * .42), fill=color, width=w)
        d.line((s * .33, s * .08, s * .33, s * .28), fill=color, width=w)
        d.line((s * .67, s * .08, s * .67, s * .28), fill=color, width=w)
    elif kind == "pin":
        d.ellipse((s * .2, s * .06, s * .8, s * .66), outline=color, width=w)
        d.line((s * .26, s * .52, s * .5, s * .94), fill=color, width=w)
        d.line((s * .74, s * .52, s * .5, s * .94), fill=color, width=w)
        d.ellipse((s * .4, s * .26, s * .6, s * .46), fill=color)
    elif kind == "layers":
        for dy in (0, .2, .4):
            d.polygon([(s * .5, s * (.1 + dy)), (s * .92, s * (.3 + dy)),
                       (s * .5, s * (.5 + dy)), (s * .08, s * (.3 + dy))], outline=color, width=w)
    elif kind == "folder":
        d.rounded_rectangle((s * .08, s * .28, s * .92, s * .86), radius=s * .08, outline=color, width=w)
        d.line((s * .08, s * .3, s * .08, s * .18, s * .4, s * .18, s * .48, s * .28), fill=color, width=w,
               joint="curve")
    elif kind == "check_circle":
        d.ellipse((0, 0, s - 1, s - 1), fill=SUCCESS_BG)
        d.line((s * .28, s * .52, s * .43, s * .67, s * .73, s * .36), fill=SUCCESS, width=w, joint="curve")
    elif kind == "stop_circle":
        d.ellipse((0, 0, s - 1, s - 1), fill="#FCEFE3")
        d.rounded_rectangle((s * .35, s * .35, s * .65, s * .65), radius=s * .04, fill=WARN)
    elif kind == "photo":
        d.rounded_rectangle((s * .1, s * .1, s * .9, s * .9), radius=s * .14, outline=color, width=w)
        d.ellipse((s * .28, s * .28, s * .44, s * .44), outline=color, width=w)
        d.line((s * .9, s * .62, s * .66, s * .4, s * .14, s * .86), fill=color, width=w, joint="curve")
    img = img.resize((size * 2, size * 2), Image.LANCZOS)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))


# ----------------------------------------------------------------------------- small widgets
class StatTile(ctk.CTkFrame):
    def __init__(self, master, caption: str, **kw):
        super().__init__(master, fg_color=WHITE, border_width=1, border_color=LINE, corner_radius=10, **kw)
        self.number = ctk.CTkLabel(self, text="–", font=ctk.CTkFont(UI_FAMILY, 24, "bold"),
                                   text_color=TEXT, anchor="w")
        self.number.pack(fill="x", padx=16, pady=(12, 0))
        self.caption = ctk.CTkLabel(self, text=caption, font=ctk.CTkFont(UI_FAMILY, 12),
                                    text_color=MUTED, anchor="w")
        self.caption.pack(fill="x", padx=16, pady=(0, 12))

    def set(self, value, color: str = TEXT):
        self.number.configure(text=str(value), text_color=color)


class ChoiceCard(ctk.CTkFrame):
    """A big clickable option card (By date / By location / Both)."""

    def __init__(self, master, icon: str, title: str, desc: str, variable, value: str, command):
        super().__init__(master, fg_color=WHITE, border_width=2, border_color="#D9DEE4", corner_radius=12)
        self.variable, self.value, self.command = variable, value, command
        ctk.CTkLabel(self, text="", image=make_icon(icon, size=26)).pack(anchor="w", padx=16, pady=(16, 6))
        self.radio = ctk.CTkRadioButton(self, text=title, variable=variable, value=value, command=command,
                                        font=ctk.CTkFont(UI_FAMILY, 15, "bold"), text_color=TEXT,
                                        fg_color=ACCENT, hover_color=ACCENT_HOVER, radiobutton_width=18,
                                        radiobutton_height=18, border_width_unchecked=2)
        self.radio.pack(anchor="w", padx=16)
        self.desc = ctk.CTkLabel(self, text=desc, font=ctk.CTkFont(UI_FAMILY, 12), text_color=MUTED,
                                 justify="left", anchor="w", wraplength=150)
        self.desc.pack(anchor="w", fill="x", padx=16, pady=(4, 16))
        for widget in {self, self.desc, *self.winfo_children()}:
            if widget is self.radio:
                continue  # the radio button handles its own clicks
            widget.bind("<Button-1>", self._click, add="+")
            try:
                widget.configure(cursor="hand2")
            except Exception:
                pass

    def _click(self, _event=None):
        self.variable.set(self.value)
        self.command()

    def refresh(self):
        selected = self.variable.get() == self.value
        self.configure(border_color=ACCENT if selected else "#D9DEE4", fg_color=SELECTED_BG if selected else WHITE)


# ----------------------------------------------------------------------------- the app
class App(ctk.CTk):
    STEP_NAMES = ("Source folder", "Save location", "Sort options", "Sort & finish")

    def __init__(self):
        ctk.set_appearance_mode("light")
        super().__init__(fg_color=WHITE)
        self.title(APP_NAME)
        self.geometry("900x720")
        self.minsize(840, 680)
        self._set_window_icon()

        self.f_eyebrow = ctk.CTkFont(UI_FAMILY, 12, "bold")
        self.f_title = ctk.CTkFont(UI_FAMILY, 24, "bold")
        self.f_body = ctk.CTkFont(UI_FAMILY, 14)
        self.f_label = ctk.CTkFont(UI_FAMILY, 13, "bold")
        self.f_small = ctk.CTkFont(UI_FAMILY, 12)
        self.f_button = ctk.CTkFont(UI_FAMILY, 14, "bold")
        self.f_mono = ctk.CTkFont(MONO_FAMILY, 13)

        # State shared by all steps
        self.source_var = ctk.StringVar()
        self.subfolders_var = ctk.BooleanVar(value=True)
        self.dest_var = ctk.StringVar(value=default_save_location())
        self.name_var = ctk.StringVar()
        self.mode_var = ctk.StringVar(value="both")
        self.order_var = ctk.StringVar(value=ORDER_DATE_FIRST)
        self.group_var = ctk.StringVar(value="Day")  # Day | Month | Year
        self.action_var = ctk.StringVar(value="copy")
        self.scan_result = None
        self.scanned_key = None
        self.scan_token = 0
        self.name_edited = False
        self.events: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.sorter: Sorter | None = None
        self.worker: threading.Thread | None = None
        self.summary = None
        self.geocoder = Geocoder()
        self.page_index = 0

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()
        self.pages = [self._build_source_page(), self._build_destination_page(),
                      self._build_options_page(), self._build_progress_page(), self._build_done_page()]
        self.dest_var.trace_add("write", lambda *_: self._refresh_destination())
        self.name_var.trace_add("write", lambda *_: self._refresh_destination())
        self.show_page(0)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(60, self._poll_events)

    # ------------------------------------------------------------------ frame
    def _set_window_icon(self):
        try:
            if IS_WINDOWS:
                self.iconbitmap(str(resource_path("assets", "icon.ico")))
            else:
                from PIL import ImageTk
                self._icon_img = ImageTk.PhotoImage(Image.open(resource_path("assets", "icon.png")))
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass

    def _build_sidebar(self):
        bar = ctk.CTkFrame(self, width=220, fg_color=SIDEBAR_BG, corner_radius=0)
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.pack_propagate(False)
        ctk.CTkFrame(self, width=1, fg_color=LINE, corner_radius=0).grid(row=0, column=0, sticky="nse")

        brand = ctk.CTkFrame(bar, fg_color="transparent")
        brand.pack(fill="x", padx=20, pady=(22, 18))
        ctk.CTkLabel(brand, text="", image=make_icon("photo", size=22)).pack(side="left")
        ctk.CTkLabel(brand, text=APP_NAME, font=ctk.CTkFont(UI_FAMILY, 15, "bold"),
                     text_color=TEXT).pack(side="left", padx=(10, 0))

        ctk.CTkLabel(bar, text="STEPS", font=ctk.CTkFont(UI_FAMILY, 11, "bold"), text_color=MUTED,
                     anchor="w").pack(fill="x", padx=26, pady=(4, 8))
        self.step_rows = []
        for i, name in enumerate(self.STEP_NAMES):
            row = ctk.CTkFrame(bar, fg_color="transparent", corner_radius=8, height=46)
            row.pack(fill="x", padx=14, pady=2)
            row.pack_propagate(False)
            circle = ctk.CTkLabel(row, text=str(i + 1), width=26, height=26, corner_radius=13,
                                  font=ctk.CTkFont(UI_FAMILY, 12, "bold"))
            circle.pack(side="left", padx=(12, 12))
            label = ctk.CTkLabel(row, text=name, font=ctk.CTkFont(UI_FAMILY, 14), anchor="w")
            label.pack(side="left", fill="x")
            self.step_rows.append((row, circle, label))
        about = ctk.CTkFrame(bar, fg_color="transparent")
        about.pack(side="bottom", fill="x", padx=14, pady=14)
        ctk.CTkButton(about, text="ⓘ  About", command=self.show_about, height=36, anchor="w",
                      font=ctk.CTkFont(UI_FAMILY, 13, "bold"), fg_color="transparent", hover_color=CURRENT_ROW,
                      text_color=TEXT, corner_radius=8).pack(fill="x")
        ctk.CTkLabel(about, text=f"Version {__version__}  ·  by {AUTHOR}", font=self.f_small, text_color=MUTED,
                     anchor="w", wraplength=180, justify="left").pack(fill="x", padx=12, pady=(2, 0))

    def _set_sidebar_step(self, current: int):
        for i, (row, circle, label) in enumerate(self.step_rows):
            if i < current:      # done
                row.configure(fg_color="transparent")
                circle.configure(text="✓", fg_color=ACCENT, text_color=WHITE)
                label.configure(text_color=TEXT, font=ctk.CTkFont(UI_FAMILY, 14))
            elif i == current:   # current
                row.configure(fg_color=CURRENT_ROW)
                circle.configure(text=str(i + 1), fg_color=ACCENT, text_color=WHITE)
                label.configure(text_color=TEXT, font=ctk.CTkFont(UI_FAMILY, 14, "bold"))
            else:                # upcoming
                row.configure(fg_color="transparent")
                circle.configure(text=str(i + 1), fg_color="#E3E7EC", text_color=MUTED)
                label.configure(text_color=MUTED, font=ctk.CTkFont(UI_FAMILY, 14))

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color=WHITE, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)
        self.content = ctk.CTkFrame(main, fg_color=WHITE, corner_radius=0)
        self.content.grid(row=0, column=0, sticky="nsew", padx=40, pady=(32, 16))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        ctk.CTkFrame(main, height=1, fg_color=LINE, corner_radius=0).grid(row=1, column=0, sticky="ew")
        footer = ctk.CTkFrame(main, fg_color=WHITE, corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew", padx=40, pady=16)
        self.back_btn = self._button(footer, "Back", self._go_back, primary=False, width=170)
        self.back_btn.pack(side="left")
        self.next_btn = self._button(footer, "Next  →", self._go_next, primary=True, width=170)
        self.next_btn.pack(side="right")

    def _button(self, master, text, command, primary=True, **kw):
        if primary:
            return ctk.CTkButton(master, text=text, command=command, height=42, corner_radius=8,
                                 font=self.f_button, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                 text_color=WHITE, text_color_disabled=DISABLED_TEXT, **kw)
        return ctk.CTkButton(master, text=text, command=command, height=42, corner_radius=8,
                             font=ctk.CTkFont(UI_FAMILY, 14), fg_color=WHITE, hover_color="#F1F3F5",
                             border_width=1, border_color=BORDER, text_color=TEXT,
                             text_color_disabled=DISABLED_TEXT, **kw)

    @staticmethod
    def _enable(button: ctk.CTkButton, enabled: bool, primary: bool = True):
        if primary:
            button.configure(state="normal" if enabled else "disabled",
                             fg_color=ACCENT if enabled else DISABLED_BG)
        else:
            button.configure(state="normal" if enabled else "disabled",
                             fg_color=WHITE if enabled else DISABLED_BG)

    def _page(self, step: int | None, title: str, body: str) -> ctk.CTkFrame:
        page = ctk.CTkFrame(self.content, fg_color=WHITE, corner_radius=0)
        if step is not None:
            ctk.CTkLabel(page, text=f"STEP {step} OF 4", font=self.f_eyebrow, text_color=ACCENT,
                         anchor="w").pack(fill="x")
        page.title_label = ctk.CTkLabel(page, text=title, font=self.f_title, text_color=TEXT, anchor="w",
                                        justify="left")
        page.title_label.pack(fill="x", pady=(4, 4))
        page.body_label = ctk.CTkLabel(page, text=body, font=self.f_body, text_color=MUTED, anchor="w",
                                       justify="left", wraplength=560)
        page.body_label.pack(fill="x", pady=(0, 20))
        return page

    def _label(self, master, text, **pack):
        lbl = ctk.CTkLabel(master, text=text, font=self.f_label, text_color=TEXT, anchor="w")
        lbl.pack(fill="x", **pack)
        return lbl

    def _path_row(self, master, variable, browse_command, placeholder=""):
        row = ctk.CTkFrame(master, fg_color="transparent")
        row.pack(fill="x", pady=(6, 0))
        entry = ctk.CTkEntry(row, textvariable=variable, height=42, corner_radius=8, border_width=1,
                             border_color=BORDER, fg_color=WHITE, text_color=TEXT, font=self.f_mono,
                             placeholder_text=placeholder)
        entry.pack(side="left", fill="x", expand=True)
        btn = self._button(row, "  Browse…", browse_command, primary=False, width=120,
                           image=make_icon("folder", TEXT, 16), compound="left")
        btn.pack(side="left", padx=(10, 0))
        return entry

    # ------------------------------------------------------------------ step 1: source
    def _build_source_page(self):
        p = self._page(1, "Choose your photos and videos",
                       "Pick the folder you want to sort. Nothing is changed until you press Start.")
        self._label(p, "Source folder")
        entry = self._path_row(p, self.source_var, self._browse_source, "Click Browse to pick a folder")
        entry.bind("<Return>", lambda _e: self._start_scan())
        entry.bind("<FocusOut>", lambda _e: self._start_scan())
        ctk.CTkCheckBox(p, text="Include subfolders", variable=self.subfolders_var, command=self._start_scan,
                        font=self.f_body, text_color=TEXT, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                        checkbox_width=20, checkbox_height=20, corner_radius=4,
                        border_width=2).pack(anchor="w", pady=(12, 20))

        card = ctk.CTkFrame(p, fg_color=CARD_BG, border_width=1, border_color=LINE, corner_radius=12)
        card.pack(fill="x")
        status_row = ctk.CTkFrame(card, fg_color="transparent")
        status_row.pack(fill="x", padx=20, pady=(16, 12))
        # The icon has its own label that is shown/hidden; clearing an icon with image=None
        # breaks CustomTkinter labels (that was the "frozen on second folder" bug).
        self.scan_icon = ctk.CTkLabel(status_row, text="", image=make_icon("check_circle", size=20), width=24)
        self.scan_status = ctk.CTkLabel(status_row, text="No folder selected yet.",
                                        font=ctk.CTkFont(UI_FAMILY, 14, "bold"), text_color=MUTED, anchor="w")
        self.scan_status.pack(side="left", fill="x", expand=True)
        tiles = ctk.CTkFrame(card, fg_color="transparent")
        tiles.pack(fill="x", padx=20, pady=(0, 20))
        for c in range(3):
            tiles.grid_columnconfigure(c, weight=1, uniform="tiles")
        self.tile_photos = StatTile(tiles, "Photos")
        self.tile_videos = StatTile(tiles, "Videos")
        self.tile_other = StatTile(tiles, "Other files (skipped)")
        for c, t in enumerate((self.tile_photos, self.tile_videos, self.tile_other)):
            t.grid(row=0, column=c, sticky="ew", padx=(0 if c == 0 else 6, 0 if c == 2 else 6))
        return p

    def _browse_source(self):
        start = self.source_var.get() or str(Path.home())
        folder = filedialog.askdirectory(title="Choose the folder with your photos and videos",
                                         initialdir=start if os.path.isdir(start) else str(Path.home()))
        if folder:
            self.source_var.set(os.path.normpath(folder))
            self._start_scan()

    def _start_scan(self):
        path = self.source_var.get().strip().strip('"')
        key = (path, self.subfolders_var.get())
        if key == self.scanned_key:
            return
        self.scanned_key = key
        self.scan_result = None
        self.scan_token += 1
        for t in (self.tile_photos, self.tile_videos, self.tile_other):
            t.set("–")
        if not path:
            self._set_scan_status("No folder selected yet.", MUTED)
        elif not os.path.isdir(path):
            self._set_scan_status("That folder doesn't exist. Please check the path.", ERROR)
        else:
            self._set_scan_status("Scanning the folder…", MUTED)
            token, subfolders = self.scan_token, self.subfolders_var.get()

            def work():
                try:
                    self.events.put(("scan", token, scan(Path(path), subfolders), None))
                except Exception as exc:
                    self.events.put(("scan", token, None, exc))

            threading.Thread(target=work, daemon=True).start()
        self._refresh_footer()

    def _scan_finished(self, token, result, error):
        if token != self.scan_token:
            return  # an older scan; the user picked another folder since
        if error:
            self._set_scan_status(f"Couldn't read that folder: {error}", ERROR)
        else:
            self.scan_result = result
            self.tile_photos.set(f"{len(result.photos):,}")
            self.tile_videos.set(f"{len(result.videos):,}")
            self.tile_other.set(f"{result.skipped:,}", MUTED)
            if result.total:
                self._set_scan_status("Folder scanned — ready to sort", TEXT, ok_icon=True)
            else:
                self._set_scan_status("No photos or videos found in this folder.", WARN)
        self._refresh_footer()

    def _set_scan_status(self, text: str, color: str, ok_icon: bool = False):
        self.scan_status.configure(text=text, text_color=color)
        if ok_icon:
            self.scan_icon.pack(side="left", padx=(0, 8), before=self.scan_status)
        else:
            self.scan_icon.pack_forget()

    # ------------------------------------------------------------------ step 2: destination
    def _build_destination_page(self):
        p = self._page(2, "Where should the sorted folder go?",
                       "A new folder will be created here, and all sorted files will go inside it.")
        self._label(p, "Save location")
        self._path_row(p, self.dest_var, self._browse_dest)
        self._label(p, "Name of the new folder", pady=(20, 0))
        name_entry = ctk.CTkEntry(p, textvariable=self.name_var, height=42, corner_radius=8, border_width=1,
                                  border_color=BORDER, fg_color=WHITE, text_color=TEXT,
                                  font=ctk.CTkFont(UI_FAMILY, 15, "bold"))
        name_entry.pack(fill="x", pady=(6, 0))
        name_entry.bind("<Key>", lambda _e: setattr(self, "name_edited", True))
        self.name_hint = ctk.CTkLabel(p, text='Names can\'t use these characters:  \\ / : * ? " < > |',
                                      font=self.f_small, text_color=MUTED, anchor="w")
        self.name_hint.pack(fill="x", pady=(4, 20))

        card = ctk.CTkFrame(p, fg_color=SIDEBAR_BG, border_width=1, border_color=LINE, corner_radius=12)
        card.pack(fill="x")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=16)
        ctk.CTkLabel(inner, text="", image=make_icon("folder", ACCENT, 22)).pack(side="left", anchor="n")
        text_col = ctk.CTkFrame(inner, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True, padx=(14, 0))
        self.dest_preview_title = ctk.CTkLabel(text_col, text="Will be created at", font=self.f_label,
                                               text_color=TEXT, anchor="w")
        self.dest_preview_title.pack(fill="x")
        self.dest_preview = ctk.CTkLabel(text_col, text="", font=self.f_mono, text_color=TEXT, anchor="w",
                                         justify="left", wraplength=500)
        self.dest_preview.pack(fill="x", pady=(4, 0))
        return p

    def _browse_dest(self):
        start = self.dest_var.get()
        folder = filedialog.askdirectory(title="Where should the sorted folder be saved?",
                                         initialdir=start if os.path.isdir(start) else str(Path.home()))
        if folder:
            self.dest_var.set(os.path.normpath(folder))

    def _dest_root(self) -> Path:
        return Path(self.dest_var.get().strip().strip('"')) / self.name_var.get().strip()

    def _destination_problem(self) -> str | None:
        dest = self.dest_var.get().strip().strip('"')
        if not dest:
            return "Please choose where to save the folder."
        if not os.path.isdir(dest):
            return "That save location doesn't exist. Please pick a folder with Browse."
        problem = folder_name_problem(self.name_var.get())
        if problem:
            return problem
        source = Path(self.source_var.get().strip().strip('"'))
        if self._dest_root().resolve() == source.resolve():
            return "The new folder can't be the same as the source folder."
        return None

    def _refresh_destination(self):
        name_problem = folder_name_problem(self.name_var.get()) if self.name_var.get() else None
        self.name_hint.configure(text=name_problem or 'Names can\'t use these characters:  \\ / : * ? " < > |',
                                 text_color=ERROR if name_problem else MUTED)
        name = self.name_var.get().strip() or "[folder name]"
        dest = self.dest_var.get().strip().strip('"').rstrip("\\/")
        full = Path(dest) / name if dest else Path(name)
        self.dest_preview.configure(text=str(full))
        if full.is_dir():
            self.dest_preview_title.configure(text="This folder already exists — sorted files will be added to it")
        else:
            self.dest_preview_title.configure(text="Will be created at")
        self._refresh_example()
        self._refresh_footer()

    # ------------------------------------------------------------------ step 3: options
    def _build_options_page(self):
        p = self._page(3, "How should we organize them?",
                       "Date and location are read from each file's hidden details.")
        cards = ctk.CTkFrame(p, fg_color="transparent")
        cards.pack(fill="x")
        for c in range(3):
            cards.grid_columnconfigure(c, weight=1, uniform="cards")
        self.cards = [
            ChoiceCard(cards, "calendar", "By date", "One folder per day, month or year",
                       self.mode_var, "date", self._options_changed),
            ChoiceCard(cards, "pin", "By location", "One folder per place, like the town name",
                       self.mode_var, "location", self._options_changed),
            ChoiceCard(cards, "layers", "Both", "Dates and places, nested inside each other",
                       self.mode_var, "both", self._options_changed),
        ]
        for c, card in enumerate(self.cards):
            card.grid(row=0, column=c, sticky="nsew", padx=(0 if c == 0 else 6, 0 if c == 2 else 6))

        self.group_row = ctk.CTkFrame(p, fg_color="transparent")
        self.group_row.pack(fill="x", pady=(18, 0))
        ctk.CTkLabel(self.group_row, text="Group dates by", font=self.f_label, text_color=TEXT).pack(side="left")
        self._segmented(self.group_row, ["Day", "Month", "Year"], self.group_var, width=330).pack(side="right")

        self.order_row = ctk.CTkFrame(p, fg_color="transparent")
        self.order_row.pack(fill="x", pady=(12, 0))
        ctk.CTkLabel(self.order_row, text="Folder order", font=self.f_label, text_color=TEXT).pack(side="left")
        self._segmented(self.order_row, [ORDER_DATE_FIRST, ORDER_LOCATION_FIRST], self.order_var,
                        width=330).pack(side="right")

        self.action_box = ctk.CTkFrame(p, fg_color="transparent")
        self.action_box.pack(fill="x", pady=(18, 0))
        self.action_box.grid_columnconfigure((0, 1), weight=1, uniform="act")
        self.action_tiles = []
        for c, (value, title, desc) in enumerate((
                ("copy", "Copy files", "Keeps the originals · recommended"),
                ("move", "Move files", "Saves disk space, empties the source"))):
            tile = ctk.CTkFrame(self.action_box, fg_color=WHITE, border_width=2, border_color="#D9DEE4",
                                corner_radius=10)
            tile.grid(row=0, column=c, sticky="nsew", padx=(0 if c == 0 else 6, 6 if c == 0 else 0))
            radio = ctk.CTkRadioButton(tile, text=title, variable=self.action_var, value=value,
                                       command=self._options_changed, font=ctk.CTkFont(UI_FAMILY, 14, "bold"),
                                       text_color=TEXT, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                       radiobutton_width=18, radiobutton_height=18)
            radio.pack(anchor="w", padx=14, pady=(12, 0))
            sub = ctk.CTkLabel(tile, text=desc, font=self.f_small, text_color=MUTED, anchor="w",
                               justify="left", wraplength=200)
            sub.pack(anchor="w", padx=(44, 14), pady=(0, 12))
            for w in (tile, sub):
                w.bind("<Button-1>", lambda _e, v=value: (self.action_var.set(v), self._options_changed()))
            self.action_tiles.append((tile, value))

        example = ctk.CTkFrame(p, fg_color=SIDEBAR_BG, border_width=1, border_color=LINE, corner_radius=10)
        example.pack(fill="x", pady=(18, 0))
        ctk.CTkLabel(example, text="Example", font=self.f_label, text_color=MUTED).pack(side="left", padx=(16, 10),
                                                                                    pady=12)
        self.example_label = ctk.CTkLabel(example, text="", font=self.f_mono, text_color=TEXT, anchor="w")
        self.example_label.pack(side="left", fill="x", expand=True, pady=12)
        self._options_changed()
        return p

    def _segmented(self, master, values, variable, width=None):
        return ctk.CTkSegmentedButton(master, values=values, variable=variable,
                                      command=lambda _v: self._options_changed(), width=width or 0,
                                      height=38, font=ctk.CTkFont(UI_FAMILY, 13, "bold"), fg_color="#E6EAEF",
                                      selected_color=WHITE, selected_hover_color="#F7F9FB",
                                      unselected_color="#E6EAEF", unselected_hover_color="#DCE2E9",
                                      text_color=TEXT, text_color_disabled=MUTED, dynamic_resizing=False)

    def _options_changed(self):
        for card in self.cards:
            card.refresh()
        mode = self.mode_var.get()
        self.group_row.pack_forget()
        self.order_row.pack_forget()
        if mode in ("date", "both"):
            self.group_row.pack(fill="x", pady=(18, 0), before=self.action_box)
        if mode == "both":
            self.order_row.pack(fill="x", pady=(12, 0), before=self.action_box)
        for tile, value in self.action_tiles:
            selected = self.action_var.get() == value
            tile.configure(border_color=ACCENT if selected else "#D9DEE4",
                           fg_color=SELECTED_BG if selected else WHITE)
        self._refresh_example()

    def _refresh_example(self):
        if not hasattr(self, "example_label"):
            return
        root = self.name_var.get().strip() or "Sorted"
        day = SortOptions(date_group=self.group_var.get().lower()).date_label(datetime.now())
        place = "Town name"
        mode = self.mode_var.get()
        if mode == "date":
            parts = [root, day]
        elif mode == "location":
            parts = [root, place]
        elif self.order_var.get() == ORDER_DATE_FIRST:
            parts = [root, day, place]
        else:
            parts = [root, place, day]
        self.example_label.configure(text="\\".join(parts + ["IMG_0412.jpg"]))

    # ------------------------------------------------------------------ step 4: progress
    def _build_progress_page(self):
        p = self._page(4, "Sorting your files…",
                       "You can keep using your PC. A summary appears when it's finished.")
        top = ctk.CTkFrame(p, fg_color="transparent")
        top.pack(fill="x")
        self.progress_count = ctk.CTkLabel(top, text="", font=ctk.CTkFont(UI_FAMILY, 15, "bold"),
                                           text_color=TEXT)
        self.progress_count.pack(side="left", anchor="s")
        self.progress_pct = ctk.CTkLabel(top, text="0%", font=ctk.CTkFont(UI_FAMILY, 28, "bold"),
                                         text_color=ACCENT)
        self.progress_pct.pack(side="right")
        self.progress_bar = ctk.CTkProgressBar(p, height=12, corner_radius=6, fg_color=LINE,
                                               progress_color=ACCENT)
        self.progress_bar.pack(fill="x", pady=(8, 12))
        self.progress_bar.set(0)
        now = ctk.CTkFrame(p, fg_color=SIDEBAR_BG, corner_radius=10)
        now.pack(fill="x")
        self.progress_verb = ctk.CTkLabel(now, text="Now copying", font=self.f_label, text_color=MUTED)
        self.progress_verb.pack(side="left", padx=(14, 10), pady=12)
        self.progress_file = ctk.CTkLabel(now, text="", font=ctk.CTkFont(MONO_FAMILY, 12), text_color=TEXT,
                                          anchor="w")
        self.progress_file.pack(side="left", fill="x", expand=True, pady=12)

        tiles = ctk.CTkFrame(p, fg_color="transparent")
        tiles.pack(fill="x", pady=(24, 0))
        for c in range(3):
            tiles.grid_columnconfigure(c, weight=1, uniform="ptiles")
        self.ptile_photos = StatTile(tiles, "Photos sorted")
        self.ptile_videos = StatTile(tiles, "Videos sorted")
        self.ptile_noloc = StatTile(tiles, "No location found")
        for c, t in enumerate((self.ptile_photos, self.ptile_videos, self.ptile_noloc)):
            t.grid(row=0, column=c, sticky="ew", padx=(0 if c == 0 else 6, 0 if c == 2 else 6))
        return p

    def _start_sorting(self):
        dest_root = self._dest_root()
        files = [f for f in self.scan_result.files if not is_inside(f, dest_root)]
        options = SortOptions(
            mode=self.mode_var.get(),
            order="date" if self.order_var.get() == ORDER_DATE_FIRST else "location",
            date_group=self.group_var.get().lower(),
            action=self.action_var.get(),
        )
        self.cancel_event = threading.Event()
        self.sorter = Sorter(files, dest_root, options,
                             progress=lambda d, t, txt: self.events.put(("progress", d, t, txt)),
                             cancel=self.cancel_event, geocoder=self.geocoder)
        self.progress_bar.set(0)
        self.progress_pct.configure(text="0%", text_color=ACCENT)
        self.progress_bar.configure(progress_color=ACCENT)
        self.progress_count.configure(text=f"0 of {len(files):,} files")
        self.progress_verb.configure(text="Now copying" if options.action == "copy" else "Now moving")
        self.progress_file.configure(text="Getting ready…")
        for t in (self.ptile_photos, self.ptile_videos):
            t.set(0)
        self.ptile_noloc.set(0 if options.mode != "date" else "–", WARN)

        def work():
            try:
                self.events.put(("done", self.sorter.run()))
            except Exception as exc:
                self.events.put(("failed", exc))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self.show_page(3)

    def _show_progress(self, done, total, text):
        pct = int(done * 100 / total) if total else 100
        self.progress_bar.set(done / total if total else 1)
        self.progress_pct.configure(text=f"{pct}%")
        self.progress_count.configure(text=f"{done:,} of {total:,} files")
        if text and text != "Finished":
            self.progress_file.configure(text=text)
        live = self.sorter.summary if self.sorter else None
        if live:
            self.ptile_photos.set(f"{live.photos:,}")
            self.ptile_videos.set(f"{live.videos:,}")
            if self.mode_var.get() != "date":
                self.ptile_noloc.set(f"{live.no_location:,}", WARN)

    def _cancel_sorting(self):
        if self.worker and self.worker.is_alive():
            if messagebox.askyesno(APP_NAME, "Stop sorting?\n\nFiles that are already sorted stay in the new "
                                             "folder. The rest are left where they are."):
                self.cancel_event.set()
                self.progress_file.configure(text="Stopping after the current file…")
                self._enable(self.back_btn, False, primary=False)

    # ------------------------------------------------------------------ done
    def _build_done_page(self):
        p = ctk.CTkFrame(self.content, fg_color=WHITE, corner_radius=0)
        head = ctk.CTkFrame(p, fg_color="transparent")
        head.pack(fill="x")
        self.done_icon = ctk.CTkLabel(head, text="", image=make_icon("check_circle", size=48))
        self.done_icon.pack(side="left", anchor="n")
        col = ctk.CTkFrame(head, fg_color="transparent")
        col.pack(side="left", fill="x", expand=True, padx=(16, 0))
        self.done_title = ctk.CTkLabel(col, text="", font=self.f_title, text_color=TEXT, anchor="w")
        self.done_title.pack(fill="x")
        self.done_path = ctk.CTkLabel(col, text="", font=self.f_body, text_color=MUTED, anchor="w",
                                      justify="left", wraplength=520)
        self.done_path.pack(fill="x")

        body = ctk.CTkFrame(p, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(22, 0))
        body.grid_columnconfigure(0, weight=2, uniform="done")
        body.grid_columnconfigure(1, weight=3, uniform="done")
        body.grid_rowconfigure(0, weight=1)
        self.summary_box = ctk.CTkFrame(body, fg_color=WHITE, border_width=1, border_color=LINE, corner_radius=12)
        self.summary_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tree_box = ctk.CTkFrame(body, fg_color=SIDEBAR_BG, border_width=1, border_color=LINE, corner_radius=12)
        tree_box.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ctk.CTkLabel(tree_box, text="Folder preview", font=self.f_label, text_color=TEXT,
                     anchor="w").pack(fill="x", padx=16, pady=(14, 4))
        self.tree_text = ctk.CTkTextbox(tree_box, font=ctk.CTkFont(MONO_FAMILY, 12), fg_color=SIDEBAR_BG,
                                        text_color=TEXT, wrap="none", border_width=0, activate_scrollbars=True)
        self.tree_text.pack(fill="both", expand=True, padx=8, pady=(0, 10))

        self.log_link = ctk.CTkButton(p, text="View the log of every file", command=self._open_log,
                                      fg_color="transparent", hover_color="#EEF2F8", text_color=ACCENT,
                                      font=ctk.CTkFont(UI_FAMILY, 13, "bold"), height=32, anchor="w", width=10)
        self.log_link.pack(anchor="w", pady=(12, 0))
        return p

    def _fill_done_page(self, s):
        total = s.sorted_count
        if s.cancelled:
            self.done_icon.configure(image=make_icon("stop_circle", size=48))
            self.done_title.configure(text=f"Stopped — {total:,} file{'s' if total != 1 else ''} sorted")
        else:
            self.done_icon.configure(image=make_icon("check_circle", size=48))
            self.done_title.configure(text=f"All done — {total:,} file{'s' if total != 1 else ''} sorted")
        self.done_path.configure(text=f"Your folder is ready at  {s.dest_root}")

        for w in self.summary_box.winfo_children():
            w.destroy()
        rows = [("Photos", f"{s.photos:,}", TEXT), ("Videos", f"{s.videos:,}", TEXT)]
        if self.mode_var.get() != "location":
            rows.append((f"{self.group_var.get()} folders", f"{len(s.day_folders):,}", TEXT))
        if self.mode_var.get() != "date":
            rows.append(("Place folders", f"{len(s.place_folders):,}", TEXT))
            rows.append(("No location", f"{s.no_location:,}", WARN if s.no_location else TEXT))
        if s.duplicates:
            rows.append(("Already there (skipped)", f"{s.duplicates:,}", MUTED))
        if s.errors:
            rows.append(("Problems (see log)", f"{len(s.errors):,}", ERROR))
        for i, (label, value, color) in enumerate(rows):
            row = ctk.CTkFrame(self.summary_box, fg_color="transparent")
            row.pack(fill="x", padx=18, pady=(12 if i == 0 else 0, 0))
            ctk.CTkLabel(row, text=label, font=self.f_body, text_color=MUTED, anchor="w").pack(side="left", pady=8)
            ctk.CTkLabel(row, text=value, font=ctk.CTkFont(UI_FAMILY, 15, "bold"),
                         text_color=color).pack(side="right", pady=8)
            if i < len(rows) - 1:
                ctk.CTkFrame(self.summary_box, height=1, fg_color="#EEF1F4").pack(fill="x", padx=18)

        self.tree_text.configure(state="normal")
        self.tree_text.delete("1.0", "end")
        self.tree_text.insert("1.0", folder_tree_text(s.dest_root.name, s.folder_counts) if s.folder_counts
                              else "No new files were added.")
        self.tree_text.configure(state="disabled")

    def _open_log(self):
        if self.summary and self.summary.log_path and self.summary.log_path.exists():
            open_path(self.summary.log_path)

    def _restart(self):
        self.summary = None
        self.sorter = None
        self.scanned_key = None  # rescan: files may have moved
        self.name_edited = False
        self.name_var.set("")
        self._start_scan()
        self.show_page(0)

    # ------------------------------------------------------------------ about
    def show_about(self):
        if getattr(self, "_about", None) is not None and self._about.winfo_exists():
            self._about.focus()
            return
        win = ctk.CTkToplevel(self, fg_color=WHITE)
        self._about = win
        win.title(f"About {APP_NAME}")
        win.geometry("440x480")
        win.resizable(False, False)
        win.transient(self)
        try:
            if IS_WINDOWS:
                win.after(250, lambda: win.iconbitmap(str(resource_path("assets", "icon.ico"))))
        except Exception:
            pass

        try:
            logo = ctk.CTkImage(Image.open(resource_path("assets", "icon.png")), size=(72, 72))
            ctk.CTkLabel(win, text="", image=logo).pack(pady=(28, 10))
        except Exception:
            pass
        ctk.CTkLabel(win, text=APP_NAME, font=ctk.CTkFont(UI_FAMILY, 22, "bold"), text_color=TEXT).pack()
        ctk.CTkLabel(win, text=f"Version {__version__}", font=self.f_body, text_color=MUTED).pack(pady=(2, 10))
        ctk.CTkLabel(win, text=DESCRIPTION, font=self.f_body, text_color=TEXT, wraplength=360).pack(padx=30)

        maker = ctk.CTkFrame(win, fg_color=SIDEBAR_BG, corner_radius=12, border_width=1, border_color=LINE)
        maker.pack(fill="x", padx=30, pady=(20, 0))
        ctk.CTkLabel(maker, text="DEVELOPED BY", font=ctk.CTkFont(UI_FAMILY, 11, "bold"),
                     text_color=MUTED).pack(pady=(14, 0))
        ctk.CTkLabel(maker, text=AUTHOR, font=ctk.CTkFont(UI_FAMILY, 17, "bold"), text_color=TEXT).pack()
        ctk.CTkButton(maker, text=GITHUB_URL.replace("https://", ""), command=lambda: webbrowser.open(GITHUB_URL),
                      fg_color="transparent", hover_color=CURRENT_ROW, text_color=ACCENT, height=32,
                      font=ctk.CTkFont(UI_FAMILY, 13, "bold")).pack(pady=(2, 12))

        ctk.CTkLabel(win, text="Town names: GeoNames (CC BY 4.0) · Works offline — your photos never leave this PC.",
                     font=self.f_small, text_color=MUTED, wraplength=380, justify="center").pack(padx=30, pady=(16, 0))
        buttons = ctk.CTkFrame(win, fg_color="transparent")
        buttons.pack(side="bottom", fill="x", padx=30, pady=22)
        self._button(buttons, "More info", lambda: webbrowser.open(GITHUB_URL), primary=False,
                     width=180).pack(side="left")
        self._button(buttons, "Close", win.destroy, width=180).pack(side="right")
        win.after(100, win.grab_set)

    # ------------------------------------------------------------------ navigation
    def show_page(self, index: int):
        for page in self.pages:
            page.grid_remove()
        self.pages[index].grid(row=0, column=0, sticky="nsew")
        self.page_index = index
        self._set_sidebar_step(min(index, 4) if index < 4 else 4)
        self._refresh_footer()

    def _refresh_footer(self):
        i = getattr(self, "page_index", 0)
        if not hasattr(self, "next_btn"):
            return
        self.back_btn.pack(side="left")
        self.next_btn.pack(side="right")
        if i == 0:
            self.back_btn.configure(text="Back", command=self._go_back)
            self._enable(self.back_btn, False, primary=False)
            self.next_btn.configure(text="Next  →", command=self._go_next)
            self._enable(self.next_btn, bool(self.scan_result and self.scan_result.total))
        elif i == 1:
            self.back_btn.configure(text="Back", command=self._go_back)
            self._enable(self.back_btn, True, primary=False)
            self.next_btn.configure(text="Next  →", command=self._go_next)
            self._enable(self.next_btn, self._destination_problem() is None)
        elif i == 2:
            self.back_btn.configure(text="Back", command=self._go_back)
            self._enable(self.back_btn, True, primary=False)
            self.next_btn.configure(text="▶  Start sorting", command=self._go_next)
            self._enable(self.next_btn, True)
        elif i == 3:
            self.back_btn.configure(text="Cancel", command=self._cancel_sorting)
            self._enable(self.back_btn, not self.cancel_event.is_set(), primary=False)
            self.next_btn.configure(text="View summary  →", command=lambda: None)
            self._enable(self.next_btn, False)
        else:
            self.back_btn.configure(text="Sort another folder", command=self._restart)
            self._enable(self.back_btn, True, primary=False)
            self.next_btn.configure(text="Open folder", command=lambda: open_path(self.summary.dest_root))
            self._enable(self.next_btn, True)

    def _go_back(self):
        if self.page_index in (1, 2):
            self.show_page(self.page_index - 1)

    def _go_next(self):
        i = self.page_index
        if i == 0:
            if not (self.scan_result and self.scan_result.total):
                return
            if not self.name_edited or not self.name_var.get().strip():
                source_name = Path(self.source_var.get().strip().strip('"')).name or "Photos"
                self.name_var.set(f"{source_name} - Sorted")
            self.show_page(1)
            self._refresh_destination()
        elif i == 1:
            problem = self._destination_problem()
            if problem:
                messagebox.showwarning(APP_NAME, problem)
                return
            self.show_page(2)
        elif i == 2:
            if self.action_var.get() == "move" and not messagebox.askyesno(
                    APP_NAME, "Move files?\n\nYour photos and videos will be moved out of the source folder "
                              "into the new folder. Choose Copy if you want to keep the originals."):
                return
            self._start_sorting()

    # ------------------------------------------------------------------ background events
    def _poll_events(self):
        latest_progress = None
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "scan":
                    self._scan_finished(*event[1:])
                elif kind == "progress":
                    latest_progress = event[1:]
                elif kind == "done":
                    if latest_progress:
                        self._show_progress(*latest_progress)
                        latest_progress = None
                    self._sorting_finished(event[1])
                elif kind == "failed":
                    messagebox.showerror(APP_NAME, f"Sorting stopped because of an error:\n\n{event[1]}")
                    self.show_page(2)
        except queue.Empty:
            pass
        if latest_progress and self.page_index == 3:
            self._show_progress(*latest_progress)
        self.after(60, self._poll_events)

    def _sorting_finished(self, summary):
        self.summary = summary
        self.progress_bar.configure(progress_color=SUCCESS)
        self.progress_pct.configure(text_color=SUCCESS)
        self.progress_file.configure(text="All files sorted" if not summary.cancelled else "Stopped")
        self._fill_done_page(summary)
        self.after(700, lambda: self.show_page(4))

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(APP_NAME, "Sorting is still running.\n\nStop and close Media Sorter? "
                                                 "Files already sorted stay in the new folder."):
                return
            self.cancel_event.set()
            self.worker.join(timeout=15)
        self.destroy()


def log_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def run():
    import logging
    import traceback

    log_file = log_dir() / "error.log"
    logging.basicConfig(filename=str(log_file), level=logging.WARNING, encoding="utf-8",
                        format="%(asctime)s  %(message)s")
    # A windowed .exe has no console; send any stray output to the log instead of nowhere.
    if sys.stdout is None or sys.stderr is None:
        stream = open(log_file, "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - lives as long as the app
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream

    def log_thread_error(args):
        logging.error("Background error:\n%s",
                      "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))

    threading.excepthook = log_thread_error

    app = App()
    shown = {"count": 0}

    def on_error(exc_type, exc, tb):
        logging.error("Unexpected error (v%s):\n%s", __version__,
                      "".join(traceback.format_exception(exc_type, exc, tb)))
        if shown["count"] < 2:  # don't bury the user in pop-ups
            shown["count"] += 1
            messagebox.showwarning(APP_NAME, "Something went wrong, but your files are safe.\n\n"
                                             "Please try again. If it keeps happening, send this file to the "
                                             f"developer:\n{log_file}")

    app.report_callback_exception = on_error
    app.mainloop()
