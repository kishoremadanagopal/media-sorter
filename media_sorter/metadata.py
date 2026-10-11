"""Find out when (and where) a photo or video was taken.

Order of trust for the date:
  1. Data inside the file (photo EXIF / video header)
  2. A date in the file name (IMG_20261008_174512.jpg, IMG-20261008-WA0001.jpg, ...)
  3. The file's "date modified"
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from PIL import ExifTags, Image

from .mp4meta import read_video_metadata

try:  # iPhone .heic / .heif support
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:  # pragma: no cover - app still works without HEIC
    pass

PHOTO_EXTS = {
    ".jpg", ".jpeg", ".jpe", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff",
    ".gif", ".bmp", ".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".raf",
}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".3gp", ".3g2", ".avi", ".mkv", ".wmv", ".mts", ".m2ts"}
MP4_FAMILY = {".mp4", ".mov", ".m4v", ".3gp", ".3g2"}

_EXIF_DATE_TAGS = (36867, 36868)  # DateTimeOriginal, DateTimeDigitized
_TIFF_DATE_TAG = 306              # DateTime
_MIN_YEAR = 1990

_NAME_DATE = re.compile(
    r"(?<!\d)((?:19|20)\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])"
    r"(?:[ _T.-]?([01]\d|2[0-3])[-_.:]?([0-5]\d)[-_.:]?([0-5]\d))?"
)


@dataclass
class MediaInfo:
    path: Path
    kind: str            # "photo" or "video"
    taken: datetime
    date_source: str     # "photo data", "video data", "file name", "date modified"
    gps: tuple[float, float] | None


def kind_of(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in PHOTO_EXTS:
        return "photo"
    if ext in VIDEO_EXTS:
        return "video"
    return None


def _plausible(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.year < _MIN_YEAR or dt > datetime.now() + timedelta(days=2):
        return None
    return dt


def _parse_exif_date(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, bytes):
        value = value.decode("ascii", "ignore")
    text = str(value).strip().replace("\x00", "")
    attempts = (
        ("%Y:%m:%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M:%S", 19),
        ("%Y:%m:%d %H:%M", 16), ("%Y:%m:%d", 10), ("%Y-%m-%d", 10),
    )
    for fmt, length in attempts:
        try:
            return datetime.strptime(text[:length], fmt)
        except ValueError:
            continue
    return None


def _to_degrees(value) -> float | None:
    try:
        if isinstance(value, (tuple, list)):
            parts = [float(v) for v in value] + [0.0, 0.0]
            return parts[0] + parts[1] / 60.0 + parts[2] / 3600.0
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _gps_from_exif(gps_ifd) -> tuple[float, float] | None:
    if not gps_ifd:
        return None
    lat, lon = _to_degrees(gps_ifd.get(2)), _to_degrees(gps_ifd.get(4))
    if lat is None or lon is None:
        return None
    lat_ref = str(gps_ifd.get(1, "N")).upper()
    lon_ref = str(gps_ifd.get(3, "E")).upper()
    if lat_ref.startswith("S"):
        lat = -lat
    if lon_ref.startswith("W"):
        lon = -lon
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    return lat, lon


def read_photo_metadata(path: Path):
    """Return (taken | None, gps | None) from the photo's EXIF data."""
    with Image.open(path) as im:
        exif = im.getexif()
    if not exif:
        return None, None
    taken = None
    try:
        sub = exif.get_ifd(ExifTags.IFD.Exif)
    except Exception:
        sub = {}
    for tag in _EXIF_DATE_TAGS:
        taken = _plausible(_parse_exif_date(sub.get(tag)))
        if taken:
            break
    if not taken:
        taken = _plausible(_parse_exif_date(exif.get(_TIFF_DATE_TAG)))
    try:
        gps = _gps_from_exif(exif.get_ifd(ExifTags.IFD.GPSInfo))
    except Exception:
        gps = None
    return taken, gps


def date_from_name(name: str) -> datetime | None:
    for m in _NAME_DATE.finditer(name):
        y, mo, d, h, mi, s = m.groups()
        try:
            dt = datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0))
        except ValueError:
            continue
        dt = _plausible(dt)
        if dt:
            return dt
    return None


def read_info(path: Path, kind: str) -> MediaInfo:
    taken, gps, source = None, None, ""
    try:
        if kind == "photo":
            taken, gps = read_photo_metadata(path)
            source = "photo data"
        elif path.suffix.lower() in MP4_FAMILY:
            taken, gps = read_video_metadata(path)
            taken = _plausible(taken)
            source = "video data"
    except Exception:
        taken, gps = None, None

    if taken is None:
        taken = date_from_name(path.stem)
        source = "file name"
    if taken is None:
        taken = datetime.fromtimestamp(os.path.getmtime(path))
        source = "date modified"
    return MediaInfo(path=path, kind=kind, taken=taken, date_source=source, gps=gps)
