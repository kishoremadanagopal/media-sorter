"""The sorting engine: scan a folder, work out where each file belongs,
then copy or move it there. No user interface code lives here, so the
same engine can be reused by Version 2 (documents) or a command line tool.
"""

from __future__ import annotations

import csv
import filecmp
import os
import re
import shutil
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from .geocode import Geocoder
from .metadata import kind_of, read_info

UNKNOWN_LOCATION = "Unknown Location"
INVALID_NAME_CHARS = '\\/:*?"<>|'
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


# --------------------------------------------------------------------------- helpers

def safe_folder_name(name: str, fallback: str = "Unnamed") -> str:
    """Make any text safe to use as a Windows folder name."""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip().rstrip(". ")
    if not cleaned:
        cleaned = fallback
    if cleaned.upper() in _RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned[:100]


def folder_name_problem(name: str) -> str | None:
    """Return a friendly error message if the user's folder name can't be used."""
    if not name.strip():
        return "Please enter a folder name."
    bad = sorted({c for c in name if c in INVALID_NAME_CHARS})
    if bad:
        return "Folder names can't contain: " + " ".join(bad)
    if name.strip().endswith("."):
        return "Folder names can't end with a dot."
    if name.strip().rstrip(". ").upper() in _RESERVED:
        return "Windows doesn't allow that folder name. Please choose another."
    if len(name) > 100:
        return "That name is too long. Please keep it under 100 characters."
    return None


def is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def folder_tree_text(root_name: str, counts: Counter, max_lines: int = 400) -> str:
    """Draw the created folders as a text tree with file counts."""
    tree: dict = {}
    for parts, n in counts.items():
        node = tree
        for part in parts:
            node = node.setdefault(part, {"__n__": 0})
            node["__n__"] += n

    rows: list[tuple[str, int]] = []

    def walk(node: dict, prefix: str):
        names = sorted(k for k in node if k != "__n__")
        names.sort(key=lambda k: (k == UNKNOWN_LOCATION, k))  # Unknown Location last
        for i, name in enumerate(names):
            last = i == len(names) - 1
            rows.append((f"{prefix}{'└── ' if last else '├── '}{name}\\", node[name]["__n__"]))
            walk(node[name], prefix + ("    " if last else "│   "))

    walk(tree, "")
    width = max((len(label) for label, _ in rows), default=0) + 2
    lines = [root_name + "\\"] + [f"{label:<{width}}{n:>4}" for label, n in rows]
    if len(lines) > max_lines:
        hidden = len(lines) - max_lines
        lines = lines[:max_lines] + [f"… and {hidden} more folders"]
    return "\n".join(lines)


# --------------------------------------------------------------------------- scanning

@dataclass
class ScanResult:
    photos: list[Path] = field(default_factory=list)
    videos: list[Path] = field(default_factory=list)
    skipped: int = 0

    @property
    def files(self) -> list[Path]:
        return self.photos + self.videos

    @property
    def total(self) -> int:
        return len(self.photos) + len(self.videos)


def scan(source: Path, include_subfolders: bool = True, exclude: Path | None = None,
         cancel: threading.Event | None = None) -> ScanResult:
    """Find every photo and video in the source folder."""
    result = ScanResult()
    source = Path(source)
    if include_subfolders:
        walker = os.walk(source)
    else:
        walker = [(str(source), [], [e.name for e in os.scandir(source) if e.is_file()])]
    for dirpath, dirnames, filenames in walker:
        if cancel and cancel.is_set():
            break
        here = Path(dirpath)
        if exclude is not None and is_inside(here, exclude):
            dirnames[:] = []
            continue
        dirnames.sort()
        for name in sorted(filenames):
            path = here / name
            kind = kind_of(path)
            if kind == "photo":
                result.photos.append(path)
            elif kind == "video":
                result.videos.append(path)
            else:
                result.skipped += 1
    return result


# --------------------------------------------------------------------------- sorting

MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December")


@dataclass
class SortOptions:
    mode: str = "both"        # "date" | "location" | "both"
    order: str = "date"       # for "both": "date" (Date -> Location) or "location" (Location -> Date)
    action: str = "copy"      # "copy" | "move"
    date_group: str = "day"   # "day" (2026-10-08) | "month" (2026-10 October) | "year" (2026)

    def date_label(self, taken: datetime) -> str:
        """Folder name for a date. Numbers first, so folders sort in time order."""
        if self.date_group == "year":
            return f"{taken.year}"
        if self.date_group == "month":
            return f"{taken.year}-{taken.month:02d} {MONTH_NAMES[taken.month - 1]}"
        return taken.strftime("%Y-%m-%d")


