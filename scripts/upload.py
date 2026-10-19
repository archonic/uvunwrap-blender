# SPDX-License-Identifier: GPL-3.0-or-later
"""Uploads the built zips in dist/ to extensions.blender.org.

Usage: python scripts/upload.py [--dry-run] [DIST_DIR]

Every zip except the GitHub-only ones (see scripts/build.py) is checked like
build.py does, then posted to the site's upload API as a file of its
version: the first zip of a new version creates it, the rest add their
platforms to it. The extension must already exist on the site (the first
upload of an extension goes through the web form).

Environment:
  BLENDER_EXTENSIONS_TOKEN  an API token from your extensions.blender.org
                            account (not needed with --dry-run)
  RELEASE_NOTES             optional release notes (trimmed to 1024 chars)
  BLENDER_EXTENSIONS_URL    the site, default https://extensions.blender.org
"""

import json
import os
import pathlib
import sys
import tomllib
import urllib.error
import urllib.request
import uuid
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build  # noqa: E402

MAX_RELEASE_NOTES = 1024


def site_zips(dist):
    """The zips to upload: all but the GitHub-only platforms', checked."""
    github_only = tuple(f"-{p.replace('-', '_')}.zip" for p in build.GITHUB_ONLY)
    zips = sorted(z for z in dist.glob("*.zip") if not z.name.endswith(github_only))
    if not zips:
        raise SystemExit(f"no zips to upload in {dist}")
    ids = set()
    for z in zips:
        build.check(z, github_only=False)
        with zipfile.ZipFile(z) as f:
            manifest = tomllib.loads(f.read("blender_manifest.toml").decode())
        ids.add((manifest["id"], manifest["version"]))
    if len(ids) != 1:
        raise SystemExit(f"zips disagree on id and version: {sorted(ids)}")
    return zips, ids.pop()


def multipart(fields, files):
    """A multipart/form-data body and its content type."""
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode()
        )
    for name, path in files.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
            f'filename="{path.name}"\r\nContent-Type: application/zip\r\n\r\n'.encode()
            + path.read_bytes()
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def upload(site, token, extension_id, path, notes):
    """Posts one zip; returns (HTTP status, response text)."""
    body, content_type = multipart({"release_notes": notes} if notes else {}, {"version_file": path})
    request = urllib.request.Request(
        f"{site}/api/v1/extensions/{extension_id}/versions/upload/",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def main(argv):
    dry_run = "--dry-run" in argv
    args = [a for a in argv if a != "--dry-run"]
    dist = pathlib.Path(args[0]) if args else build.DIST
    zips, (extension_id, version) = site_zips(dist)
    site = os.environ.get("BLENDER_EXTENSIONS_URL", "https://extensions.blender.org").rstrip("/")
    notes = os.environ.get("RELEASE_NOTES", "").strip()[:MAX_RELEASE_NOTES]
    print(f"{extension_id} {version}: {len(zips)} zip(s) for {site}")
    if dry_run:
        for z in zips:
            print(f"  would upload {z.name}")
        return 0
    token = os.environ.get("BLENDER_EXTENSIONS_TOKEN", "").strip()
    if not token:
        raise SystemExit("BLENDER_EXTENSIONS_TOKEN is not set")
    for z in zips:
        status, text = upload(site, token, extension_id, z, notes)
        try:
            text = json.dumps(json.loads(text))
        except ValueError:
            pass
        print(f"  {z.name}: HTTP {status} {text[:500]}")
        if status != 201:
            print(f"stopped: {z.name} was rejected; the zips after it weren't uploaded")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
