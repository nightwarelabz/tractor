"""Build one native portable bundle on the target OS; never cross-compile."""

import platform
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
system = {"Darwin": "macos"}.get(platform.system(), platform.system().lower())
machine = platform.machine().lower()
machine = {"amd64": "x86_64", "aarch64": "arm64"}.get(machine, machine)
architecture = os.environ.get("TRACTOR_NATIVE_ARCH", machine)
icon_args = []
if sys.platform == "win32":
    icon_args = ["--icon", str(root / "tractor" / "assets" / "icon.ico")]
elif sys.platform == "darwin":
    iconset = root / "build" / "tractor.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    source = root / "tractor" / "assets" / "icon-1024.png"
    for filename, size in (
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ):
        subprocess.run(
            ["sips", "-z", str(size), str(size), str(source), "--out", str(iconset / filename)],
            check=True,
            capture_output=True,
        )
    app_icon = root / "build" / "tractor.icns"
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(app_icon)], check=True
    )
    icon_args = ["--icon", str(app_icon)]
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "Tractor",
        "--onedir",
        "--collect-data",
        "tractor",
        "--collect-data",
        "langdetect",
        "--hidden-import",
        "tractor.packaging_smoke",
        "--distpath",
        str(root / "dist" / "native"),
        "--workpath",
        str(root / "build" / "native"),
        "--specpath",
        str(root / "build"),
        *icon_args,
        *(["--windowed"] if sys.platform == "darwin" else []),
        *(["--hide-console", "hide-early"] if sys.platform == "win32" else []),
        str(root / "scripts" / "native_entry.py"),
    ],
    cwd=root,
    check=True,
)
name = f"Tractor-{version}-{system}-{architecture}"
folder = root / "dist" / "native"
bundle = "Tractor.app" if sys.platform == "darwin" else "Tractor"
executable = (
    folder
    / bundle
    / (
        "Contents/MacOS/Tractor"
        if sys.platform == "darwin"
        else "Tractor.exe"
        if sys.platform == "win32"
        else "Tractor"
    )
)
subprocess.run([str(executable), "--smoke-test"], check=True, timeout=90)
releases = root / "dist" / "release"
releases.mkdir(exist_ok=True)
if sys.platform == "win32":
    shutil.make_archive(str(releases / name), "zip", root_dir=folder, base_dir=bundle)
else:
    shutil.make_archive(str(releases / name), "gztar", root_dir=folder, base_dir=bundle)
print(name)