@dataclass
class SortSummary:
    dest_root: Path
    photos: int = 0
    videos: int = 0
    no_location: int = 0
    duplicates: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)
    day_folders: set[str] = field(default_factory=set)   # date folders (day, month or year)
    place_folders: set[str] = field(default_factory=set)
    folder_counts: Counter = field(default_factory=Counter)  # relative folder parts -> file count
    log_path: Path | None = None
    cancelled: bool = False

    @property
    def sorted_count(self) -> int:
        return self.photos + self.videos


ProgressCallback = Callable[[int, int, str], None]


class Sorter:
    def __init__(self, files: list[Path], dest_root: Path, options: SortOptions,
                 progress: ProgressCallback | None = None,
                 cancel: threading.Event | None = None,
                 geocoder: Geocoder | None = None):
        self.files = files
        self.dest_root = Path(dest_root)
        self.options = options
        self.progress = progress or (lambda done, total, text: None)
        self.cancel = cancel or threading.Event()
        self.geocoder = geocoder or Geocoder()
        self.summary: SortSummary | None = None  # live counters, readable while running

    # Where should this file go? Returns the list of folder names under dest_root.
    def folder_parts(self, taken: datetime, place: str | None) -> list[str]:
        day = self.options.date_label(taken)
        place = place or UNKNOWN_LOCATION
        mode = self.options.mode
        if mode == "date":
            return [day]
        if mode == "location":
            return [place]
        return [day, place] if self.options.order == "date" else [place, day]

    @staticmethod
    def _target_for(folder: Path, src: Path) -> tuple[Path, bool]:
        """Pick a free file name in folder. Returns (target, is_exact_duplicate)."""
        target = folder / src.name
        n = 1
        while target.exists():
            try:
                if target.stat().st_size == src.stat().st_size and filecmp.cmp(src, target, shallow=False):
                    return target, True
            except OSError:
                pass
            target = folder / f"{src.stem} ({n}){src.suffix}"
            n += 1
        return target, False

    def run(self) -> SortSummary:
        summary = SortSummary(dest_root=self.dest_root)
        self.summary = summary
        self.dest_root.mkdir(parents=True, exist_ok=True)
        need_place = self.options.mode in ("location", "both")
        total = len(self.files)
        stamp = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        summary.log_path = self.dest_root / f"Media Sorter log {stamp}.csv"
        verb = "Copying" if self.options.action == "copy" else "Moving"

        with open(summary.log_path, "w", newline="", encoding="utf-8-sig") as log_file:
            log = csv.writer(log_file)
            log.writerow(["Original file", "Saved as", "Type", "Date taken", "Date found from",
                          "Latitude", "Longitude", "Place", "Result"])

            for done, src in enumerate(self.files):
                if self.cancel.is_set():
                    summary.cancelled = True
                    break
                kind = kind_of(src) or "photo"
                row_gps = ("", "")
                place_name = ""
                try:
                    info = read_info(src, kind)
                    place = None
                    if info.gps:
                        row_gps = (f"{info.gps[0]:.6f}", f"{info.gps[1]:.6f}")
                        if need_place:
                            place = self.geocoder.lookup(*info.gps)
                    place_name = safe_folder_name(place.name) if place else ""
                    parts = self.folder_parts(info.taken, place_name or None)
                    folder = self.dest_root.joinpath(*parts)
                    self.progress(done, total, f"{src.name}  →  {chr(92).join(parts)}")
                    folder.mkdir(parents=True, exist_ok=True)

                    target, duplicate = self._target_for(folder, src)
                    if duplicate:
                        result = "Skipped: identical file already there"
                        summary.duplicates += 1
                        if self.options.action == "move":
                            # Same file is already sorted; leave the original where it is.
                            result += " (original left in place)"
                    else:
                        if self.options.action == "move":
                            shutil.move(str(src), str(target))
                        else:
                            shutil.copy2(src, target)
                        result = "Moved" if self.options.action == "move" else "Copied"
                        if kind == "video":
                            summary.videos += 1
                        else:
                            summary.photos += 1
                        if need_place and not place_name:
                            summary.no_location += 1
                        if self.options.mode in ("date", "both"):
                            summary.day_folders.add(self.options.date_label(info.taken))
                        if self.options.mode in ("location", "both") and place_name:
                            summary.place_folders.add(place_name)
                        summary.folder_counts[tuple(parts)] += 1

                    log.writerow([str(src), str(target), kind, info.taken.strftime("%Y-%m-%d %H:%M:%S"),
                                  info.date_source, *row_gps, place_name or UNKNOWN_LOCATION if need_place else "",
                                  result])
                except Exception as exc:  # keep going; report at the end
                    summary.errors.append((str(src), str(exc)))
                    log.writerow([str(src), "", kind, "", "", *row_gps, place_name, f"Error: {exc}"])

            self.progress(total if not summary.cancelled else done, total, "Finished")
        return summary
