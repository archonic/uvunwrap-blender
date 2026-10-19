# SPDX-License-Identifier: GPL-3.0-or-later
"""Downloads the uvunwrap wheels the manifest lists into extension/wheels.

Usage: python scripts/fetch_wheels.py
The wheel file names, and so the version, are read from the manifest.
"""

import pathlib
import re
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parent.parent
manifest = (root / "extension" / "blender_manifest.toml").read_text()
wheels = re.findall(r'"\./wheels/([^"]+\.whl)"', manifest)
dest = root / "extension" / "wheels"
dest.mkdir(exist_ok=True)

for name in wheels:
    if (dest / name).exists():
        continue
    # name: uvunwrap-<version>-cp311-abi3-<platform tags joined by ".">
    package, version, python, abi, platforms = name[: -len(".whl")].split("-")
    args = [sys.executable, "-m", "pip", "download", f"{package}=={version}", "--no-deps",
            "--only-binary=:all:", "--python-version", python[2:], "--abi", abi, "-d", str(dest)]
    for platform in platforms.split("."):
        args += ["--platform", platform]
    subprocess.run(args, check=True)
    if not (dest / name).exists():
        sys.exit(f"pip did not download {name}")
print("\n".join(sorted(p.name for p in dest.glob("*.whl"))))
