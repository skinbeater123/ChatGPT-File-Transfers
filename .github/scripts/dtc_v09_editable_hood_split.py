#!/usr/bin/env python3
"""Build the first practical editable DTC sprint-car body stage from v08.

This is intentionally a modelling operation, not a forensic claim.
The existing 438-face `dtc_hood_candidate_b` envelope is adopted as a
modeller-defined hood seam. The untouched v08 Frame_LOD0 is preserved as a
hidden rollback object; working Body and Hood objects partition its faces.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path

import bpy

V08_SHA = "ad9080c7bc7b9475547edda3ad1eb2ca9fabed6cbd2341b2ac339683b32a6456"
BROAD_ATTR = "dtc_hood_candidate_b"
EXPECTED_HOOD_FACES = 438
ROLLBACK_NAME = "Frame_LOD0_v08_ROLLBACK"
BODY_NAME = "DTC_Body_LOD0"
HOOD_NAME = "DTC_Hood"
ASSET_VERSION = "DTC_SPRINT_A_v09_EDITABLE_HOOD_SPLIT"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def face_signature(obj, poly, digits=8):
    verts = []
    for vi in poly.vertices:
        w = obj.matrix_world @ obj.data.vertices[vi].co
        verts.append(tuple(round(float(w[k]), digits) for k in range(3)))
    # Polygon winding/index order is irrelevant for conservation checking.
    return tuple(sorted(verts))


def mesh_face_multiset(obj):
    return Counter(face_signature(obj, p) for p in obj.data.polygons)


def selected_faces(mesh, attr_name):
    attr = mesh.attributes.get(attr_name)
    if attr is None or attr.domain != 'FACE' or attr.data_type != 'BOOLEAN':
        raise RuntimeError(f"missing FACE boolean attribute {attr_name}")
    return [i for i, x in enumerate(attr.data) if bool(x.value)]


def duplicate_object(src, name):
    obj = src.copy()
    obj.data = src.data.copy()
    obj.name = name
    obj.data.name = name + "_Mesh"
    src.users_collection[0].objects.link(obj)
    return obj


def keep_only_faces(obj, keep_ids):
    keep = set(keep_ids)
    mesh = obj.data
    # Delete in descending source polygon order so source indices remain valid
    # throughout the operation.
    for i in range(len(mesh.polygons) - 1, -1, -1):
        if i not in keep:
            mesh.polygons.remove(i)
    mesh.update()


def delete_faces(obj, delete_ids):
    delete = set(delete_ids)
    mesh = obj.data
    for i in range(len(mesh.polygons) - 1, -1, -1):
        if i in delete:
            mesh.polygons.remove(i)
    mesh.update()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--blend', required=True, type=Path)
    ap.add_argument('--out-blend', required=True, type=Path)
    ap.add_argument('--report', required=True, type=Path)
    ns = ap.parse_args()

    got = sha256(ns.blend)
    if got != V08_SHA:
        raise RuntimeError(f"v08 hash gate failed: {got}")

    bpy.ops.wm.open_mainfile(filepath=str(ns.blend))
    src = bpy.data.objects.get('Frame_LOD0')
    if src is None or src.type != 'MESH':
        raise RuntimeError('Frame_LOD0 missing')

    hood_faces = selected_faces(src.data, BROAD_ATTR)
    if len(hood_faces) != EXPECTED_HOOD_FACES:
        raise RuntimeError(f"hood face count {len(hood_faces)} != {EXPECTED_HOOD_FACES}")

    original_faces = len(src.data.polygons)
    original_verts = len(src.data.vertices)
    original_multiset = mesh_face_multiset(src)

    # The source object itself becomes the immutable rollback witness.
    src.name = ROLLBACK_NAME
    src.data.name = ROLLBACK_NAME + "_Mesh"
    src.hide_viewport = True
    src.hide_render = True
    src['dtc_role'] = 'rollback_v08_full_body'
    src['dtc_editable'] = False

    body = duplicate_object(src, BODY_NAME)
    hood = duplicate_object(src, HOOD_NAME)
    body.hide_viewport = False
    body.hide_render = False
    hood.hide_viewport = False
    hood.hide_render = False

    delete_faces(body, hood_faces)
    keep_only_faces(hood, hood_faces)

    body['dtc_role'] = 'working_body'
    body['dtc_editable'] = True
    body['dtc_source_version'] = 'v08'
    hood['dtc_role'] = 'detachable_hood'
    hood['dtc_editable'] = True
    hood['dtc_component'] = 'hood'
    hood['dtc_boundary_policy'] = 'modeller_defined_from_v08_438_face_visual_envelope'
    hood['dtc_forensic_claim'] = False

    # Remove staging-only evidence attributes from working pieces. The rollback
    # retains them, so nothing is lost.
    for obj in (body, hood):
        for name in ('dtc_hood_candidate_b', 'dtc_hood_reference_core'):
            a = obj.data.attributes.get(name)
            if a is not None:
                obj.data.attributes.remove(a)

    body_multiset = mesh_face_multiset(body)
    hood_multiset = mesh_face_multiset(hood)
    union = body_multiset + hood_multiset
    overlap = body_multiset & hood_multiset
    if union != original_multiset:
        raise RuntimeError('body+hood do not exactly conserve original polygon geometry')
    if sum(overlap.values()) != 0:
        raise RuntimeError('body and hood overlap after split')
    if len(body.data.polygons) + len(hood.data.polygons) != original_faces:
        raise RuntimeError('face-count conservation failed')
    if len(hood.data.polygons) != EXPECTED_HOOD_FACES:
        raise RuntimeError('hood count changed during split')

    scene = bpy.context.scene
    scene['dtc_asset_version'] = ASSET_VERSION
    scene['dtc_parent_asset'] = 'DTC_SPRINT_A_v08_HOOD_COMPONENT_STAGE'
    scene['dtc_parent_sha256'] = V08_SHA
    scene['dtc_modelling_policy'] = 'practical_modeller_defined_components'
    scene['dtc_production_cut'] = True
    scene['dtc_forensic_hood_boundary_claim'] = False
    scene['dtc_rollback_object'] = ROLLBACK_NAME
    scene['dtc_body_object'] = BODY_NAME
    scene['dtc_hood_object'] = HOOD_NAME

    ns.out_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(ns.out_blend))
    out_sha = sha256(ns.out_blend)

    report = {
        'schema': 'dtc_sprint_a_v09_editable_hood_split_v1',
        'asset_version': ASSET_VERSION,
        'parent': {
            'filename': ns.blend.name,
            'sha256': V08_SHA,
        },
        'policy': {
            'operation': 'practical modelling split',
            'forensic_boundary_claim': False,
            'boundary_source': 'v08 dtc_hood_candidate_b visual envelope',
            'rollback_preserved': True,
        },
        'source': {
            'object': 'Frame_LOD0',
            'vertices': original_verts,
            'faces': original_faces,
        },
        'result': {
            'rollback_object': ROLLBACK_NAME,
            'body_object': BODY_NAME,
            'hood_object': HOOD_NAME,
            'body_faces': len(body.data.polygons),
            'hood_faces': len(hood.data.polygons),
            'face_total': len(body.data.polygons) + len(hood.data.polygons),
            'face_geometry_conserved_exactly': True,
            'body_hood_overlap_faces': 0,
            'production_cut': True,
            'output_sha256': out_sha,
        },
        'next_modelling_focus': [
            'visually inspect and clean hood/body seam',
            'correct cockpit position and proportions',
            'add/shape fuel tank',
            'correct cage and side-panel silhouette',
            'correct wing geometry and mounting',
        ],
    }
    ns.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
