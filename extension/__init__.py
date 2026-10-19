# SPDX-License-Identifier: GPL-3.0-or-later
"""uvunwrap for Blender: automatic lightmap and atlas UVs with the uvunwrap
unwrapper (Rust, via its Python package).

Unwraps the selected mesh objects into one shared atlas (Object Mode), or
the selected faces (Edit Mode), into a UV map. Quads and n-gons stay whole
and marked seams are chart boundaries; the mesh itself is never changed.
"""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

from . import mesh_io


class Settings:
    """Unwrap settings, shared by the scene (sidebar panel) and the operator
    (redo panel, scripts)."""

    uv_map: StringProperty(
        name="UV Map",
        description="UV map to write (created if missing)",
        default="UVMap_Lightmap",
    )
    density: EnumProperty(
        name="Density",
        items=(
            ("AUTO", "Fit Page", "The highest texel density that fits one page"),
            ("FIXED", "Fixed", "A fixed number of texels per meter, on as many pages as needed"),
        ),
        default="AUTO",
    )
    page_size: IntProperty(
        name="Page Size", description="Page width and height in texels",
        default=1024, min=8, soft_max=8192,
    )
    texels_per_meter: FloatProperty(
        name="Texels per Meter", description="Texel density with Fixed density",
        default=32.0, min=0.001, soft_max=1024.0,
    )
    padding: IntProperty(
        name="Padding", description="Empty texels around each chart, against bleeding",
        default=2, min=0, soft_max=16,
    )
    packing: EnumProperty(
        name="Packing",
        items=(
            ("SHAPE", "Shape", "Nest charts into each other's concavities (densest)"),
            ("FAST", "Fast", "Fold charts into rows (milliseconds for thousands of charts)"),
        ),
        default="SHAPE",
    )
    max_chart_angle: FloatProperty(
        name="Angle Limit", description="Maximum angle between a face and its chart's average normal",
        subtype="ANGLE", default=1.2217305, min=0.0175, max=1.553,
    )
    respect_seams: BoolProperty(
        name="Respect Seams", description="Marked seams become chart boundaries", default=True,
    )
    block_align: BoolProperty(
        name="Block Align",
        description="Give every chart whole 4×4 texel blocks, for BC/ASTC-compressed textures",
        default=False,
    )
    fit_square: BoolProperty(
        name="Fit Square Image",
        description="Scale a page that ended up shorter than it is wide into a square image",
        default=True,
    )

    def unwrap_kwargs(self):
        """Keyword arguments for uvunwrap.generate/start."""
        fixed = self.density == "FIXED"
        return dict(
            page_size=self.page_size,
            texels_per_unit=self.texels_per_meter if fixed else None,
            padding=self.padding,
            packing=self.packing.lower(),
            max_chart_angle=self.max_chart_angle * 57.29577951308232,
            block_align=self.block_align,
        )


SETTING_NAMES = [name for name in Settings.__annotations__]


class UVUNWRAP_PG_settings(Settings, bpy.types.PropertyGroup):
    pass


def progress_fraction(p):
    """A rough overall fraction from a stage report."""
    if p is None:
        return 0.0
    span = {"segmenting": (0.0, 0.1), "parameterizing": (0.1, 0.8),
            "packing": (0.8, 0.97), "output": (0.97, 1.0)}.get(p.stage, (0.0, 1.0))
    # Packing reports trials, typically 5-20.
    part = p.done / p.total if p.total else min(p.done / 15.0, 1.0)
    return span[0] + (span[1] - span[0]) * part


