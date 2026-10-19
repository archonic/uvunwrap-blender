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
  (id `uvunwrap`, platforms, the wheel per platform), `__init__.py`
  (settings shared by the scene and the operator, operator, sidebar panel,
  UV menu entry), `mesh_io.py` (mesh → `uvunwrap.Mesh`, results → UV map;
  world space, edit-mode selection as `ignored_faces`, page fit to a square
  image, extra pages as UDIM tiles).
- `extension/wheels/`: downloaded by `scripts/fetch_wheels.py` from the
  names in the manifest (gitignored).
- `docs/`: the listing description (`listing.md`, pasted into
  extensions.blender.org) and screenshots, regenerated with
  `scripts/screenshots.py` (needs the UI; see its docstring).
- `tests/test_extension.py`: run inside Blender, from this checkout
  (`-- --wheels DIR`) or against the installed extension.
- `.github/workflows/ci.yml`: builds the zips with Blender 5.2, installs the
  Linux one and runs the tests on Blender 4.2 LTS and 5.2.

## Commands

- `python scripts/fetch_wheels.py`
- `blender --command extension validate extension`
- `mkdir -p dist && blender --command extension build --source-dir extension
  --output-dir dist --split-platforms` (the output directory must exist).
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
  and tags) and run `scripts/fetch_wheels.py`.
- Every source file starts with `# SPDX-License-Identifier: GPL-3.0-or-later`.
