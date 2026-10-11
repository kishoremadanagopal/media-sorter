"""Tiny, dependency-free reader for the date and GPS location stored in
MP4 / MOV / M4V / 3GP videos (the formats phones record).

Where the information lives:
  * moov/mvhd                      -> creation time (seconds since 1904, UTC)
  * moov/udta/\xa9xyz              -> GPS written by Android and older iPhones
  * moov/meta (keys + ilst)        -> iPhone "com.apple.quicktime.location.ISO6709"
                                      and "com.apple.quicktime.creationdate"
"""

from __future__ import annotations

import re
import struct
from datetime import datetime, timedelta, timezone

_MAC_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc)
_MAX_MOOV = 64 * 1024 * 1024  # never load more than 64 MB of header data
_CONTAINERS = {b"moov", b"udta", b"meta", b"trak", b"mdia", b"minf", b"ilst"}
_ISO6709 = re.compile(r"([+-]\d+(?:\.\d*)?)([+-]\d+(?:\.\d*)?)")


def _iter_atoms(buf: bytes, start: int, end: int):
    """Yield (type, payload_start, payload_end) for atoms in buf[start:end]."""
    pos = start
    while pos + 8 <= end:
        size, kind = struct.unpack(">I4s", buf[pos:pos + 8])
        header = 8
        if size == 1:
            if pos + 16 > end:
                return
            size = struct.unpack(">Q", buf[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:
            size = end - pos
        if size < header or pos + size > end:
            return
        yield kind, pos + header, pos + size
        pos += size


def _find_moov(f) -> bytes | None:
    """Walk the top-level atoms of the file and return the moov payload."""
    f.seek(0, 2)
    file_size = f.tell()
    pos = 0
    while pos + 8 <= file_size:
        f.seek(pos)
        head = f.read(16)
        if len(head) < 8:
            return None
        size, kind = struct.unpack(">I4s", head[:8])
        header = 8
        if size == 1:
            if len(head) < 16:
                return None
            size = struct.unpack(">Q", head[8:16])[0]
            header = 16
        elif size == 0:
            size = file_size - pos
        if size < header:
            return None
        if kind == b"moov":
            length = min(size - header, _MAX_MOOV)
            f.seek(pos + header)
            return f.read(length)
        pos += size
    return None


def _parse_iso6709(text: str):
    m = _ISO6709.match(text.strip())
    if not m:
        return None
    try:
        lat, lon = float(m.group(1)), float(m.group(2))
    except ValueError:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
        return None
    return lat, lon


def _parse_apple_date(text: str):
    """'2026-10-08T17:45:12+0530' -> naive local datetime (the wall-clock time where it was filmed)."""
    text = text.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:24], fmt).replace(tzinfo=None)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return None


def _read_meta(buf: bytes, start: int, end: int, out: dict):
    """Parse a QuickTime 'meta' box with 'keys' + 'ilst'."""
    # ISO-style meta boxes start with 4 bytes of version/flags; QuickTime ones don't.
    if end - start >= 4 and buf[start:start + 4] == b"\x00\x00\x00\x00":
        start += 4
    keys: list[str] = []
    ilst = None
    for kind, s, e in _iter_atoms(buf, start, end):
        if kind == b"keys" and e - s >= 8:
            count = struct.unpack(">I", buf[s + 4:s + 8])[0]
            p = s + 8
            for _ in range(count):
                if p + 8 > e:
                    break
                ksize = struct.unpack(">I", buf[p:p + 4])[0]
                if ksize < 8:
                    break
                keys.append(buf[p + 8:p + ksize].decode("utf-8", "replace"))
                p += ksize
        elif kind == b"ilst":
            ilst = (s, e)
    if not ilst:
        return
    for kind, s, e in _iter_atoms(buf, ilst[0], ilst[1]):
        index = struct.unpack(">I", kind)[0]
        if not 1 <= index <= len(keys):
            continue
        key = keys[index - 1]
        for dkind, ds, de in _iter_atoms(buf, s, e):
            if dkind != b"data" or de - ds < 8:
                continue
            value = buf[ds + 8:de].decode("utf-8", "replace")
            if key == "com.apple.quicktime.location.ISO6709":
                out.setdefault("gps", _parse_iso6709(value))
            elif key == "com.apple.quicktime.creationdate":
                out.setdefault("local_date", _parse_apple_date(value))


def _walk(buf: bytes, start: int, end: int, out: dict):
    for kind, s, e in _iter_atoms(buf, start, end):
        if kind == b"mvhd" and e - s >= 12 and "utc_date" not in out:
            version = buf[s]
            if version == 1 and e - s >= 12:
                seconds = struct.unpack(">Q", buf[s + 4:s + 12])[0]
            else:
                seconds = struct.unpack(">I", buf[s + 4:s + 8])[0]
            if seconds:
                try:
                    out["utc_date"] = _MAC_EPOCH + timedelta(seconds=seconds)
                except OverflowError:
                    pass
        elif kind == b"\xa9xyz" and e - s > 4 and not out.get("gps"):
            length = struct.unpack(">H", buf[s:s + 2])[0]
            text = buf[s + 4:min(e, s + 4 + length)].decode("utf-8", "replace")
            out["gps"] = _parse_iso6709(text)
        elif kind == b"meta":
            _read_meta(buf, s, e, out)
        elif kind in _CONTAINERS:
            _walk(buf, s, e, out)


def read_video_metadata(path):
    """Return (taken: naive local datetime | None, gps: (lat, lon) | None)."""
    with open(path, "rb") as f:
        moov = _find_moov(f)
    if not moov:
        return None, None
    out: dict = {}
    _walk(moov, 0, len(moov), out)
    taken = out.get("local_date")
    if taken is None and out.get("utc_date") is not None:
        # mvhd is UTC; show it in this computer's local time zone.
        taken = out["utc_date"].astimezone().replace(tzinfo=None)
    return taken, out.get("gps")
