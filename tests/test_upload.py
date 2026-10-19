# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of scripts/upload.py against a stand-in API server on localhost
(never the real site): python -m unittest tests/test_upload.py"""

import contextlib
import http.server
import io
import os
import pathlib
import sys
import tempfile
import threading
import unittest
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import upload  # noqa: E402

WHEEL = "uvunwrap-0.2.0-cp311-abi3-{}.whl"


def fake_zip(dist, platform, tag, *, site=True, version="9.9.9"):
    """A zip like build.py's: the site platforms in the manifest, plus the
    generated section naming this zip's platform and wheel."""
    wheel = WHEEL.format(tag)
    platforms = '["linux-x64", "windows-x64"]' if site else f'["{platform}"]'
    manifest = (
        f'schema_version = "1.0.0"\nid = "uvunwrap"\nversion = "{version}"\n'
        f"platforms = {platforms}\n"
        f'wheels = ["./wheels/{wheel}"]\n'
    )
    if site:
        manifest += f'\n[build.generated]\nplatforms = ["{platform}"]\nwheels = ["./wheels/{wheel}"]\n'
    path = dist / f"uvunwrap-{version}-{platform.replace('-', '_')}.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("blender_manifest.toml", manifest)
        z.writestr(f"wheels/{wheel}", b"wheel bytes for " + platform.encode())
    return path


class FakeSite:
    """Records each POST and answers with the next queued status."""

    def __init__(self, statuses):
        self.requests, self.statuses = [], list(statuses)
        site = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                site.requests.append((self.path, dict(self.headers), body))
                status = site.statuses.pop(0)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                message = "ok" if status == 201 else "Manifest value error"
                self.wfile.write(f'{{"message": "{message}"}}'.encode())

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class UploadTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dist = pathlib.Path(self.tmp.name)
        fake_zip(self.dist, "windows-x64", "win_amd64")
        fake_zip(self.dist, "linux-x64", "manylinux_2_17_x86_64")
        fake_zip(self.dist, "linux-arm64", "manylinux_2_17_aarch64", site=False)
        self.env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.env)
        self.tmp.cleanup()

    def run_upload(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = upload.main([*args, str(self.dist)])
        return code, out.getvalue()

    def test_uploads_the_site_zips_with_the_token(self):
        site = FakeSite([201, 201])
        self.addCleanup(site.close)
        os.environ.update(BLENDER_EXTENSIONS_URL=site.url, BLENDER_EXTENSIONS_TOKEN="secret",
                          RELEASE_NOTES="x" * 2000)
        code, out = self.run_upload()
        self.assertEqual(code, 0, out)
        self.assertEqual(len(site.requests), 2)  # never the linux_arm64 zip
        for (path, headers, body), name in zip(site.requests, ["linux_x64", "windows_x64"]):
            self.assertEqual(path, "/api/v1/extensions/uvunwrap/versions/upload/")
            self.assertEqual(headers["Authorization"], "Bearer secret")
            self.assertIn("multipart/form-data; boundary=", headers["Content-Type"])
            self.assertIn(f'name="version_file"; filename="uvunwrap-9.9.9-{name}.zip"'.encode(), body)
            self.assertIn(b'name="release_notes"\r\n\r\n' + b"x" * 1024 + b"\r\n", body)
            zip_bytes = (self.dist / f"uvunwrap-9.9.9-{name}.zip").read_bytes()
            self.assertIn(zip_bytes, body)

    def test_stops_at_the_first_rejected_zip(self):
        site = FakeSite([400])
        self.addCleanup(site.close)
        os.environ.update(BLENDER_EXTENSIONS_URL=site.url, BLENDER_EXTENSIONS_TOKEN="secret")
        code, out = self.run_upload()
        self.assertEqual(code, 1)
        self.assertEqual(len(site.requests), 1)
        self.assertIn("HTTP 400", out)
        self.assertIn("Manifest value error", out)

    def test_dry_run_needs_no_token_or_network(self):
        os.environ.pop("BLENDER_EXTENSIONS_TOKEN", None)
        os.environ["BLENDER_EXTENSIONS_URL"] = "http://127.0.0.1:9"  # nothing listens here
        code, out = self.run_upload("--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("would upload uvunwrap-9.9.9-linux_x64.zip", out)
        self.assertNotIn("linux_arm64", out)

    def test_refuses_without_a_token(self):
        os.environ.pop("BLENDER_EXTENSIONS_TOKEN", None)
        with self.assertRaises(SystemExit) as e:
            self.run_upload()
        self.assertIn("BLENDER_EXTENSIONS_TOKEN", str(e.exception))

    def test_refuses_zips_the_site_would_reject(self):
        bad = fake_zip(self.dist, "windows-x64", "win_amd64")
        text = zipfile.ZipFile(bad).read("blender_manifest.toml").decode()
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("blender_manifest.toml", text.replace('"linux-x64", ', '"linux-arm64", '))
            z.writestr(f"wheels/{WHEEL.format('win_amd64')}", b"wheel")
        with self.assertRaises(SystemExit) as e:
            self.run_upload("--dry-run")
        self.assertIn("linux-arm64", str(e.exception))


if __name__ == "__main__":
    unittest.main()
