"""Create the first reversible DTC modification pass from the validated A01 donor.

Run with Blender 5.2.x:

  blender --background --python modify_a01_to_dtc_v02_blender.py -- \
      --in DTC_BIGANT_A01_DONOR_v01.blend \
      --out DTC_SPRINT_A_v02.blend \
      --baseline-render-dir renders/v01 \
      --render-dir renders/v02 \
      --report DTC_SPRINT_A_v02_mod_report.json \
      --export-glb DTC_SPRINT_A_v02.glb

Safety contract:
- SOURCE_BIGANT_A01_LOCKED is never edited.
- DTC_SPRINT_A_WORK is independently copied to DTC_SPRINT_A_BASELINE_V01 before
  any creative change.
- Only isolated, independently authored parts are changed in v02: top wing,
  front wing and side nerf bars.
- Wheel centres, chassis/engine/suspension meshes, driver and steering remain
  unchanged in this pass. WoO wheel/track targets are guides only for a later
  suspension-aware pass.

Evidence boundary:
- WoO 2002 retail measurements are primary visual/historical reference targets.
- Big Ant A01 is a COMPARATIVE TITLE DIRECT donor.
- This script creates a DTC-authored derivative; it does not import donor physics
  authority into G2-003.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

IN_TO_M = 0.0254
SOURCE_COLLECTION = "SOURCE_BIGANT_A01_LOCKED"
WORK_COLLECTION = "DTC_SPRINT_A_WORK"
BASELINE_COLLECTION = "DTC_SPRINT_A_BASELINE_V01"
GUIDE_COLLECTION = "DTC_WOO_REFERENCE_GUIDES_V02"

WOO = {
    "wheelbase_in": 85.4193,
    "front_track_in": 55.4295,
    "rear_track_in": 52.7976,
    "cockpit_from_rear_in": 5.4467,
    "top_wing_span_in": 62.3471,
    "top_wing_long_in": 78.2231,
    "top_wing_wb_fraction": 0.31294,
    "front_wing_span_in": 40.2439,
    "front_wing_long_in": 21.9439,
    "front_wing_ahead_front_in": 7.3339,
    "nerf_outer_width_in": 55.5684,
    "nerf_long_in": 21.6712,
    "nerf_wb_fraction": 0.37169,
}
BIGANT = {
    "wheelbase_in": 88.3457,
    "front_track_in": 53.8101,
    "rear_track_in": 56.5828,
    "cockpit_from_rear_in": 6.0345,
    "top_wing_span_in": 64.6983,
    "top_wing_long_in": 83.6137,
    "top_wing_wb_fraction": 0.27916,
    "front_wing_span_in": 39.2526,
    "front_wing_long_in": 24.7943,
    "front_wing_ahead_front_in": 10.3745,
    "nerf_outer_width_in": 58.1518,
    "nerf_long_in": 19.0521,
    "nerf_wb_fraction": 0.33268,
}


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="input_blend", required=True, type=Path)
    ap.add_argument("--out", dest="output_blend", required=True, type=Path)
    ap.add_argument("--baseline-render-dir", type=Path)
    ap.add_argument("--render-dir", type=Path)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--export-glb", type=Path)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return ap.parse_args(argv)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def collection(name: str):
    c = bpy.data.collections.get(name)
    if c is None:
        raise RuntimeError(f"required collection missing: {name}")
    return c


def collection_objects_recursive(c):
    seen = set()
    out = []
    stack = [c]
    while stack:
        current = stack.pop()
        for obj in current.objects:
            if obj.name not in seen:
                seen.add(obj.name)
                out.append(obj)
        stack.extend(current.children)
    return out


def mesh_objects(c):
    return [o for o in collection_objects_recursive(c) if o.type == "MESH"]


def match_meshes(c, prefix: str):
    result = [o for o in mesh_objects(c) if o.name.startswith(prefix)]
    if not result:
        raise RuntimeError(f"no work meshes match prefix {prefix!r}")
    return result


def duplicate_collection_objects(source, name: str):
    existing = bpy.data.collections.get(name)
    if existing is not None:
        raise RuntimeError(f"backup collection already exists: {name}")
    backup = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(backup)
    source_objects = collection_objects_recursive(source)
    copies = {}
    for obj in source_objects:
        cp = obj.copy()
        if obj.data is not None:
            cp.data = obj.data.copy()
        cp.hide_select = True
        cp["dtc.rollback_role"] = "V01_PRE_MODIFICATION_BACKUP"
        cp["dtc.source_object"] = obj.name
        backup.objects.link(cp)
        copies[obj] = cp
    for obj, cp in copies.items():
        cp.parent = copies.get(obj.parent)
        if obj.parent is not None and obj.parent in copies:
            cp.matrix_parent_inverse = obj.matrix_parent_inverse.copy()
    backup.hide_render = True
    backup.hide_viewport = True
    backup["dtc.locked_backup"] = True
    backup["dtc.rollback_target"] = "DTC_SPRINT_A_WORK before v02 edits"
    return backup, copies


def world_vertices(objects):
    for obj in objects:
        mw = obj.matrix_world
        for v in obj.data.vertices:
            yield mw @ v.co


def group_bounds(objects):
    pts = list(world_vertices(objects))
    if not pts:
        raise RuntimeError("cannot bound empty mesh group")
    mins = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    maxs = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mins, maxs


def group_center(objects):
    mn, mx = group_bounds(objects)
    return (mn + mx) * 0.5


def scale_translate_group(objects, *, sx=1.0, sy=1.0, sz=1.0, delta=(0.0, 0.0, 0.0), label=""):
    center = group_center(objects)
    delta_v = Vector(delta)
    for obj in objects:
        mw = obj.matrix_world.copy()
        inv = mw.inverted()
        for v in obj.data.vertices:
            p = mw @ v.co
            q = Vector((
                center.x + (p.x - center.x) * sx,
                center.y + (p.y - center.y) * sy,
                center.z + (p.z - center.z) * sz,
            )) + delta_v
            v.co = inv @ q
        obj.data.update()
        obj["dtc.v02_modified"] = True
        obj["dtc.v02_change"] = label
    return center


def object_origin_average(objects):
    if not objects:
        raise RuntimeError("cannot average empty object list")
    acc = Vector((0.0, 0.0, 0.0))
    for o in objects:
        acc += o.matrix_world.translation
    return acc / len(objects)


def add_empty(c, name, location, *, status, extra=None, display_size=0.06):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = display_size
    obj.location = location
    obj["dtc.guide_status"] = status
    obj["dtc.physics_authority"] = "NONE_G2_003_OWNS_SIMULATION"
    if extra:
        for k, v in extra.items():
            obj[k] = v
    c.objects.link(obj)
    return obj


def build_woo_guides(work):
    existing = bpy.data.collections.get(GUIDE_COLLECTION)
    if existing is not None:
        raise RuntimeError(f"guide collection already exists: {GUIDE_COLLECTION}")
    guides = bpy.data.collections.new(GUIDE_COLLECTION)
    bpy.context.scene.collection.children.link(guides)

    lf = match_meshes(work, "WheelLF_LOD0")
    rf = match_meshes(work, "WheelRF_LOD0")
    lr = match_meshes(work, "WheelLR_LOD0")
    rr = match_meshes(work, "WheelRR_LOD0")
    front_now = (object_origin_average(lf) + object_origin_average(rf)) * 0.5
    rear_now = (object_origin_average(lr) + object_origin_average(rr)) * 0.5

    target_front_x = rear_now.x + WOO["wheelbase_in"] * IN_TO_M
    front_half = WOO["front_track_in"] * IN_TO_M * 0.5
    rear_half = WOO["rear_track_in"] * IN_TO_M * 0.5

    add_empty(guides, "LOC_WOO_REAR_AXLE_REFERENCE", (rear_now.x, 0.0, rear_now.z),
              status="WOO_MEASURED_LONGITUDINAL_REFERENCE")
    add_empty(guides, "LOC_WOO_FRONT_AXLE_TARGET", (target_front_x, 0.0, front_now.z),
              status="FUTURE_SUSPENSION_AWARE_TARGET",
              extra={"wheelbase_target_in": WOO["wheelbase_in"]})
    add_empty(guides, "LOC_WOO_LF_TARGET", (target_front_x, front_half, front_now.z),
              status="FUTURE_SUSPENSION_AWARE_TARGET")
    add_empty(guides, "LOC_WOO_RF_TARGET", (target_front_x, -front_half, front_now.z),
              status="FUTURE_SUSPENSION_AWARE_TARGET")
    add_empty(guides, "LOC_WOO_LR_TARGET", (rear_now.x, rear_half, rear_now.z),
              status="FUTURE_SUSPENSION_AWARE_TARGET")
    add_empty(guides, "LOC_WOO_RR_TARGET", (rear_now.x, -rear_half, rear_now.z),
              status="FUTURE_SUSPENSION_AWARE_TARGET")

    cockpit_x = rear_now.x + WOO["cockpit_from_rear_in"] * IN_TO_M
    add_empty(guides, "LOC_WOO_COCKPIT_REFERENCE_DO_NOT_USE_AS_DRIVER_CENTER",
              (cockpit_x, 0.0, rear_now.z),
              status="LONGITUDINAL_LOCATOR_ONLY_NOT_VISIBLE_DRIVER_CENTER",
              extra={"cockpit_from_rear_in": WOO["cockpit_from_rear_in"]})

    top = match_meshes(work, "TopWing_LOD0_DMG0")
    top_c = group_center(top)
    top_x = rear_now.x + WOO["top_wing_wb_fraction"] * WOO["wheelbase_in"] * IN_TO_M
    add_empty(guides, "LOC_WOO_TOP_WING_CENTRE_TARGET", (top_x, 0.0, top_c.z),
              status="V02_APPLIED_TARGET",
              extra={"span_in": WOO["top_wing_span_in"], "long_in": WOO["top_wing_long_in"]})

    front_c = group_center(match_meshes(work, "FrontWing_LOD0_DMG0"))
    future_front_wing_x = target_front_x + WOO["front_wing_ahead_front_in"] * IN_TO_M
    add_empty(guides, "LOC_WOO_FRONT_WING_CENTRE_FUTURE_TARGET", (future_front_wing_x, 0.0, front_c.z),
              status="FUTURE_TARGET_AFTER_WHEELBASE_CHANGE",
              extra={"span_in": WOO["front_wing_span_in"], "long_in": WOO["front_wing_long_in"]})

    guides["dtc.reference_authority"] = "WoO 2002 retail measurements"
    guides["dtc.geometry_role"] = "GUIDES_ONLY"
    guides["dtc.physics_authority"] = "NONE_G2_003_OWNS_SIMULATION"
    return guides, rear_now, front_now


def all_visible_work_bounds(work):
    return group_bounds(mesh_objects(work))


def look_at(camera, target):
    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def render_views(work, out_dir: Path, prefix: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 650
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.display.shading.light = "STUDIO"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.color_type = "SINGLE"
    scene.display.shading.single_color = (0.36, 0.37, 0.40)
    scene.world.color = (0.055, 0.055, 0.055)

    for name in (SOURCE_COLLECTION, BASELINE_COLLECTION, GUIDE_COLLECTION):
        c = bpy.data.collections.get(name)
        if c:
            c.hide_render = True
    work.hide_render = False

    mn, mx = all_visible_work_bounds(work)
    center = (mn + mx) * 0.5
    ext = mx - mn
    radius = max(ext.x, ext.y, ext.z)

    cam_data = bpy.data.cameras.get("DTC_PROOF_CAMERA") or bpy.data.cameras.new("DTC_PROOF_CAMERA")
    cam = bpy.data.objects.get("DTC_PROOF_CAMERA") or bpy.data.objects.new("DTC_PROOF_CAMERA", cam_data)
    if not cam.users_collection:
        scene.collection.objects.link(cam)
    scene.camera = cam

    views = [
        ("LEFT_SIDE", Vector((center.x, center.y + radius * 3.0, center.z + ext.z * 0.05)), True),
        ("FRONT", Vector((center.x + radius * 3.0, center.y, center.z + ext.z * 0.05)), True),
        ("REAR", Vector((center.x - radius * 3.0, center.y, center.z + ext.z * 0.05)), True),
        ("TOP", Vector((center.x, center.y, center.z + radius * 3.5)), True),
        ("FRONT_3_4", Vector((center.x + radius * 2.3, center.y + radius * 2.0, center.z + radius * 1.15)), False),
        ("REAR_3_4", Vector((center.x - radius * 2.3, center.y + radius * 2.0, center.z + radius * 1.15)), False),
    ]

    outputs = []
    for label, loc, ortho in views:
        cam.location = loc
        look_at(cam, center)
        if ortho:
            cam.data.type = "ORTHO"
            cam.data.ortho_scale = max(ext.x, ext.y, ext.z) * 1.28
        else:
            cam.data.type = "PERSP"
            cam.data.lens = 58
        path = out_dir / f"{prefix}_{label}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        outputs.append(str(path))
    return outputs


def export_work_glb(work, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    objs = collection_objects_recursive(work)
    for obj in objs:
        if obj.type == "MESH":
            obj.select_set(True)
    meshes = [o for o in objs if o.type == "MESH"]
    if meshes:
        bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True)


def main():
    ns = parse_args()
    if not ns.input_blend.is_file():
        raise SystemExit(f"input blend not found: {ns.input_blend}")
    input_hash = sha256(ns.input_blend)
    bpy.ops.wm.open_mainfile(filepath=str(ns.input_blend))

    source = collection(SOURCE_COLLECTION)
    work = collection(WORK_COLLECTION)
    if not source.get("dtc.locked_source"):
        raise RuntimeError("source collection is not marked locked")
    if not work.get("dtc.editable"):
        raise RuntimeError("work collection is not marked editable")

    baseline_renders = []
    if ns.baseline_render_dir:
        baseline_renders = render_views(work, ns.baseline_render_dir, "V01_BASE")

    backup, _ = duplicate_collection_objects(work, BASELINE_COLLECTION)
    guides, rear_now, front_now = build_woo_guides(work)

    top = match_meshes(work, "TopWing_LOD0_DMG0")
    top_span_scale = WOO["top_wing_span_in"] / BIGANT["top_wing_span_in"]
    top_long_scale = WOO["top_wing_long_in"] / BIGANT["top_wing_long_in"]
    top_dx = (
        WOO["top_wing_wb_fraction"] * WOO["wheelbase_in"]
        - BIGANT["top_wing_wb_fraction"] * BIGANT["wheelbase_in"]
    ) * IN_TO_M
    scale_translate_group(
        top, sx=top_long_scale, sy=top_span_scale, delta=(top_dx, 0.0, 0.0),
        label="V02_WOO_ENVELOPE_TOP_WING_PITCH_PRESERVED",
    )

    front = match_meshes(work, "FrontWing_LOD0_DMG0")
    front_span_scale = WOO["front_wing_span_in"] / BIGANT["front_wing_span_in"]
    front_long_scale = WOO["front_wing_long_in"] / BIGANT["front_wing_long_in"]
    front_dx = (WOO["front_wing_ahead_front_in"] - BIGANT["front_wing_ahead_front_in"]) * IN_TO_M
    scale_translate_group(
        front, sx=front_long_scale, sy=front_span_scale, delta=(front_dx, 0.0, 0.0),
        label="V02_WOO_ENVELOPE_FRONT_WING_CURRENT_AXLE_REFERENCE",
    )

    left = match_meshes(work, "BumperLeft_DMG0_LOD0")
    right = match_meshes(work, "BumperRight_DMG0_LOD0")
    nerf_long_scale = WOO["nerf_long_in"] / BIGANT["nerf_long_in"]
    nerf_dx = (
        WOO["nerf_wb_fraction"] * WOO["wheelbase_in"]
        - BIGANT["nerf_wb_fraction"] * BIGANT["wheelbase_in"]
    ) * IN_TO_M
    nerf_inward = (BIGANT["nerf_outer_width_in"] - WOO["nerf_outer_width_in"]) * IN_TO_M * 0.5
    scale_translate_group(left, sx=nerf_long_scale, delta=(nerf_dx, -nerf_inward, 0.0),
                          label="V02_WOO_ENVELOPE_LEFT_NERF")
    scale_translate_group(right, sx=nerf_long_scale, delta=(nerf_dx, nerf_inward, 0.0),
                          label="V02_WOO_ENVELOPE_RIGHT_NERF")

    for prefix in ("Frame_LOD0", "Frame_engine_struts_LOD0", "Driver_LOD0", "SteeringWheel_LOD0",
                   "WheelLF_LOD0", "WheelRF_LOD0", "WheelLR_LOD0", "WheelRR_LOD0"):
        for obj in match_meshes(work, prefix):
            obj["dtc.v02_modified"] = False
            obj["dtc.v02_boundary"] = "UNCHANGED_UNTIL_SUSPENSION_AWARE_OR_BODY_FORM_PASS"

    scene = bpy.context.scene
    scene["dtc.asset_version"] = "DTC_SPRINT_A_v02"
    scene["dtc.base_blend_sha256"] = input_hash
    scene["dtc.rollback_base_collection"] = BASELINE_COLLECTION
    scene["dtc.v02_scope"] = "top wing + front wing + side nerf envelope/position only"
    scene["dtc.v02_wheelbase_status"] = "GUIDE_ONLY_NOT_APPLIED"
    scene["dtc.v02_physics_authority"] = "NONE_G2_003_OWNS_SIMULATION"

    ns.output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(ns.output_blend))

    modified_renders = []
    if ns.render_dir:
        modified_renders = render_views(work, ns.render_dir, "V02_MOD")
        bpy.ops.wm.save_as_mainfile(filepath=str(ns.output_blend))

    if ns.export_glb:
        export_work_glb(work, ns.export_glb)

    report = {
        "schema": "dtc_sprint_a_v02_modification_report_v1",
        "base": {
            "path": str(ns.input_blend),
            "sha256": input_hash,
            "immutable_source_collection": SOURCE_COLLECTION,
            "pre_modification_backup_collection": BASELINE_COLLECTION,
        },
        "evidence_boundary": {
            "donor": "Big Ant 2010 retail A01 — COMPARATIVE TITLE DIRECT",
            "primary_visual_targets": "WoO 2002 retail measurements",
            "physics_authority": "NONE — G2-003 remains authoritative for simulation",
        },
        "changes": {
            "top_wing": {
                "span_scale": top_span_scale,
                "longitudinal_scale": top_long_scale,
                "forward_translation_m": top_dx,
                "pitch_changed": False,
            },
            "front_wing": {
                "span_scale": front_span_scale,
                "longitudinal_scale": front_long_scale,
                "translation_x_m": front_dx,
                "reference": "current Big Ant front axle; future WoO wheelbase guide is not yet applied",
                "pitch_changed": False,
            },
            "nerfs": {
                "longitudinal_scale": nerf_long_scale,
                "forward_translation_m": nerf_dx,
                "each_side_inward_m": nerf_inward,
            },
        },
        "deliberately_unchanged": [
            "wheel centres and tyre geometry",
            "Frame_LOD0 body/cage shell",
            "Frame_engine_struts_LOD0 suspension/axle/mechanical structure",
            "driver and steering wheel",
            "front/rear bumpers",
            "top/front wing pitch",
        ],
        "future_guides": {
            "rear_axle_current_m": list(rear_now),
            "front_axle_current_m": list(front_now),
            "woo_wheelbase_target_m": WOO["wheelbase_in"] * IN_TO_M,
            "woo_front_track_target_m": WOO["front_track_in"] * IN_TO_M,
            "woo_rear_track_target_m": WOO["rear_track_in"] * IN_TO_M,
            "guide_collection": GUIDE_COLLECTION,
        },
        "renders": {"baseline": baseline_renders, "modified": modified_renders},
    }
    if ns.report:
        ns.report.parent.mkdir(parents=True, exist_ok=True)
        ns.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("DTC_SPRINT_A_V02_PASS")
    print(json.dumps(report["changes"], indent=2))


if __name__ == "__main__":
    main()
