# SPDX-License-Identifier: GPL-3.0-or-later
"""Reading Blender meshes into uvunwrap inputs and writing the results back
as UV maps, with numpy. Meshes are never modified, only UV maps written.

A Blender polygon's triangles (`loop_triangles`) are passed as one polygon,
so every face corner (loop) gets exactly one UV. Marked seams become chart
boundaries by splitting corners: loops that meet at a vertex across edges
that aren't seams form one corner, and each corner is its own input vertex.
"""

import numpy as np

import uvunwrap


class Source:
    """One object's mesh as unwrapped: what writing its UVs back needs."""

    def __init__(self, obj, tri_loops, tri_written, mesh):
        self.obj = obj
        # Loop of each triangle corner, three per triangle.
        self.tri_loops = tri_loops
        # Triangles whose UVs are written (all, or the selected faces').
        self.tri_written = tri_written
        self.mesh = mesh


def _get(collection, attr, dtype, count, width=1):
    out = np.empty(count * width, dtype)
    collection.foreach_get(attr, out)
    return out.reshape(-1, width) if width > 1 else out


def corners(me, loop_vert):
    """Per loop, a corner id: the lowest loop index of the loops that meet at
    its vertex across edges that aren't seams (or that aren't shared by
    exactly two faces)."""
    nl = len(me.loops)
    loop_start = _get(me.polygons, "loop_start", np.int32, len(me.polygons))
    loop_total = _get(me.polygons, "loop_total", np.int32, len(me.polygons))
    loop_edge = _get(me.loops, "edge_index", np.int32, nl)
    seam = _get(me.edges, "use_seam", bool, len(me.edges))

    # The next loop around each polygon.
    nxt = np.arange(1, nl + 1, dtype=np.int64)
    nxt[loop_start + loop_total - 1] = loop_start

    # Edges shared by exactly two loops, not seams: the two faces' loops at
    # each end of the edge are the same corner.
    order = np.argsort(loop_edge, kind="stable")
    counts = np.bincount(loop_edge, minlength=len(me.edges))
    starts = np.concatenate(([0], np.cumsum(counts)[:-1]))
    joined = (counts == 2) & ~seam
    la, lb = order[starts[joined]], order[starts[joined] + 1]
    na, nb = nxt[la], nxt[lb]
    # Consistently wound faces traverse the edge in opposite directions, so
    # loop la's vertex is at the end of lb's edge; else at its start.
    opposite = loop_vert[la] == loop_vert[nb]
    x = np.concatenate((la, na))
    y = np.concatenate((np.where(opposite, nb, lb), np.where(opposite, lb, nb)))

    # Connected components: propagate the lowest loop index until stable.
    label = np.arange(nl, dtype=np.int64)
    while True:
        before = label.copy()
        np.minimum.at(label, x, label[y])
        np.minimum.at(label, y, label[x])
        label = label[label]
        if np.array_equal(label, before):
            return label


def read(obj, *, selected_only, respect_seams):
    """The uvunwrap Mesh for a mesh object, in world space (so objects share
    one texel density), and its Source; None if no face is to be unwrapped."""
    me = obj.data
    me.calc_loop_triangles()
    nv, nl, nt = len(me.vertices), len(me.loops), len(me.loop_triangles)
    if nt == 0:
        return None
    co = _get(me.vertices, "co", np.float32, nv, 3).astype(np.float64)
    m = np.array(obj.matrix_world, dtype=np.float64)
    co = (co @ m[:3, :3].T + m[:3, 3]).astype(np.float32)
    tri_loops = _get(me.loop_triangles, "loops", np.int32, nt * 3)
    tri_poly = _get(me.loop_triangles, "polygon_index", np.int32, nt)
    loop_vert = _get(me.loops, "vertex_index", np.int32, nl)

    if respect_seams:
        corner = corners(me, loop_vert)
        reps, corner_index = np.unique(corner, return_inverse=True)
        positions = co[loop_vert[reps]]
        indices = corner_index[tri_loops].astype(np.uint32)
    else:
        positions = co
        indices = loop_vert[tri_loops].astype(np.uint32)

    ignored = None
    tri_written = np.ones(nt, bool)
    if selected_only:
        selected = _get(me.polygons, "select", bool, len(me.polygons))
        tri_written = selected[tri_poly]
        if not tri_written.any():
            return None
        ignored = ~tri_written

    mesh = uvunwrap.Mesh(positions, indices, polygons=tri_poly, ignored_faces=ignored)
    return mesh, Source(obj, tri_loops, tri_written, mesh)


def write(source, out, atlas, uv_map, *, fit_square):
    """Writes an output mesh's UVs into the UV map `uv_map` (created if
    missing) for the written triangles' loops; other loops keep their UVs.
    With `fit_square`, a non-square page is scaled into a square image; extra
    pages go to UDIM tiles (u + page). Returns False if the map couldn't be
    created (Blender allows at most 8)."""
    me = source.obj.data
    layer = me.uv_layers.get(uv_map) or me.uv_layers.new(name=uv_map)
    if layer is None:
        return False
    nl = len(me.loops)
    uv = _get(layer.data, "uv", np.float32, nl, 2)

    corner_uv = np.frombuffer(out.corner_uvs, np.float32).reshape(-1, 2).copy()
    if fit_square and atlas.width != atlas.height:
        side = max(atlas.width, atlas.height)
        corner_uv *= (atlas.width / side, atlas.height / side)
    if atlas.page_count > 1:
        page = np.frombuffer(out.page, np.int32)[np.frombuffer(out.indices, np.uint32)]
        corner_uv[:, 0] += np.maximum(page, 0)

    written = np.repeat(source.tri_written, 3)
    uv[source.tri_loops[written]] = corner_uv[written]
    layer.data.foreach_set("uv", uv.ravel())
    me.update()
    return True
