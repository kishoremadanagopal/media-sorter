"""Create a folder of sample photos and videos for testing Media Sorter.

Run:  python tests/make_samples.py <output folder>
Needs: pillow, pillow-heif, piexif  (pip install piexif)
"""

from __future__ import annotations

import os
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import piexif
from PIL import Image

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC = True
except Exception:
    HEIC = False


def _dms(value: float):
    value = abs(value)
    d = int(value)
    m = int((value - d) * 60)
    s = round(((value - d) * 60 - m) * 60 * 100)
    return ((d, 1), (m, 1), (s, 100))


def exif_bytes(taken: str | None, gps: tuple[float, float] | None) -> bytes:
    data = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
    if taken:
        data["0th"][piexif.ImageIFD.DateTime] = taken
        data["Exif"][piexif.ExifIFD.DateTimeOriginal] = taken
    if gps:
        lat, lon = gps
        data["GPS"] = {
            piexif.GPSIFD.GPSLatitudeRef: "N" if lat >= 0 else "S",
            piexif.GPSIFD.GPSLatitude: _dms(lat),
            piexif.GPSIFD.GPSLongitudeRef: "E" if lon >= 0 else "W",
            piexif.GPSIFD.GPSLongitude: _dms(lon),
        }
    return piexif.dump(data)


def photo(path: Path, taken=None, gps=None, color=(90, 140, 200), fmt=None):
    img = Image.new("RGB", (64, 48), color)
    kwargs = {}
    if taken or gps:
        kwargs["exif"] = exif_bytes(taken, gps)
    img.save(path, format=fmt, **kwargs)


# --- minimal MP4/MOV writer -------------------------------------------------
def atom(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def mvhd(utc: datetime | None) -> bytes:
    secs = int((utc - datetime(1904, 1, 1, tzinfo=timezone.utc)).total_seconds()) if utc else 0
    return atom(b"mvhd", b"\x00\x00\x00\x00" + struct.pack(">II", secs, secs) + b"\x00" * 88)


def xyz(gps) -> bytes:
    text = f"{gps[0]:+08.4f}{gps[1]:+09.4f}/".encode()
    return atom(b"\xa9xyz", struct.pack(">HH", len(text), 0x15c7) + text)


def apple_meta(location: str | None, created: str | None) -> bytes:
    keys, items = [], []
    for key, value in (("com.apple.quicktime.location.ISO6709", location),
                       ("com.apple.quicktime.creationdate", created)):
        if value:
            keys.append(key)
            data = atom(b"data", struct.pack(">II", 1, 0) + value.encode())
            items.append(atom(struct.pack(">I", len(keys)), data))
    keys_box = atom(b"keys", struct.pack(">II", 0, len(keys)) +
                    b"".join(struct.pack(">I4s", 8 + len(k), b"mdta") + k.encode() for k in keys))
    hdlr = atom(b"hdlr", b"\x00" * 8 + b"mdta" + b"\x00" * 13)
    return atom(b"meta", hdlr + keys_box + atom(b"ilst", b"".join(items)))


def video(path: Path, utc=None, gps=None, apple=None, moov_last=False):
    children = mvhd(utc)
    if gps:
        children += atom(b"udta", xyz(gps))
    if apple:
        children += apple_meta(*apple)
    ftyp = atom(b"ftyp", b"qt  " if path.suffix.lower() == ".mov" else b"isom" + b"\x00\x00\x02\x00isom")
    mdat = atom(b"mdat", os.urandom(2048))
    moov = atom(b"moov", children)
    path.write_bytes(ftyp + (mdat + moov if moov_last else moov + mdat))


def set_mtime(path: Path, when: datetime):
    ts = time.mktime(when.timetuple())
    os.utime(path, (ts, ts))


GOA_PANAJI = (15.4989, 73.8278)
GOA_CALANGUTE = (15.5439, 73.7553)
GOA_ANJUNA = (15.5735, 73.7406)
GOA_BAGA = (15.5560, 73.7517)
PARIS = (48.8584, 2.2945)
SEA = (10.0, 65.0)  # middle of the Arabian Sea


def main(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    sub = out / "Camera"
    sub.mkdir(exist_ok=True)

    photo(out / "IMG_0412.jpg", "2026:10:08 10:15:32", GOA_PANAJI)
    photo(out / "IMG_0413.jpg", "2026:10:08 17:45:12", GOA_CALANGUTE, (220, 160, 90))
    photo(out / "IMG_0414.JPG", "2026:10:09 09:02:14", GOA_ANJUNA)
    photo(sub / "IMG_0415.jpeg", "2026:10:10 12:11:45", GOA_BAGA)
    photo(sub / "DSC_1001.jpg", "2026:10:09 18:30:20", GOA_CALANGUTE)
    photo(out / "paris.jpg", "2025:06:14 11:00:00", PARIS)
    photo(out / "on_the_boat.jpg", "2026:10:10 16:20:00", SEA)
    photo(out / "date_only_no_gps.jpg", "2026:10:09 20:00:00", None)
    # Name collision: same file name, different picture, different day
    (sub / "dup").mkdir(exist_ok=True)
    photo(sub / "dup" / "IMG_0412.jpg", "2026:10:08 10:16:00", GOA_PANAJI, (10, 200, 10))
    # Exact duplicate of IMG_0413.jpg in another folder
    (sub / "IMG_0413_copy").mkdir(exist_ok=True)
    (sub / "IMG_0413_copy" / "IMG_0413.jpg").write_bytes((out / "IMG_0413.jpg").read_bytes())
    # WhatsApp image: no EXIF, date in the file name
    photo(out / "IMG-20261009-WA0001.jpg")
    # Screenshot PNG: no EXIF, date in file name
    photo(out / "Screenshot_20261010-121145.png", fmt="PNG")
    # No EXIF, no date in name -> falls back to date modified
    photo(out / "random_picture.jpg")
    set_mtime(out / "random_picture.jpg", datetime(2026, 9, 30, 8, 0, 0))
    if HEIC:
        img = Image.new("RGB", (64, 48), (180, 80, 160))
        img.save(out / "IMG_0500.HEIC", exif=exif_bytes("2026:10:10 13:05:00", GOA_BAGA))

    # Videos
    video(out / "VID_20261008_183000.mp4", datetime(2026, 10, 8, 13, 0, 0, tzinfo=timezone.utc), GOA_CALANGUTE)
    video(sub / "IMG_0600.MOV", datetime(2026, 10, 9, 4, 0, 0, tzinfo=timezone.utc), None,
          ("+15.5735+073.7406+010.000/", "2026-10-09T09:30:00+0530"), moov_last=True)
    video(out / "clip_no_data.mp4")
    set_mtime(out / "clip_no_data.mp4", datetime(2026, 10, 10, 19, 0, 0))

    # Not media -> skipped
    (out / "notes.txt").write_text("not a photo")
    (out / "desktop.ini").write_text("[.ShellClassInfo]")
    print(f"Samples written to {out} (HEIC: {HEIC})")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "sample_media"))
