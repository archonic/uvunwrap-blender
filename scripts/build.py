# SPDX-License-Identifier: GPL-3.0-or-later
"""Builds the extension zips into dist/ and checks them.

Usage: python scripts/build.py   (needs Python 3.11+ and `blender` on PATH)

1. Downloads the uvunwrap wheels from PyPI into extension/wheels: the ones
   the manifest lists, plus the Linux ARM64 wheel (its name derived from the
   Linux x64 one, so the version lives in the manifest only).
2. Builds one zip per manifest platform: these are the ones uploaded to
   extensions.blender.org, which doesn't accept linux-arm64.
3. Builds the Linux ARM64 zip from a copy of the extension whose manifest
   names only that platform; it's offered on GitHub releases only.
4. Checks every zip: a site zip's manifest may only name platforms the site
   accepts, and each zip holds exactly its own wheels.
"""

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXTENSION = ROOT / "extension"
WHEELS = EXTENSION / "wheels"
DIST = ROOT / "dist"
MANIFEST = EXTENSION / "blender_manifest.toml"

# What extensions.blender.org accepts in `platforms`.
SITE_PLATFORMS = {"windows-x64", "windows-arm64", "macos-x64", "macos-arm64", "linux-x64"}
# Built for GitHub releases only, from the Linux x64 wheel's name.
GITHUB_ONLY = {"linux-arm64": ("x86_64", "aarch64")}


def wheel_names():
    """The manifest's wheels and the GitHub-only platforms' wheels."""
    listed = [w.removeprefix("./wheels/") for w in tomllib.loads(MANIFEST.read_text())["wheels"]]
    linux_x64 = next(w for w in listed if "x86_64" in w and "linux" in w)
    extra = {p: linux_x64.replace(a, b) for p, (a, b) in GITHUB_ONLY.items()}
    return listed, extra


def fetch(names):
    WHEELS.mkdir(exist_ok=True)
    for name in names:
        if (WHEELS / name).exists():
            continue
        # name: uvunwrap-<version>-cp311-abi3-<platform tags joined by ".">
        package, version, python, abi, platforms = name[: -len(".whl")].split("-")
        args = [sys.executable, "-m", "pip", "download", f"{package}=={version}", "--no-deps",
                "--only-binary=:all:", "--python-version", python[2:], "--abi", abi,
                "-d", str(WHEELS), "-q"]
        for platform in platforms.split("."):
            args += ["--platform", platform]
        subprocess.run(args, check=True)
        if not (WHEELS / name).exists():
            sys.exit(f"pip did not download {name}")


def blender_build(source, *, split):
    args = ["blender", "--command", "extension", "build", "--source-dir", str(source),
            "--output-dir", str(DIST)]
    subprocess.run(args + (["--split-platforms"] if split else []), check=True)


def build_github_only(extra):
    """One zip per GitHub-only platform, from a copy of the extension whose
    manifest names just that platform and its wheel."""
    version = tomllib.loads(MANIFEST.read_text())["version"]
    for platform, wheel in extra.items():
        with tempfile.TemporaryDirectory() as tmp:
            src = pathlib.Path(tmp) / "extension"
            shutil.copytree(EXTENSION, src, ignore=shutil.ignore_patterns("wheels", "__pycache__"))
            (src / "wheels").mkdir()
            shutil.copy2(WHEELS / wheel, src / "wheels" / wheel)
            text = (src / "blender_manifest.toml").read_text()
            text = re.sub(r"^platforms = \[.*?\]", f'platforms = ["{platform}"]', text, flags=re.M | re.S)
            text = re.sub(r"^wheels = \[.*?\]", f'wheels = ["./wheels/{wheel}"]', text, flags=re.M | re.S)
            (src / "blender_manifest.toml").write_text(text)
            blender_build(src, split=False)
            built = DIST / f"uvunwrap-{version}.zip"
            built.rename(DIST / f"uvunwrap-{version}-{platform.replace('-', '_')}.zip")


def check(zip_path, github_only):
    """Raises if the zip's manifest or wheels are wrong."""
    with zipfile.ZipFile(zip_path) as z:
        manifest = tomllib.loads(z.read("blender_manifest.toml").decode())
        wheels = {n.removeprefix("wheels/") for n in z.namelist() if n.endswith(".whl")}
    platforms = set(manifest["platforms"])
    expected = manifest.get("build", {}).get("generated", {}).get("wheels", manifest["wheels"])
    expected = {w.removeprefix("./wheels/") for w in expected}
    if not github_only and not platforms <= SITE_PLATFORMS:
        raise SystemExit(f"{zip_path.name}: platforms the site rejects: {sorted(platforms - SITE_PLATFORMS)}")
    if wheels != expected:
        raise SystemExit(f"{zip_path.name}: wheels {sorted(wheels)}, expected {sorted(expected)}")
    return f"{zip_path.name}: platforms {sorted(platforms)}, {len(wheels)} wheel"


def main():
    listed, extra = wheel_names()
    fetch(listed + list(extra.values()))
    shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir()
    # Split builds take only the manifest's wheels; keep the others out.
    with tempfile.TemporaryDirectory() as tmp:
        parked = [WHEELS / w for w in extra.values()]
        for w in parked:
            shutil.move(w, pathlib.Path(tmp) / w.name)
        try:
            subprocess.run(["blender", "--command", "extension", "validate", str(EXTENSION)], check=True)
            blender_build(EXTENSION, split=True)
        finally:
            for w in parked:
                shutil.move(pathlib.Path(tmp) / w.name, w)
    build_github_only(extra)
    github_only = {f"-{p.replace('-', '_')}.zip" for p in GITHUB_ONLY}
    for z in sorted(DIST.glob("*.zip")):
        print(check(z, any(z.name.endswith(s) for s in github_only)))


if __name__ == "__main__":
    main()
