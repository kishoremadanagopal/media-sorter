"""Drive the wizard automatically and save a screenshot of every step.
Run on a machine with a display (or under xvfb-run on Linux):
    python tests/ui_screenshots.py <sample folder> <save folder> <screenshot folder>
"""

import sys
from pathlib import Path

from PIL import ImageGrab

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from media_sorter.ui import App  # noqa: E402

src, dest, shots = (Path(a) for a in sys.argv[1:4])
shots.mkdir(parents=True, exist_ok=True)
app = App()
app.geometry("900x720+0+0")


def snap(name):
    app.update()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    w, h = app.winfo_width(), app.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(shots / f"{name}.png")
    print("shot", name)


steps = []


def step(delay, fn):
    steps.append((delay, fn))


step(400, lambda: snap("0_empty"))
step(100, lambda: (app.source_var.set(str(src)), app._start_scan()))
step(1200, lambda: snap("1_source"))
step(100, lambda: (app._go_next(), app.dest_var.set(str(dest)), app.name_var.set("Goa Trip")))
step(500, lambda: snap("2_destination"))
step(100, lambda: (app._go_next(),))
step(400, lambda: snap("3_options_both"))
step(100, lambda: (app.mode_var.set("date"), app._options_changed()))
step(300, lambda: snap("3b_options_date"))
step(100, lambda: (app.mode_var.set("both"), app._options_changed(), app._go_next()))
step(40, lambda: snap("4_progress"))
step(3500, lambda: snap("5_done"))


def snap_about():
    app.show_about()
    app.update()


def grab_about():
    win = app._about
    win.update()
    x, y, w, h = win.winfo_rootx(), win.winfo_rooty(), win.winfo_width(), win.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(shots / "6_about.png")
    print("shot 6_about")


step(200, snap_about)
step(800, grab_about)
step(200, lambda: app.destroy())


t = 0
for delay, fn in steps:
    t += delay
    app.after(t, fn)
app.mainloop()
