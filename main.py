"""Start Media Sorter.

    MediaSorter.exe                      open the app
    MediaSorter.exe --selftest [file]    check the bundled data loads (used by the automatic build)
"""

import sys


def selftest(out_path: str | None) -> int:
    from PIL import Image

    from media_sorter import __version__
    from media_sorter.geocode import Geocoder
    from media_sorter import metadata  # noqa: F401  (switches on HEIC support)

    try:
        place = Geocoder().lookup(15.5439, 73.7553)
        heic = ".heic" in Image.registered_extensions()
        ok = bool(place) and heic
        report = f"version={__version__} geocoder={place.name if place else 'FAILED'} heic={heic} -> {'OK' if ok else 'FAIL'}"
    except Exception as exc:  # pragma: no cover
        ok, report = False, f"FAIL: {exc!r}"
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report + "\n")
    elif sys.stdout:
        print(report)
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        sys.exit(selftest(sys.argv[i + 1] if len(sys.argv) > i + 1 else None))
    if sys.platform == "win32":
        import ctypes

        try:  # sharp text on high-DPI screens and a proper taskbar icon
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("KishoreMadanagopal.MediaSorter")
        except Exception:
            pass
    from media_sorter.ui import run

    run()
