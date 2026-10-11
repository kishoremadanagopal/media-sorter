# Developing Media Sorter

## Building the installer (no Python needed on your PC)

GitHub builds `MediaSorter-Setup-<version>.exe` on its own Windows machines
(`.github/workflows/build-windows.yml`). It also runs a self-test of the built app.

- **Test build:** **Actions → Build Windows installer → Run workflow**. After about 5 minutes,
  download **MediaSorter-Setup-…** under *Artifacts* (it arrives inside a .zip).
- **Public release:** **Releases → Draft a new release → tag `v1.1.0` → Publish**.
  The installer is built and attached to the release automatically.

## Releasing a new version

1. Change `__version__` in `media_sorter/__init__.py` (for example `1.2.0`).
2. Commit the change.
3. Publish a release tagged with the same version (`v1.2.0`).

`media_sorter/__init__.py` also holds the app name, author and GitHub link shown in the About window,
the installer and the `.exe`'s Properties.

## Running from source

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

`build.bat` builds the installer locally instead (needs Python 3.12 and NSIS).

## Tests

- `tests/make_samples.py <folder>` creates sample photos and videos with and without dates and GPS
  (needs `pip install piexif`).
- `tests/ui_screenshots.py <samples> <save folder> <screenshots folder>` clicks through the wizard
  and saves a screenshot of each step.

## Code signing

Builds are unsigned. Signing is optional and switches on by itself once it's configured;
see [SIGNING.md](SIGNING.md).

## Project layout

```
main.py                         starts the app
media_sorter/ui.py              the wizard window and About box
media_sorter/engine.py          scanning, folder plan, copy/move, log
media_sorter/metadata.py        photo dates/GPS, file-name dates
media_sorter/mp4meta.py         video dates/GPS (MP4/MOV)
media_sorter/geocode.py         offline GPS → town name
media_sorter/data/              world towns list (GeoNames)
packaging/installer.nsi         the Setup.exe installer (NSIS)
packaging/make_version_info.py  puts the author in the .exe's Properties
.github/workflows/              the automatic Windows build
```

## Known limits

- Place names are the nearest town, so a photo near a big city's edge may get a suburb's name.
- Android video times are stored in UTC; the app converts them to the PC's time zone.
