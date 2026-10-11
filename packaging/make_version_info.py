"""Write build/version_info.txt so MediaSorter.exe shows the right details in
Windows (right-click > Properties > Details): product name, version, publisher.
The values come from media_sorter/__init__.py, so there's one place to change them.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
text = (ROOT / "media_sorter" / "__init__.py").read_text(encoding="utf-8")


def value(name: str) -> str:
    return re.search(rf'^{name}\s*=\s*"([^"]*)"', text, re.M).group(1)


version, app, author = value("__version__"), value("APP_NAME"), value("AUTHOR")
desc = value("DESCRIPTION")
parts = [int(p) for p in re.findall(r"\d+", version)][:4]
parts += [0] * (4 - len(parts))
nums = ", ".join(str(p) for p in parts)

out = ROOT / "build" / "version_info.txt"
out.parent.mkdir(exist_ok=True)
out.write_text(f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers=({nums}), prodvers=({nums}), mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', '{author}'),
      StringStruct('FileDescription', '{app}'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'MediaSorter'),
      StringStruct('LegalCopyright', '\\u00a9 {author}'),
      StringStruct('OriginalFilename', 'MediaSorter.exe'),
      StringStruct('ProductName', '{app}'),
      StringStruct('ProductVersion', '{version}'),
      StringStruct('Comments', '{desc}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding="utf-8")
print(f"Wrote {out} ({app} {version} by {author})")