class UV_OT_uvunwrap(Settings, bpy.types.Operator):
    """Unwrap the selected objects (or, in Edit Mode, faces) into one atlas"""

    bl_idname = "uv.uvunwrap"
    bl_label = "Unwrap with uvunwrap"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return any(o.type == "MESH" for o in context.selected_objects) or (
            context.active_object is not None and context.active_object.type == "MESH"
        )

    def _prepare(self, context):
        """Reads the meshes; returns the uvunwrap meshes or a message why
        there is nothing to unwrap."""
        self._edit = context.mode == "EDIT_MESH"
        if self._edit:
            objects = {o for o in context.objects_in_mode if o.type == "MESH"}
        else:
            objects = {o for o in context.selected_objects if o.type == "MESH"}
            if context.active_object is not None and context.active_object.type == "MESH":
                objects.add(context.active_object)
        if self._edit:
            bpy.ops.object.mode_set(mode="OBJECT")
        self._sources = []
        for obj in sorted(objects, key=lambda o: o.name):
            read = mesh_io.read(obj, selected_only=self._edit, respect_seams=self.respect_seams)
            if read is not None:
                self._sources.append(read[1])
        if not self._sources:
            self._restore_mode()
            return "No faces selected" if self._edit else "No mesh faces to unwrap"
        return None

    def _restore_mode(self):
        if self._edit:
            bpy.ops.object.mode_set(mode="EDIT")

    def _finish(self, atlas):
        for source, out in zip(self._sources, atlas.meshes):
            if not mesh_io.write(source, out, atlas, self.uv_map, fit_square=self.fit_square):
                self._restore_mode()
                self.report({"ERROR"}, f"{source.obj.name}: can't add another UV map")
                return {"CANCELLED"}
        self._restore_mode()
        pages = f", {atlas.page_count} pages (UDIM)" if atlas.page_count > 1 else ""
        self.report(
            {"INFO"},
            f"uvunwrap: {atlas.chart_count} charts, {atlas.utilization:.0%} of the atlas used{pages}",
        )
        return {"FINISHED"}

    def execute(self, context):
        import uvunwrap

        if (why := self._prepare(context)) is not None:
            self.report({"WARNING"}, why)
            return {"CANCELLED"}
        try:
            atlas = uvunwrap.generate([s.mesh for s in self._sources], **self.unwrap_kwargs())
        except (uvunwrap.UnwrapError, ValueError) as e:
            self._restore_mode()
            self.report({"ERROR"}, f"uvunwrap: {e}")
            return {"CANCELLED"}
        return self._finish(atlas)

    def invoke(self, context, event):
        import uvunwrap

        if context.window is None:
            return self.execute(context)
        if (why := self._prepare(context)) is not None:
            self.report({"WARNING"}, why)
            return {"CANCELLED"}
        try:
            self._job = uvunwrap.start([s.mesh for s in self._sources], **self.unwrap_kwargs())
        except ValueError as e:
            self._restore_mode()
            self.report({"ERROR"}, f"uvunwrap: {e}")
            return {"CANCELLED"}
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.progress_begin(0, 1000)
        wm.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def _end_progress(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        wm.progress_end()
        context.workspace.status_text_set(None)

    def modal(self, context, event):
        import uvunwrap

        if event.type == "ESC":
            self._job.cancel()
        if event.type not in {"TIMER", "ESC"}:
            return {"PASS_THROUGH"}
        if not self._job.done:
            p = self._job.progress
            context.window_manager.progress_update(int(progress_fraction(p) * 1000))
            if p is not None:
                count = f"{p.done}/{p.total}" if p.total else f"{p.done}"
                context.workspace.status_text_set(f"uvunwrap: {p.stage} {count}  (Esc to cancel)")
            return {"RUNNING_MODAL"}
        self._end_progress(context)
        try:
            atlas = self._job.result()
        except uvunwrap.Cancelled:
            self._restore_mode()
            self.report({"WARNING"}, "uvunwrap: cancelled")
            return {"CANCELLED"}
        except uvunwrap.UnwrapError as e:
            self._restore_mode()
            self.report({"ERROR"}, f"uvunwrap: {e}")
            return {"CANCELLED"}
        return self._finish(atlas)


def draw_settings(layout, settings):
    layout.prop(settings, "uv_map")
    layout.prop(settings, "density")
    col = layout.column(align=True)
    col.prop(settings, "page_size")
    if settings.density == "FIXED":
        col.prop(settings, "texels_per_meter")
    layout.prop(settings, "padding")
    layout.prop(settings, "packing")
    layout.prop(settings, "max_chart_angle")
    layout.prop(settings, "respect_seams")
    layout.prop(settings, "block_align")
    layout.prop(settings, "fit_square")


def operator_with(layout, settings, text=None):
    op = layout.operator(UV_OT_uvunwrap.bl_idname, text=text, icon="UV")
    for name in SETTING_NAMES:
        setattr(op, name, getattr(settings, name))


class VIEW3D_PT_uvunwrap(bpy.types.Panel):
    bl_label = "uvunwrap"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "uvunwrap"

    def draw(self, context):
        settings = context.scene.uvunwrap
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        draw_settings(layout, settings)
        what = "Selected Faces" if context.mode == "EDIT_MESH" else "Selected Objects"
        operator_with(layout, settings, text=f"Unwrap {what}")


def menu_entry(self, context):
    self.layout.separator()
    operator_with(self.layout, context.scene.uvunwrap)


classes = (UVUNWRAP_PG_settings, UV_OT_uvunwrap, VIEW3D_PT_uvunwrap)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.uvunwrap = bpy.props.PointerProperty(type=UVUNWRAP_PG_settings)
    bpy.types.VIEW3D_MT_uv_map.append(menu_entry)


def unregister():
    bpy.types.VIEW3D_MT_uv_map.remove(menu_entry)
    del bpy.types.Scene.uvunwrap
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
