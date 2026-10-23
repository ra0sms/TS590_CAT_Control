"""Сборка kenwood_control в один exe-файл через PyInstaller.

Запуск (на Windows для Windows-версии, PyInstaller не умеет собирать под другую ОС):
    pip install -r requirements.txt pyinstaller
    python build.py

Результат: dist/kenwood_control-<версия>-windows.exe
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "src" / "kenwood_control.py"
ICON = ROOT / "src" / "Open-source-hardware.ico"


def read_version():
    match = re.search(r'^VERSION = "([^"]+)"', SOURCE.read_text(encoding="utf-8"), re.M)
    if not match:
        sys.exit(f"VERSION not found in {SOURCE}")
    return match.group(1)


def main():
    version = read_version()

    # В GitHub Actions тег релиза должен совпадать с версией в программе
    tag = os.environ.get("GITHUB_REF_NAME", "")
    if os.environ.get("GITHUB_REF_TYPE") == "tag" and tag != f"v{version}":
        sys.exit(f"Tag {tag} does not match VERSION {version} in {SOURCE.name}")

    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    name = f"kenwood_control-{version}-{system}"
    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", name,
        "--icon", str(ICON),
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        str(SOURCE),
    ], check=True)
    print(f"\nBuilt: dist/{name}{'.exe' if system == 'windows' else ''}")


if __name__ == "__main__":
    main()
