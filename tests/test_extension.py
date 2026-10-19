# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests of the extension, run inside Blender:

    blender -b --factory-startup --python-exit-code 1 \\
        --python tests/test_extension.py [-- --wheels DIR]

With `--wheels DIR` (a directory with the uvunwrap package, e.g. an unpacked
wheel), the extension is loaded from this checkout; without it, it must be
installed (CI installs the built extension).
"""

import importlib
import pathlib
import sys
import traceback

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
INSTALLED = "--wheels" not in argv
if not INSTALLED:
    sys.path.insert(0, argv[argv.index("--wheels") + 1])
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    importlib.import_module("extension").register()


def fresh():
    """An empty scene. Factory settings also reset the preferences, which
    disables an installed extension, so it is enabled again."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if INSTALLED:
        bpy.ops.preferences.addon_enable(module="bl_ext.user_default.uvunwrap")


def uv_triangles(obj, uv_map="UVMap_Lightmap"):
    """Per triangle of `obj`: its polygon and its corners' UVs (n, 3, 2)."""
    me = obj.data
    me.calc_loop_triangles()
    nt, nl = len(me.loop_triangles), len(me.loops)
    loops = np.empty(nt * 3, np.int32)
    me.loop_triangles.foreach_get("loops", loops)
    poly = np.empty(nt, np.int32)
    me.loop_triangles.foreach_get("polygon_index", poly)
    uv = np.empty(nl * 2, np.float32)
    me.uv_layers[uv_map].data.foreach_get("uv", uv)
    return poly, uv.reshape(-1, 2)[loops].reshape(-1, 3, 2)


def assert_valid(tris_by_object, size=2048):
    """UVs inside their UDIM tile and no two triangles overlapping: texel
    centers on a `size` grid per tile are covered by at most one triangle
    (strictly inside, so shared edges don't count)."""
    owner = {}
    for k, tris in enumerate(tris_by_object):
        assert np.isfinite(tris).all()
        tile = np.floor(tris[:, :, 0].min(axis=1)).astype(int)
        local = tris.copy()
        local[:, :, 0] -= tile[:, None]
        assert (local >= -1e-6).all() and (local <= 1 + 1e-6).all(), "UV outside its tile"
        for t, (tri, page) in enumerate(zip(local * size, tile)):
            lo = np.floor(tri.min(axis=0)).astype(int)
            hi = np.ceil(tri.max(axis=0)).astype(int)
            xs, ys = np.meshgrid(np.arange(lo[0], hi[0]) + 0.5, np.arange(lo[1], hi[1]) + 0.5)
            p = np.stack([xs.ravel(), ys.ravel()], axis=1)
            a, b, c = tri
            d = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if abs(d) < 1e-9:
                continue
            w1 = ((b[0] - p[:, 0]) * (c[1] - p[:, 1]) - (b[1] - p[:, 1]) * (c[0] - p[:, 0])) / d
            w2 = ((c[0] - p[:, 0]) * (a[1] - p[:, 1]) - (c[1] - p[:, 1]) * (a[0] - p[:, 0])) / d
            inside = (w1 > 1e-6) & (w2 > 1e-6) & (1 - w1 - w2 > 1e-6)
            for x, y in p[inside].astype(int):
                key = (page, x, y)
                assert key not in owner, f"overlap at {key}: {owner[key]} and {(k, t)}"
                owner[key] = (k, t)


def unwrap(**settings):
    result = bpy.ops.uv.uvunwrap(**settings)
    assert result == {"FINISHED"}, result


def test_object_mode_suzanne():
    fresh()
    bpy.ops.mesh.primitive_monkey_add()
    obj = bpy.context.active_object
    unwrap()
    assert "UVMap_Lightmap" in obj.data.uv_layers and "UVMap" in obj.data.uv_layers
    _, tris = uv_triangles(obj)
    assert_valid([tris])


def test_seams_are_chart_boundaries():
    fresh()
    # An open tube with a seam from rim to rim: the faces on its two sides
    # must be apart in UV. (A seam whose ends stay connected around other
    # faces is a slit, which cuts the edge but not its end vertices, as in
    # Blender's own unwrap.)
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, end_fill_type="NOTHING")
    obj = bpy.context.active_object
    me = obj.data
    on_seam = [v.index for v in me.vertices if abs(v.co.y) < 1e-6 and v.co.x > 0]
    edge = next(e for e in me.edges if set(e.vertices) == set(on_seam))
    edge.use_seam = True
    unwrap(max_chart_angle=1.5)  # wide enough that the tube would be one chart
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers["UVMap_Lightmap"].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    for v in on_seam:
        at = {tuple(uv[l.index]) for l in me.loops if l.vertex_index == v}
        assert len(at) == 2, f"vertex {v} has UVs {at} at the seam"
    _, tris = uv_triangles(obj)
    assert_valid([tris])


def test_edit_mode_writes_only_selected_faces():
    fresh()
    bpy.ops.mesh.primitive_monkey_add()
    obj = bpy.context.active_object
    me = obj.data
    layer = me.uv_layers.new(name="UVMap_Lightmap")
    before = np.full(len(me.loops) * 2, 7.0, np.float32)
    layer.data.foreach_set("uv", before)
    for p in me.polygons:
        p.select = p.index % 3 == 0
    bpy.ops.object.mode_set(mode="EDIT")
    unwrap()
    assert bpy.context.mode == "EDIT_MESH"
    bpy.ops.object.mode_set(mode="OBJECT")
    after = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers["UVMap_Lightmap"].data.foreach_get("uv", after)
    after = after.reshape(-1, 2)
    for p in me.polygons:
        changed = not np.all(after[list(p.loop_indices)] == 7.0)
        assert changed == p.select, f"face {p.index}: selected {p.select}, changed {changed}"
    poly, tris = uv_triangles(obj)
    selected = np.array([me.polygons[i].select for i in poly])
    assert_valid([tris[selected]])


def test_objects_share_one_atlas():
    fresh()
    bpy.ops.mesh.primitive_monkey_add(location=(-2, 0, 0))
    bpy.ops.mesh.primitive_torus_add(location=(2, 0, 0))
    objs = list(bpy.context.scene.objects)
    for o in objs:
        o.select_set(True)
    unwrap()
    assert_valid([uv_triangles(o)[1] for o in objs])


def test_fixed_density_spills_onto_udim_tiles():
    fresh()
    bpy.ops.mesh.primitive_monkey_add()
    obj = bpy.context.active_object
    # Suzanne's charts fit a 128-texel page at 40 texels/m, but not together.
    unwrap(density="FIXED", texels_per_meter=40.0, page_size=128)
    _, tris = uv_triangles(obj)
    assert tris[:, :, 0].max() > 1.0, "expected more than one tile"
    assert_valid([tris])


def test_rerun_reuses_the_uv_map():
    fresh()
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    unwrap()
    unwrap(packing="FAST")
    assert [l.name for l in obj.data.uv_layers].count("UVMap_Lightmap") == 1


failures = 0
for name, test in [(n, f) for n, f in list(globals().items()) if n.startswith("test_")]:
    try:
        test()
        print(f"PASS {name}")
    except Exception:
        failures += 1
        print(f"FAIL {name}")
        traceback.print_exc()
print(f"{failures} failed")
if failures:
    sys.exit(1)
