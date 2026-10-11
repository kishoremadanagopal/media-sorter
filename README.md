# Media Sorter

Sort photos and videos into folders **by day, month or year**, **by location**, or **both**.
Made by **Kishore Madanagopal** · https://github.com/kishoremadanagopal

---

## For users: installing

1. Download **`MediaSorter-Setup-1.1.0.exe`**.
2. Double-click it → **Next** → **Install** → **Finish**.

That's all. No Python or other software is needed, and Windows won't ask for admin permission.
Media Sorter appears in the Start menu (and on the desktop if you ticked the box).
To remove it: **Settings → Apps → Media Sorter → Uninstall**.

If Windows shows "Windows protected your PC", click **More info → Run anyway**.
(This goes away once the app is signed and more people have installed it. See `SIGNING.md`.)

---

## For you (the developer): getting the Setup.exe — no Python, no command window

GitHub builds the installer for you on its own Windows computers.

**One-time setup (in your web browser):**
1. Sign in at **github.com** → **New repository** → name it `media-sorter` → **Create repository**.
   (Public is free with unlimited builds. Private works too, with a monthly free allowance.)
2. On the new repository page, click **uploading an existing file**.
3. Open the unzipped `MediaSorter` folder on your PC, select **everything inside it**
   (including the `.github` folder) and drag it into the browser window → **Commit changes**.

**Each time you want a Setup.exe:**
1. Open your repository → **Actions** tab → **Build Windows installer** → **Run workflow**.
2. Wait about 5 minutes for the green tick, open the run, and download **MediaSorter-Setup-…** under *Artifacts*.
   (GitHub delivers it inside a .zip; the Setup.exe is inside.)

**To publish a version for others:** repository → **Releases** → **Draft a new release** → tag `v1.1.0` →
**Publish**. The installer is built and attached to the release page automatically, ready to share.

**New version:** change `__version__` in `media_sorter/__init__.py`, upload the changed files, and run again.

**Signing with your name:** follow `SIGNING.md` once (Microsoft Artifact Signing, $9.99/month).
After that, every build is signed automatically: the app, its uninstaller and the Setup.exe.

**License:** MIT (see `LICENSE`). Open source, free for anyone to use and change.

---

## How it works

| What | Where it looks, in order |
|---|---|
| **Date** | 1. Photo data (EXIF) or video data inside the file → 2. A date in the file name (`IMG-20261009-WA0001.jpg`) → 3. The file's "Date modified" |
| **Place** | GPS inside the file → nearest town, looked up **offline**. Nothing is uploaded. |

Files without GPS go into **Unknown Location** (WhatsApp and many apps remove GPS).

**Supported:** JPG, PNG, HEIC/HEIF, WEBP, TIFF, GIF, BMP, common RAW · MP4, MOV, M4V, 3GP (date + GPS), AVI, MKV, WMV, MTS (date from name / modified).

**Safety:** Copy mode never touches originals · name clashes become `name (1).jpg` · identical files are skipped,
so running twice makes no duplicates · every run writes a CSV log in the new folder · Cancel any time.

## Project files

```
main.py                         starts the app
media_sorter/ui.py              the wizard window and About box
media_sorter/engine.py          scanning, folder plan, copy/move, log
media_sorter/metadata.py        photo dates/GPS, file-name dates
media_sorter/mp4meta.py         video dates/GPS (MP4/MOV)
media_sorter/geocode.py         offline GPS → town name
media_sorter/__init__.py        version, app name, your name and GitHub link
packaging/installer.nsi         the Setup.exe installer
packaging/make_version_info.py  puts your name in the .exe's Properties
.github/workflows/              the automatic Windows build
build.bat                       optional: build on your own PC instead of GitHub
tests/                          sample-file generator and UI screenshot test
```

## Known limits / Version 2 ideas

- Place names are the nearest town, so photos near a big city's edge may get a suburb's name.
- Planned for V2: documents (PDF, Word, Excel…) sorted by type, plus UI changes.

## Credits

Town data: [GeoNames](https://www.geonames.org/) (CC BY 4.0), via the `reverse_geocoder` project.
UI: [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter). Images: Pillow, pillow-heif.
