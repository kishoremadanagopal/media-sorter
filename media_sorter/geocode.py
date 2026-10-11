"""Offline reverse geocoding: GPS coordinates -> nearest town name.

Uses a bundled list of ~145,000 places with population >= 1000
(GeoNames, CC BY 4.0). No internet needed, nothing is sent anywhere.
"""

from __future__ import annotations

import csv
import gzip
import io
import math
import os
import threading
from dataclasses import dataclass

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cities.csv.gz")
MAX_DISTANCE_KM = 60.0  # farther than this from any town -> "Unknown Location"


@dataclass(frozen=True)
class Place:
    name: str
    region: str
    country: str
    distance_km: float


class Geocoder:
    def __init__(self, data_file: str = DATA_FILE):
        self._data_file = data_file
        self._grid: dict[tuple[int, int], list[int]] | None = None
        self._lat: list[float] = []
        self._lon: list[float] = []
        self._rows: list[tuple[str, str, str]] = []
        self._cache: dict[tuple[float, float], Place | None] = {}
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._grid is not None:
                return
            grid: dict[tuple[int, int], list[int]] = {}
            with gzip.open(self._data_file, "rb") as raw:
                reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
                next(reader, None)
                for i, (lat, lon, name, region, cc) in enumerate(reader):
                    la, lo = float(lat), float(lon)
                    self._lat.append(la)
                    self._lon.append(lo)
                    self._rows.append((name, region, cc))
                    grid.setdefault((math.floor(la), math.floor(lo)), []).append(i)
            self._grid = grid

    @staticmethod
    def _km(lat1, lon1, lat2, lon2) -> float:
        # Equirectangular approximation: accurate enough below a few hundred km.
        x = math.radians(((lon2 - lon1 + 180) % 360) - 180) * math.cos(math.radians((lat1 + lat2) / 2))
        y = math.radians(lat2 - lat1)
        return 6371.0 * math.hypot(x, y)

    def lookup(self, lat: float, lon: float) -> Place | None:
        key = (round(lat, 3), round(lon, 3))
        if key in self._cache:
            return self._cache[key]
        self._load()
        best_i, best_d = -1, float("inf")
        cy, cx = math.floor(lat), math.floor(lon)
        for ring in range(0, 3):
            for dy in range(-ring, ring + 1):
                for dx in range(-ring, ring + 1):
                    if max(abs(dy), abs(dx)) != ring:
                        continue
                    gx = ((cx + dx + 180) % 360) - 180
                    for i in self._grid.get((cy + dy, gx), ()):
                        d = self._km(lat, lon, self._lat[i], self._lon[i])
                        if d < best_d:
                            best_i, best_d = i, d
            # Once something is found, one more ring guarantees we have the nearest.
            if best_i >= 0 and best_d <= 111.0 * ring:
                break
        place = None
        if best_i >= 0 and best_d <= MAX_DISTANCE_KM:
            name, region, cc = self._rows[best_i]
            place = Place(name, region, cc, round(best_d, 1))
        self._cache[key] = place
        return place
