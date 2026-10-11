@echo off
REM ===================================================================
REM  OPTIONAL: build Setup.exe on your own PC instead of on GitHub.
REM  Needs Python 3.12 (python.org) and NSIS (nsis.sourceforge.io).
REM  Most people should use the GitHub build instead (see README.md).
REM ===================================================================
setlocal
cd /d "%~dp0"

where python >nul 2>nul || (echo Install Python 3.12 from https://www.python.org/downloads/ first. & pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" python -m venv .venv || goto :error
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt pyinstaller || goto :error
".venv\Scripts\python.exe" packaging\make_version_info.py || goto :error

".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed ^
    --name MediaSorter --icon assets\icon.ico --version-file build\version_info.txt ^
    --add-data "assets;assets" --add-data "media_sorter\data;media_sorter\data" ^
    --collect-all customtkinter --collect-all pillow_heif --hidden-import PIL._tkinter_finder ^
    main.py || goto :error

set NSIS="%ProgramFiles(x86)%\NSIS\makensis.exe"
if not exist %NSIS% (
    echo App built in dist\MediaSorter. Install NSIS to also make the Setup.exe.
    explorer dist & pause & exit /b 0
)
for /f %%v in ('".venv\Scripts\python.exe" -c "import media_sorter; print(media_sorter.__version__)"') do set VER=%%v
%NSIS% /DVERSION=%VER% packaging\installer.nsi || goto :error
echo Done: dist\MediaSorter-Setup-%VER%.exe
explorer dist
pause
exit /b 0

:error
echo Something went wrong. Scroll up to see the message.
pause
exit /b 1
