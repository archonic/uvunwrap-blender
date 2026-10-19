# SPDX-License-Identifier: GPL-3.0-or-later
"""Takes the listing screenshots: the UV Editing workspace after an unwrap
(docs/uv_editing.png, resized from the capture) and the exported UV layout
(docs/layout.png). Needs the UI and the extension installed:

    blender --factory-startup --enable-event-simulate \
        --window-geometry 0 0 1600 900 --python scripts/screenshots.py -- OUT_DIR

(with BLENDER_USER_RESOURCES pointing at a user directory where the built
extension is installed). Simulated clicks select the sidebar's uvunwrap tab,
since scripts can't set a region's active tab.
"""
import bpy, sys, pathlib
out = pathlib.Path(sys.argv[sys.argv.index("--") + 1])
bpy.ops.preferences.addon_enable(module="bl_ext.user_default.uvunwrap")

def win_override():
    win = bpy.context.window_manager.windows[0]
    return win

def setup():
    win = win_override()
    with bpy.context.temp_override(window=win):
        for o in list(bpy.data.objects):
            bpy.data.objects.remove(o)
        bpy.ops.mesh.primitive_monkey_add(location=(-1.3, 0, 0), rotation=(0, 0, 0.5))
        monkey = bpy.context.active_object
        monkey.modifiers.new("s", "SUBSURF").levels = 1
        bpy.ops.object.modifier_apply(modifier="s")
        bpy.ops.object.shade_smooth()
        bpy.ops.mesh.primitive_torus_add(location=(1.4, 0, 0), rotation=(1.2, 0, 0.3))
        bpy.ops.object.shade_smooth()
        for o in bpy.data.objects:
            o.select_set(True)
        # A UV grid image, shown through the lightmap UVs on both objects.
        img = bpy.data.images.new("UV Grid", 1024, 1024)
        img.generated_type = "COLOR_GRID"
        mat = bpy.data.materials.new("Grid")
        mat.use_nodes = True
        nt = mat.node_tree
        tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img
        uvn = nt.nodes.new("ShaderNodeUVMap"); uvn.uv_map = "UVMap_Lightmap"
        nt.links.new(uvn.outputs["UV"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
        nt.nodes.active = tex
        for o in bpy.data.objects:
            o.data.materials.append(mat)
        bpy.ops.uv.uvunwrap()
        for o in bpy.data.objects:
            layers = o.data.uv_layers
            layers.active = layers["UVMap_Lightmap"]
        win.workspace = bpy.data.workspaces["UV Editing"]
    bpy.app.timers.register(arrange, first_interval=0.5)

def arrange():
    win = win_override()
    screen = win.screen
    bpy.context.view_layer.objects.active = bpy.data.objects[0]
    for o in bpy.data.objects:
        o.select_set(True)
    view3d = next(a for a in screen.areas if a.type == "VIEW_3D")
    uved = next(a for a in screen.areas if a.type == "IMAGE_EDITOR")
    scene = bpy.context.scene
    # All UVs visible in the UV editor without highlighting anything.
    scene.tool_settings.use_uv_select_sync = True
    with bpy.context.temp_override(window=win, area=view3d, region=next(r for r in view3d.regions if r.type == "WINDOW")):
        if bpy.context.mode != "EDIT_MESH":
            bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="DESELECT")
        sp = view3d.spaces.active
        sp.shading.type = "SOLID"
        sp.shading.color_type = "TEXTURE"
        sp.show_region_ui = True
        sp.overlay.show_overlays = False
        bpy.ops.view3d.view_all()
    uved.spaces.active.image = bpy.data.images["UV Grid"]
    with bpy.context.temp_override(window=win, area=uved, region=next(r for r in uved.regions if r.type == "WINDOW")):
        bpy.ops.image.view_all(fit_view=True)
    state["ui"] = next(r for r in view3d.regions if r.type == "UI")
    state["y"] = state["ui"].y + state["ui"].height - 10
    ui = state["ui"]
    bpy.app.timers.register(click_tab, first_interval=0.5)


state = {}


def click(win, x, y):
    win.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x, y=y)
    win.event_simulate(type="LEFTMOUSE", value="PRESS", x=x, y=y)
    win.event_simulate(type="LEFTMOUSE", value="RELEASE", x=x, y=y)


def click_tab():
    """Clicks down the sidebar's tab strip until the uvunwrap tab is active.
    Clicking the active tab collapses or expands the sidebar, so it ends by
    clicking that tab again if the sidebar is collapsed."""
    ui, win = state["ui"], win_override()
    # The middle of the tab strip; the region's very edge is its resize handle.
    x = ui.x + ui.width - 22
    if ui.active_panel_category == "uvunwrap":
        if ui.width < 200:
            click(win, x, state["y"])
            return 0.2
        print("SHOT tab active, sidebar width", ui.width)
        bpy.app.timers.register(shoot, first_interval=1.5)
        return None
    state["y"] -= 12
    if state["y"] < ui.y:
        print("SHOT tab not found")
        bpy.app.timers.register(shoot, first_interval=1.5)
        return None
    click(win, x, state["y"])
    return 0.05


def shoot():
    win = win_override()
    with bpy.context.temp_override(window=win):
        # Simulated input doesn't trigger redraws: draw the window first.
        bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
        bpy.ops.screen.screenshot(filepath=str(out / "uv_editing.png"))
        view3d = next(a for a in win.screen.areas if a.type == "VIEW_3D")
        with bpy.context.temp_override(window=win, area=view3d):
            bpy.ops.uv.export_layout(filepath=str(out / "layout.png"), export_all=True, mode="PNG", size=(1600, 1600), opacity=0.6)
    print("SHOT done")
    bpy.ops.wm.quit_blender()
    return None

bpy.app.timers.register(setup, first_interval=1.0)
