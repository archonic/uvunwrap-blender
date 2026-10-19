# uvunwrap-blender: agent instructions

A Blender extension (add-on, Blender 4.2+) that unwraps meshes with the
`uvunwrap` Python package (PyPI; Rust crate and bindings in
github.com/archonic/uvunwrap). The unwrapping itself lives there; this repo
only reads meshes, writes UV maps and provides the UI.

Plans, status and history go in `TODO.md` (gitignored, local), never in
this file or the README.

## Invariants

- Never modify the user's mesh: only write UV maps.
- One UV per face corner: a polygon's triangles go in as one polygon
  (`loop_triangles` + `polygon_index`). Marked seams split corners
  (`mesh_io.corners`); a seam whose ends stay connected is a slit, as in
  Blender's unwrap.
- Large meshes: numpy only (`foreach_get`/`foreach_set`), no per-element
  Python loops.
- The interactive path (`invoke`) runs `uvunwrap.start` as a modal job with
  progress and `Esc`; `execute` (scripts, redo panel, background mode) runs
  `uvunwrap.generate`.

## Layout

- `extension/`: the extension (the zip's content). `blender_manifest.toml`
  (id `uvunwrap`, the platforms extensions.blender.org accepts, the wheel
  per platform), `__init__.py`
  (settings shared by the scene and the operator, operator, sidebar panel,
  UV menu entry), `mesh_io.py` (mesh → `uvunwrap.Mesh`, results → UV map;
  world space, edit-mode selection as `ignored_faces`, page fit to a square
  image, extra pages as UDIM tiles).
- `scripts/build.py`: the one build, used by CI and releases. Downloads the
  wheels (`extension/wheels/`, gitignored), builds the site zips (split by
  the manifest's platforms) and the GitHub-only `linux-arm64` zip (from a
  copy whose manifest names only that platform; extensions.blender.org
  rejects any zip whose manifest lists it), then checks every zip's
  platforms and wheels.
- `docs/`: the listing description (`listing.md`, pasted into
  extensions.blender.org) and screenshots, regenerated with
  `scripts/screenshots.py` (needs the UI; see its docstring).
- `tests/test_extension.py`: run inside Blender, from this checkout
  (`-- --wheels DIR`) or against the installed extension.
- `.github/workflows/ci.yml`: builds the zips with Blender 5.2, installs the
  Linux x64 one and runs the tests on Blender 4.2 LTS and 5.2.
  `release.yml`: on a published release tagged `v<manifest version>`,
  builds the zips and attaches them.

## Commands

- `python scripts/build.py` (Python 3.11+, `blender` on PATH): the zips in
  `dist/`, checked.
- Tests from the checkout: `blender -b --factory-startup --python-exit-code 1
  --python tests/test_extension.py -- --wheels DIR`, `DIR` holding the
  `uvunwrap` package (`pip install --target DIR uvunwrap`).
- Tests against the built zip, isolated from your Blender setup: set
  `BLENDER_USER_RESOURCES` to an empty directory, `blender --command
  extension install-file -r user_default -e dist/<zip>`, then run the tests
  without `--wheels`.

## Conventions

- Commits are authored by Joshua Flark <joshuajmark@gmail.com>, with no
  `Co-Authored-By` or other AI attribution trailers. Small commits, each
  passing the tests on its own.
- New uvunwrap versions: update the wheel names in the manifest (version
  and tags); `scripts/build.py` derives the linux-arm64 wheel's name.
- Never drop a platform without the maintainer's approval; a platform the
  site rejects goes in `GITHUB_ONLY` in `scripts/build.py`.
- Releases: bump `version` in the manifest, then publish a GitHub release
  tagged `v<version>`; upload its non-`linux_arm64` zips to the site.
- Every source file starts with `# SPDX-License-Identifier: GPL-3.0-or-later`.
