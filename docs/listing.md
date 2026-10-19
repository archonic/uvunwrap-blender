<!-- Description for the extensions.blender.org listing (paste into the
     form). Keep claims to what docs/ and the uvunwrap repo can back up.
     Images (no Blender logo anywhere, ToS 2.2):
     - Icon (exactly 256 x 256 PNG): icon.png, from icon.svg
       (rsvg-convert -w 256 -h 256 icon.svg -o icon.png).
     - Featured image (at least 1920 x 1080, 16:9): featured.png, the
       screenshot capture with the menu bar cropped off.
     - Previews (at least one): featured.png ("The UV Editing workspace after
       an unwrap: the packed layout, the models textured through it, and the
       uvunwrap panel") and layout.png ("The packed atlas: small charts nest
       inside the torus rings"). -->

**uvunwrap** creates clean, non-overlapping UVs for lightmaps, baking and
texture atlases, automatically and in seconds.

## What it does

- **Object Mode:** unwraps all selected mesh objects into one shared atlas,
  in world space, so texel density matches across objects.
- **Edit Mode:** unwraps only the selected faces; other faces keep their UVs.
- Writes the result into a UV map of your choice (`UVMap_Lightmap` by
  default, created if missing). **Your mesh is never modified.**
- Splits each mesh into charts, flattens them with low distortion and packs
  them tightly, nesting small charts inside larger charts' holes and
  concavities.
- **Guarantees:** no overlapping or folded triangles, the padding you set
  between charts and to the page edges, and uniform texel density across
  every chart and object.
- Quads and n-gons stay whole; marked seams become chart boundaries.
- Large meshes unwrap in the background with a progress bar; press **Esc**
  to cancel. The result is a single undo step.

## Where to find it

- Sidebar (**N**) → **uvunwrap** tab: settings and the unwrap button.
- Edit Mode **UV** menu (**U**) → **Unwrap with uvunwrap**.

## Settings

- **UV Map**: the UV map to write.
- **Density**: *Fit Page* (the highest density that fits one page) or
  *Fixed* (texels per meter, spilling onto UDIM tiles when one page isn't
  enough).
- **Page Size**, **Padding** (in texels).
- **Packing**: *Shape* (densest) or *Fast* (milliseconds for thousands of
  charts).
- **Angle Limit**, **Respect Seams**, **Block Align** (whole 4×4 texel blocks
  for BC/ASTC compression), **Fit Square Image**.

## Compared with Blender's built-in tools

On six standard test models (Spot, Beetle, Stanford Bunny, Armadillo,
Nefertiti, Igea) at the same padding, uvunwrap packed 1–17 percentage points
more of the page than Smart UV Project + Pack Islands, ran 21–350× faster,
and produced no folded triangles (Smart UV Project folded triangles inside
islands on every model). Lightmap Pack gives every triangle its own island;
at its default margin the gap between islands is about one texel, and
widening it toward uvunwrap's 4-texel gap left about 24% of the page used on
Spot, against 70% for uvunwrap.

## How it's built

The add-on itself is plain Python. The unwrapping is done by the open-source
[uvunwrap](https://github.com/archonic/uvunwrap) library (MIT, written in
Rust), bundled as its unmodified wheels from
[PyPI](https://pypi.org/project/uvunwrap/), whose full source is public.
Add-on source and issue tracker:
[github.com/archonic/uvunwrap-blender](https://github.com/archonic/uvunwrap-blender).
