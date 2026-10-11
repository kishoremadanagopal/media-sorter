; =====================================================================
;  Media Sorter - Windows installer (NSIS 3)
;  - No admin rights needed: installs for the current user only
;  - Start menu shortcut, optional desktop shortcut, launch at the end
;  - Shows up in Settings > Apps with an Uninstall button
;
;  Simple build:   makensis /DVERSION=1.0.0 packaging\installer.nsi
;
;  Signed build (so the uninstaller can be signed too), three steps:
;   1. makensis /DVERSION=1.0.0 /DUNINSTALLER_ONLY packaging\installer.nsi
;      then run dist\make-uninstaller.exe  -> creates dist\uninstaller\Uninstall.exe
;   2. sign dist\uninstaller\Uninstall.exe
;   3. makensis /DVERSION=1.0.0 /DPREBUILT_UNINSTALLER packaging\installer.nsi, then sign the Setup.exe
; =====================================================================

Unicode true
SetCompressor /SOLID lzma

!ifndef VERSION
  !define VERSION "1.0.0"
!endif
!ifndef SRCDIR
  !define SRCDIR "..\dist\MediaSorter"
!endif
!ifndef OUTDIR
  !define OUTDIR "..\dist"
!endif

!define APPNAME     "Media Sorter"
!define EXENAME     "MediaSorter.exe"
!define PUBLISHER   "Kishore Madanagopal"
!define WEBSITE     "https://github.com/kishoremadanagopal"
!define UNINSTKEY   "Software\Microsoft\Windows\CurrentVersion\Uninstall\MediaSorter"

Name "${APPNAME}"
!ifdef PREBUILT_UNINSTALLER
  !pragma warning disable 6020   ; expected: the uninstaller is built separately and signed
!endif
!ifdef UNINSTALLER_ONLY
  ; Helper that only writes Uninstall.exe next to itself, so it can be signed separately
  OutFile "${OUTDIR}\make-uninstaller.exe"
  SilentInstall silent
!else
  OutFile "${OUTDIR}\MediaSorter-Setup-${VERSION}.exe"
!endif
InstallDir "$LOCALAPPDATA\Programs\${APPNAME}"
InstallDirRegKey HKCU "${UNINSTKEY}" "InstallLocation"
RequestExecutionLevel user
BrandingText "${APPNAME} ${VERSION}  ·  ${PUBLISHER}"
ShowInstDetails nevershow
ShowUninstDetails nevershow

; ---- details shown in the Setup.exe file's Properties > Details
VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName"     "${APPNAME}"
VIAddVersionKey "CompanyName"     "${PUBLISHER}"
VIAddVersionKey "FileDescription" "${APPNAME} Setup"
VIAddVersionKey "FileVersion"     "${VERSION}"
VIAddVersionKey "ProductVersion"  "${VERSION}"
VIAddVersionKey "LegalCopyright"  "© ${PUBLISHER}"

; ---- look
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!define MUI_ICON   "..\assets\icon.ico"
!define MUI_UNICON "..\assets\icon.ico"
!define MUI_WELCOMEFINISHPAGE_BITMAP   "installer-side.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "installer-side.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "installer-header.bmp"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "Welcome to ${APPNAME}"
!define MUI_WELCOMEPAGE_TEXT "This will install ${APPNAME} ${VERSION} on your computer.$\r$\n$\r$\n${APPNAME} sorts your photos and videos into folders by date, by place, or both.$\r$\n$\r$\nNo extra software is needed. Click Next to continue."

!define MUI_FINISHPAGE_TITLE "${APPNAME} is ready"
!define MUI_FINISHPAGE_TEXT "${APPNAME} has been installed. You can find it in the Start menu."
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXENAME}"
!define MUI_FINISHPAGE_RUN_TEXT "Open ${APPNAME} now"
; The 'readme' checkbox is used for an optional desktop shortcut
!define MUI_FINISHPAGE_SHOWREADME ""
!define MUI_FINISHPAGE_SHOWREADME_TEXT "Add a shortcut to my desktop"
!define MUI_FINISHPAGE_SHOWREADME_FUNCTION CreateDesktopShortcut
!define MUI_FINISHPAGE_LINK "Made by ${PUBLISHER}"
!define MUI_FINISHPAGE_LINK_LOCATION "${WEBSITE}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; ---- install
Section "Install"
  SetOutPath "$INSTDIR"
  ; Remove files from an older version first so nothing stale is left behind
  RMDir /r "$INSTDIR\_internal"
!ifndef UNINSTALLER_ONLY
  File /r "${SRCDIR}\*.*"
!endif

!ifdef PREBUILT_UNINSTALLER
  File "/oname=Uninstall.exe" "${OUTDIR}\uninstaller\Uninstall.exe"   ; already signed
!else
  WriteUninstaller "$INSTDIR\Uninstall.exe"
!endif
  CreateShortCut "$SMPROGRAMS\${APPNAME}.lnk" "$INSTDIR\${EXENAME}" "" "$INSTDIR\${EXENAME}" 0 \
                 SW_SHOWNORMAL "" "Sort photos and videos by date and place"

  ; Register in Settings > Apps (for this user)
  WriteRegStr   HKCU "${UNINSTKEY}" "DisplayName"          "${APPNAME}"
  WriteRegStr   HKCU "${UNINSTKEY}" "DisplayVersion"       "${VERSION}"
  WriteRegStr   HKCU "${UNINSTKEY}" "Publisher"            "${PUBLISHER}"
  WriteRegStr   HKCU "${UNINSTKEY}" "DisplayIcon"          "$INSTDIR\${EXENAME}"
  WriteRegStr   HKCU "${UNINSTKEY}" "InstallLocation"      "$INSTDIR"
  WriteRegStr   HKCU "${UNINSTKEY}" "UninstallString"      '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "${UNINSTKEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegStr   HKCU "${UNINSTKEY}" "URLInfoAbout"         "${WEBSITE}"
  WriteRegStr   HKCU "${UNINSTKEY}" "HelpLink"             "${WEBSITE}"
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINSTKEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNINSTKEY}" "EstimatedSize" "$0"
SectionEnd

!ifdef UNINSTALLER_ONLY
Function .onInit
  CreateDirectory "$EXEDIR\uninstaller"
  WriteUninstaller "$EXEDIR\uninstaller\Uninstall.exe"
  Quit
FunctionEnd
!endif

Function CreateDesktopShortcut
  CreateShortCut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\${EXENAME}" "" "$INSTDIR\${EXENAME}" 0
FunctionEnd

; ---- uninstall (your sorted photos are never touched)
Section "Uninstall"
  Delete "$SMPROGRAMS\${APPNAME}.lnk"
  Delete "$DESKTOP\${APPNAME}.lnk"
  RMDir /r "$INSTDIR\_internal"
  Delete "$INSTDIR\${EXENAME}"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${UNINSTKEY}"
SectionEnd
