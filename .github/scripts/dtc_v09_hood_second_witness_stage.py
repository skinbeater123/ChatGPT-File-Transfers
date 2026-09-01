#!/usr/bin/env python3
"""Build a non-destructive v09 hood second-witness staging file.

Authority rules:
- exact-hash retail WoO Global.pre only;
- exact-hash DTC v08 native stage only;
- Frame_LOD0 vertex/poly geometry is not edited;
- cockpit geometry is used transiently for face-support calculations and is not
  embedded in the output blend;
- no runtime cockpit mount equation is claimed;
- output remains production_cut=false.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path

import bpy
from mathutils import Vector

GLOBAL_SHA = "6219282c663faca7bde0ef955d864aee2aa6cde85532f1614da8517ae9f61289"
V08_SHA = "ad9080c7bc7b9475547edda3ad1eb2ca9fabed6cbd2341b2ac339683b32a6456"
META_START = 9_486_209
GEOMETRY_START = 9_595_782
GEOMETRY_END = 11_026_277
COCKPIT_START = 11_059_027
HOOD = "HOOD_LN_Sol_01_0"
PANEL = "PANEL_mopcut_01_0"
WHEEL_NAMES = ("WHEEL_lf_d0_01_0", "WHEEL_rf_d0_01_0", "WHEEL_lr_d0_01_0", "WHEEL_rr_d0_01_0")
COCKPIT_TARGETS = ("cockpit_HOOD_LN_Sol__0", "cockpit_HOOD_LN_Sol__1", "cockpit_HOOD_LN_Sol__2")
DTC_WHEELS = (
    (1.2359206676483154, .7039546370506287, -.32582324743270874),
    (1.2359206676483154, -.7039546370506287, -.32582324743270874),
    (-.9337295293807983, .6705295443534851, -.3061189353466034),
    (-.9337295293807983, -.6705295443534851, -.3061189353466034),
)
BROAD_ATTR = "dtc_hood_candidate_b"
CORE_ATTR = "dtc_hood_reference_core"
SUPPORT_THRESHOLD = 0.20
MIRROR_THRESHOLDS = (0.03, 0.05, 0.10)
WELD_TOL = 1e-5


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def bounds(vs):
    return (
        tuple(min(v[i] for v in vs) for i in range(3)),
        tuple(max(v[i] for v in vs) for i in range(3)),
    )


def midpoint(bb):
    lo, hi = bb
    return tuple((lo[i] + hi[i]) * 0.5 for i in range(3))


def extent(bb):
    lo, hi = bb
    return tuple(hi[i] - lo[i] for i in range(3))


def add(a, b):
    return tuple(a[i] + b[i] for i in range(3))


def sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def dist(a, b):
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def quantile(xs, frac):
    s = sorted(xs)
    return s[min(len(s) - 1, int(round((len(s) - 1) * frac)))] if s else None


def mesh_names(data: bytes, start: int, end: int):
    out = []
    p = start
    while True:
        h = data.find(b"MeshFile\0", p, end)
        if h < 0:
            break
        s = h + 9
        e = data.find(b"\0", s, min(end, s + 256))
        if e < 0:
            break
        raw = data[s:e]
        if raw and all(32 <= c < 127 for c in raw):
            out.append((h, raw.decode("ascii")))
        p = e + 1
    return out


def matrix_for_mesh(data: bytes, hit: int, limit: int):
    h = data.find(b"\0Matrix\0", hit, min(limit, hit + 5000))
    if h < 0:
        return None
    s = h + 1 + len(b"Matrix\0")
    m = struct.unpack_from("<12f", data, s)
    if not all(math.isfinite(x) for x in m):
        return None
    return (m[0:4], m[4:8], m[8:12])


def apply34(v, m):
    return tuple(sum(m[r][c] * v[c] for c in range(3)) + m[r][3] for r in range(3))


def parse_section(data: bytes, p: int):
    if p < 0 or p + 21 > len(data):
        return None
    vc = struct.unpack_from("<I", data, p + 13)[0]
    if not 3 <= vc <= 100_000:
        return None
    vs = p + 17
    to = vs + vc * 40
    if to + 4 > len(data):
        return None
    tc = struct.unpack_from("<I", data, to)[0]
    if not 1 <= tc <= 200_000:
        return None
    end = to + 4 + tc * 12
    if end > len(data):
        return None
    verts = []
    good_normals = 0
    sn = min(vc, 24)
    for i in range(vc):
        o = vs + i * 40
        pos = struct.unpack_from("<3f", data, o)
        if not all(math.isfinite(x) for x in pos) or any(abs(x) > 1_000_000 for x in pos):
            return None
        verts.append(pos)
        if i < sn:
            n = struct.unpack_from("<3f", data, o + 12)
            if all(math.isfinite(x) for x in n):
                nn = math.sqrt(sum(x * x for x in n))
                if .75 <= nn <= 1.25:
                    good_normals += 1
            uv = struct.unpack_from("<2f", data, o + 32)
            if not all(math.isfinite(x) for x in uv):
                return None
    if good_normals < max(2, int(sn * .70)):
        return None
    tris = []
    for i in range(tc):
        tri = struct.unpack_from("<3I", data, to + 4 + i * 12)
        if max(tri) >= vc:
            return None
        tris.append(tri)
    return {"offset": p, "end": end, "header": data[p:p + 13], "verts": verts, "tris": tris}


def parse_external(data: bytes):
    ns = mesh_names(data, META_START, GEOMETRY_START)
    if len(ns) != 102:
        raise RuntimeError(("external MeshFile count", len(ns)))
    p = GEOMETRY_START
    sections = []
    for hit, name in ns:
        sec = parse_section(data, p)
        if sec is None:
            raise RuntimeError(("external section", name, p))
        sec.update(name=name, metadata_offset=hit)
        sections.append(sec)
        p = sec["end"]
    if p != GEOMETRY_END - 9:
        raise RuntimeError(("external end", p, GEOMETRY_END - 9))
    fixed = []
    for j in range(13):
        vals = {s["header"][j] for s in sections}
        if len(vals) == 1:
            fixed.append((j, next(iter(vals))))
    return ns, sections, fixed


def scan_cockpit(data: bytes, fixed):
    ns = mesh_names(data, COCKPIT_START, len(data))
    sections = []
    p = COCKPIT_START
    while p < len(data) - 21:
        if all(data[p + j] == v for j, v in fixed):
            sec = parse_section(data, p)
            if sec is not None:
                sections.append(sec)
                p = sec["end"]
                continue
        p += 1
    if len(ns) != len(sections):
        raise RuntimeError(("cockpit ordinal mapping", len(ns), len(sections)))
    for i, sec in enumerate(sections):
        sec.update(name=ns[i][1], metadata_offset=ns[i][0])
    return ns, sections


def point_triangle_distance(p, a, b, c):
    # Real-Time Collision Detection, Christer Ericson.
    px = Vector(p); av = Vector(a); bv = Vector(b); cv = Vector(c)
    ab = bv - av; ac = cv - av; ap = px - av
    d1 = ab.dot(ap); d2 = ac.dot(ap)
    if d1 <= 0 and d2 <= 0: return (px - av).length
    bp = px - bv; d3 = ab.dot(bp); d4 = ac.dot(bp)
    if d3 >= 0 and d4 <= d3: return (px - bv).length
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3); q = av + v * ab; return (px - q).length
    cp = px - cv; d5 = ab.dot(cp); d6 = ac.dot(cp)
    if d6 >= 0 and d5 <= d6: return (px - cv).length
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6); q = av + w * ac; return (px - q).length
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6)); q = bv + w * (cv - bv); return (px - q).length
    denom = 1.0 / (va + vb + vc); v = vb * denom; w = vc * denom
    q = av + ab * v + ac * w
    return (px - q).length


def face_centroid_world(obj, poly):
    return tuple(obj.matrix_world @ (sum((obj.data.vertices[i].co for i in poly.vertices), Vector()) / len(poly.vertices)))


def poly_world_vertices(obj, poly):
    return [tuple(obj.matrix_world @ obj.data.vertices[i].co) for i in poly.vertices]


def geometry_digest(obj):
    h = hashlib.sha256()
    for v in obj.data.vertices:
        w = obj.matrix_world @ v.co
        h.update(struct.pack("<3d", float(w.x), float(w.y), float(w.z)))
    for p in obj.data.polygons:
        h.update(struct.pack("<I", len(p.vertices)))
        for i in p.vertices:
            h.update(struct.pack("<I", int(i)))
    return h.hexdigest()


def add_bool_face_attr(mesh, name, selected):
    old = mesh.attributes.get(name)
    if old is not None:
        mesh.attributes.remove(old)
    a = mesh.attributes.new(name=name, type='BOOLEAN', domain='FACE')
    s = set(selected)
    for i, x in enumerate(a.data):
        x.value = i in s


def welded_components(obj, face_ids, tol=WELD_TOL):
    # Spatially welded edge adjacency, so material/UV seam duplicates do not fragment evidence.
    def key(co):
        w = obj.matrix_world @ co
        return tuple(round(float(w[k]) / tol) for k in range(3))
    edges = {}
    for fi in face_ids:
        p = obj.data.polygons[fi]
        ks = [key(obj.data.vertices[i].co) for i in p.vertices]
        for j in range(len(ks)):
            e = tuple(sorted((ks[j], ks[(j + 1) % len(ks)])))
            edges.setdefault(e, []).append(fi)
    adj = {fi: set() for fi in face_ids}
    for fs in edges.values():
        if len(fs) > 1:
            for a in fs:
                adj[a].update(b for b in fs if b != a)
    out = []
    left = set(face_ids)
    while left:
        root = min(left); stack = [root]; comp = set()
        while stack:
            x = stack.pop()
            if x in comp: continue
            comp.add(x); left.discard(x); stack.extend(adj[x] - comp)
        out.append(sorted(comp))
    out.sort(key=lambda x: (-len(x), x[0]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--blend', required=True, type=Path)
    ap.add_argument('--global-pre', required=True, type=Path)
    ap.add_argument('--out-blend', required=True, type=Path)
    ap.add_argument('--report', required=True, type=Path)
    ap.add_argument('--face-json', required=True, type=Path)
    ns = ap.parse_args()

    if sha256(ns.blend) != V08_SHA:
        raise RuntimeError('v08 hash gate')
    if sha256(ns.global_pre) != GLOBAL_SHA:
        raise RuntimeError('Global.pre hash gate')

    data = ns.global_pre.read_bytes()
    ext_names, ext_sections, fixed = parse_external(data)
    cock_names, cock_sections = scan_cockpit(data, fixed)
    ext_by_name = {s['name']: s for s in ext_sections}
    cock_by_name = {s['name']: s for s in cock_sections}

    hood = ext_by_name[HOOD]; panel = ext_by_name[PANEL]
    hbb = bounds(hood['verts']); pbb = bounds(panel['verts'])
    norm = (pbb[1][0] - hbb[1][0], pbb[0][1] - hbb[0][1], pbb[0][2] - hbb[0][2])
    hood_n = [add(v, norm) for v in hood['verts']]
    hm = matrix_for_mesh(data, hood['metadata_offset'], GEOMETRY_START)
    hood_world = [apply34(v, hm) for v in hood_n]
    ext_bb = bounds(hood_world)

    cockpit_verts = []
    cockpit_tris = []
    cockpit_parts = []
    for name in COCKPIT_TARGETS:
        sec = cock_by_name[name]
        idx = next(i for i, (_, n) in enumerate(cock_names) if n == name)
        lim = cock_names[idx + 1][0] if idx + 1 < len(cock_names) else sec['offset']
        cm = matrix_for_mesh(data, sec['metadata_offset'], max(lim, sec['metadata_offset'] + 5000))
        local = [apply34(v, cm) for v in sec['verts']] if cm else sec['verts']
        base = len(cockpit_verts); cockpit_verts.extend(local)
        cockpit_tris.extend(tuple(base + x for x in t) for t in sec['tris'])
        cockpit_parts.append({'name': name, 'verts': len(local), 'tris': len(sec['tris']), 'bounds': bounds(local)})
    cock_bb = bounds(cockpit_verts)

    # Constrained registration diagnostics: axes and scale are fixed by the shared Ratbag
    # source coordinate system. Only translation is allowed. X/Y midpoints nearly coincide
    # after translation; Z is intentionally tested three ways because cockpit visual geometry
    # is not assumed to share the exact external runtime mount preprocessing.
    em = midpoint(ext_bb); cmid = midpoint(cock_bb)
    regs = {
        'bbox_mid_xyz': (em[0] - cmid[0], em[1] - cmid[1], em[2] - cmid[2]),
        'bbox_mid_xy_min_z': (em[0] - cmid[0], em[1] - cmid[1], ext_bb[0][2] - cock_bb[0][2]),
        'bbox_mid_xy_max_z': (em[0] - cmid[0], em[1] - cmid[1], ext_bb[1][2] - cock_bb[1][2]),
    }

    wheel_world = []
    for n in WHEEL_NAMES:
        hit = next(h for h, name in ext_names if name == n)
        m = matrix_for_mesh(data, hit, GEOMETRY_START)
        wheel_world.append(tuple(m[r][3] for r in range(3)))
    scales = (
        (DTC_WHEELS[0][0] - DTC_WHEELS[2][0]) / (wheel_world[0][1] - wheel_world[2][1]),
        (DTC_WHEELS[0][1] - DTC_WHEELS[1][1]) / (-(wheel_world[0][0] - wheel_world[1][0])),
        (DTC_WHEELS[2][1] - DTC_WHEELS[3][1]) / (-(wheel_world[2][0] - wheel_world[3][0])),
    )
    scale = sum(scales) / 3.0
    fY = (wheel_world[0][1] + wheel_world[1][1]) / 2.0
    fX = (wheel_world[0][0] + wheel_world[1][0]) / 2.0
    tx = DTC_WHEELS[0][0] - scale * fY
    ty = scale * fX
    tz = DTC_WHEELS[0][2] - scale * wheel_world[0][2]
    def wd(v):
        return (scale * v[1] + tx, -scale * v[0] + ty, scale * v[2] + tz)

    bpy.ops.wm.open_mainfile(filepath=str(ns.blend))
    frame = bpy.data.objects.get('Frame_LOD0')
    if frame is None or frame.type != 'MESH':
        raise RuntimeError('Frame_LOD0 missing')
    mesh = frame.data
    broad_attr = mesh.attributes.get(BROAD_ATTR); core_attr = mesh.attributes.get(CORE_ATTR)
    if broad_attr is None or core_attr is None:
        raise RuntimeError('v08 face attributes missing')
    broad = [i for i, x in enumerate(broad_attr.data) if bool(x.value)]
    core = [i for i, x in enumerate(core_attr.data) if bool(x.value)]
    if len(broad) != 438 or len(core) != 171:
        raise RuntimeError(("v08 attr counts", len(broad), len(core)))
    before_digest = geometry_digest(frame)
    cents = {i: face_centroid_world(frame, mesh.polygons[i]) for i in broad}

    support_sets = {}
    distance_stats = {}
    mapped_bounds = {}
    for rname, tr in regs.items():
        cv = [wd(add(v, tr)) for v in cockpit_verts]
        ct = [(cv[a], cv[b], cv[c]) for a, b, c in cockpit_tris]
        mapped_bounds[rname] = bounds(cv)
        ds = {}
        for fi in broad:
            p = cents[fi]
            ds[fi] = min(point_triangle_distance(p, *tri) for tri in ct)
        chosen = sorted(fi for fi, d in ds.items() if d < SUPPORT_THRESHOLD)
        support_sets[rname] = chosen
        vals = sorted(ds.values())
        distance_stats[rname] = {
            'supported_faces_lt_0_20m': len(chosen),
            'core_supported': sum(fi in set(chosen) for fi in core),
            'median_m': quantile(vals, .5), 'p90_m': quantile(vals, .9), 'max_m': max(vals),
        }
    stable = sorted(set.intersection(*(set(x) for x in support_sets.values())))
    union = sorted(set.union(*(set(x) for x in support_sets.values())))

    # Reflect the direct external core across the DTC chassis centre plane. This is a derived
    # diagnostic justified by the direct cockpit witness's 52/52 bilateral hood evidence; it
    # is not itself promoted to a cut boundary.
    center_y = sum(w[1] for w in DTC_WHEELS) / len(DTC_WHEELS)
    mirror_sets = {}
    mirror_dist_stats = {}
    broad_ids = list(broad)
    for threshold in MIRROR_THRESHOLDS:
        matches = set()
        dvals = []
        for fi in core:
            c = cents[fi]
            target = (c[0], 2 * center_y - c[1], c[2])
            bj = min(broad_ids, key=lambda j: dist(target, cents[j]))
            dd = dist(target, cents[bj]); dvals.append(dd)
            if dd < threshold:
                matches.add(bj)
        mirror_sets[f'{threshold:.2f}'] = sorted(matches)
        mirror_dist_stats[f'{threshold:.2f}'] = {
            'unique_faces': len(matches), 'median_m': quantile(dvals, .5), 'p90_m': quantile(dvals, .9), 'max_m': max(dvals)
        }
    mirror_05 = set(mirror_sets['0.05'])
    bilateral_seed = sorted(set(core) | mirror_05)

    components = welded_components(frame, broad)
    stable_set = set(stable); core_set = set(core); bilateral_set = set(bilateral_seed)
    comp_rows = []
    for n, comp in enumerate(components):
        cs = set(comp)
        comp_rows.append({
            'component': n, 'faces': len(comp),
            'direct_core': len(cs & core_set),
            'bilateral_seed': len(cs & bilateral_set),
            'cockpit_stable_0_20': len(cs & stable_set),
            'cockpit_stable_fraction': len(cs & stable_set) / len(comp),
        })
    grown_direct = sorted(fi for comp in components if set(comp) & core_set for fi in comp)
    grown_bilateral = sorted(fi for comp in components if set(comp) & bilateral_set for fi in comp)

    eps = .02
    def lateral_counts(ids):
        out = {'negative_y': 0, 'central_y': 0, 'positive_y': 0}
        for fi in ids:
            y = cents[fi][1] - center_y
            if y < -eps: out['negative_y'] += 1
            elif y > eps: out['positive_y'] += 1
            else: out['central_y'] += 1
        return out

    # Persist only DTC face-domain evidence masks. No Ratbag geometry is embedded.
    for name, ids in (
        ('dtc_hood_cockpit_mid_020', support_sets['bbox_mid_xyz']),
        ('dtc_hood_cockpit_minz_020', support_sets['bbox_mid_xy_min_z']),
        ('dtc_hood_cockpit_maxz_020', support_sets['bbox_mid_xy_max_z']),
        ('dtc_hood_cockpit_stable_020', stable),
        ('dtc_hood_external_core_mirror_050', mirror_sets['0.05']),
        ('dtc_hood_bilateral_seed_050', bilateral_seed),
    ):
        add_bool_face_attr(mesh, name, ids)

    after_digest = geometry_digest(frame)
    if after_digest != before_digest:
        raise RuntimeError('Frame_LOD0 geometry changed while staging attributes')

    scene = bpy.context.scene
    scene['dtc_asset_version'] = 'DTC_SPRINT_A_v09_HOOD_SECOND_WITNESS_STAGE'
    scene['dtc_parent_v08_sha256'] = V08_SHA
    scene['dtc_global_pre_sha256'] = GLOBAL_SHA
    scene['dtc_production_cut'] = False
    scene['dtc_second_witness'] = 'cockpit_HOOD_LN_Sol__0/__1/__2'
    scene['dtc_second_witness_faces'] = 104
    scene['dtc_second_witness_bilateral'] = True
    scene['dtc_frame_geometry_digest'] = before_digest

    report = {
        'schema': 'dtc_sprint_a_v09_hood_second_witness_stage_v1',
        'source': {'v08_sha256': V08_SHA, 'global_pre_sha256': GLOBAL_SHA},
        'authority': {'production_cut': False, 'frame_geometry_unchanged': before_digest == after_digest},
        'v08': {'broad_faces': len(broad), 'direct_core_faces': len(core), 'frame_geometry_digest': before_digest},
        'cockpit_direct_witness': {
            'parts': cockpit_parts, 'vertices': len(cockpit_verts), 'triangles': len(cockpit_tris),
            'bounds_internal': cock_bb, 'extent_internal': extent(cock_bb),
            'semantic_result': 'complete bilateral hood witness; no exact runtime mount equation claimed',
        },
        'external_normalized_reference': {
            'vertices': len(hood_world), 'triangles': len(hood['tris']), 'bounds_internal': ext_bb,
            'extent_internal': extent(ext_bb), 'normalization_translation_internal': norm,
        },
        'registration': {
            'rule': 'fixed source axes and wheel-derived scale; translation-only bbox registrations; three Z anchors retained as uncertainty band',
            'translations_internal': regs, 'mapped_cockpit_bounds_dtc_m': mapped_bounds,
            'woofer_to_dtc': {'scale_m_per_internal_unit': scale, 'component_scales': scales, 'tx_m': tx, 'ty_m': ty, 'tz_m': tz},
        },
        'cockpit_support_0_20m': {
            'per_registration': distance_stats,
            'stable_all_three_faces': len(stable), 'union_any_faces': len(union),
            'stable_lateral_counts': lateral_counts(stable),
            'stable_direct_core_overlap': len(stable_set & core_set),
            'stable_direct_core_fraction': len(stable_set & core_set) / len(core),
        },
        'bilateral_external_diagnostic': {
            'chassis_center_y_m': center_y, 'mirror_thresholds': mirror_dist_stats,
            'mirror_faces_by_threshold': {k: len(v) for k, v in mirror_sets.items()},
            'bilateral_seed_0_05_faces': len(bilateral_seed),
            'bilateral_seed_lateral_counts': lateral_counts(bilateral_seed),
        },
        'topology': {
            'position_weld_tol_m': WELD_TOL, 'broad_components': len(components),
            'grown_from_direct_core_faces': len(grown_direct),
            'grown_from_bilateral_seed_faces': len(grown_bilateral),
            'components': comp_rows,
        },
        'decision': {
            'production_cut': False,
            'why': 'This pass establishes face-level bilateral second-witness support and registration stability. A cut is promoted only if the evidence masks converge on a stable topological boundary rather than by choosing a convenient threshold.',
        },
    }

    face_payload = {
        'schema': 'dtc_sprint_a_v09_hood_second_witness_face_sets_v1',
        'broad': broad, 'direct_core': core, 'cockpit_support': support_sets,
        'cockpit_stable': stable, 'cockpit_union': union,
        'mirror_core': mirror_sets, 'bilateral_seed_0_05': bilateral_seed,
        'grown_direct': grown_direct, 'grown_bilateral': grown_bilateral,
        'production_cut_authority': False,
    }

    ns.report.parent.mkdir(parents=True, exist_ok=True)
    ns.report.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    ns.face_json.write_text(json.dumps(face_payload, indent=2) + '\n', encoding='utf-8')
    bpy.ops.wm.save_as_mainfile(filepath=str(ns.out_blend))
    print(json.dumps({
        'V09_SECOND_WITNESS_STAGE_PASS': True,
        'stable_faces': len(stable), 'union_faces': len(union),
        'bilateral_seed_faces': len(bilateral_seed),
        'grown_bilateral_faces': len(grown_bilateral),
        'production_cut': False,
    }, indent=2))


if __name__ == '__main__':
    main()
