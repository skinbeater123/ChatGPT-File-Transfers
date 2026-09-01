#!/usr/bin/env python3
"""Bounded forensic probe for the WoO 2002 retail cockpit RAT scene.

The script emits names, offsets, transforms, geometry counts/bounds and derived
symmetry/comparison statistics only. It never writes extracted mesh payload.
"""
from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
from pathlib import Path

EXPECTED_SHA = "6219282c663faca7bde0ef955d864aee2aa6cde85532f1614da8517ae9f61289"
EXTERNAL_META_START = 9_486_209
EXTERNAL_GEOMETRY_START = 9_595_782
EXTERNAL_GEOMETRY_END = 11_026_277
COCKPIT_START = 11_059_027
EXTERNAL_HOOD = "HOOD_LN_Sol_01_0"
EXTERNAL_PANEL = "PANEL_mopcut_01_0"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def finite3(v):
    return all(math.isfinite(x) for x in v)


def bounds(vs):
    return (
        tuple(min(v[i] for v in vs) for i in range(3)),
        tuple(max(v[i] for v in vs) for i in range(3)),
    )


def centroid(vs):
    n = len(vs)
    return tuple(sum(v[i] for v in vs) / n for i in range(3))


def dist2(a, b):
    return sum((a[i] - b[i]) ** 2 for i in range(3))


def quantile(xs, f):
    q = sorted(xs)
    if not q:
        return None
    return q[min(len(q) - 1, int(round((len(q) - 1) * f)))]


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
        p = max(e + 1, h + 9)
    return out


def matrix_for_mesh(data: bytes, metadata_hit: int, search_end: int):
    mh = data.find(b"\0Matrix\0", metadata_hit, min(search_end, metadata_hit + 4000))
    if mh < 0:
        return None
    start = mh + 1 + len(b"Matrix\0")
    if start + 48 > len(data):
        return None
    m = struct.unpack_from("<12f", data, start)
    if not all(math.isfinite(x) for x in m):
        return None
    return (m[0:4], m[4:8], m[8:12])


def apply34(v, m):
    return tuple(sum(m[r][c] * v[c] for c in range(3)) + m[r][3] for r in range(3))


def parse_section(data: bytes, p: int, *, full_indices=True):
    if p < 0 or p + 21 > len(data):
        return None
    vc = struct.unpack_from("<I", data, p + 13)[0]
    if vc < 3 or vc > 100_000:
        return None
    vs = p + 17
    to = vs + vc * 40
    if to + 4 > len(data):
        return None
    tc = struct.unpack_from("<I", data, to)[0]
    if tc < 1 or tc > 200_000:
        return None
    end = to + 4 + tc * 12
    if end > len(data):
        return None

    # Strong MeshFile-stream validation using the independently proven external grammar.
    sample_n = min(vc, 32)
    good_normals = 0
    good_open = 0
    verts = []
    for i in range(vc):
        off = vs + i * 40
        pos = struct.unpack_from("<3f", data, off)
        if not finite3(pos) or any(abs(x) > 1_000_000 for x in pos):
            return None
        verts.append(pos)
        if i < sample_n:
            normal = struct.unpack_from("<3f", data, off + 12)
            if not finite3(normal):
                return None
            nn = math.sqrt(sum(x * x for x in normal))
            if 0.75 <= nn <= 1.25:
                good_normals += 1
            open_u32 = struct.unpack_from("<I", data, off + 28)[0]
            if open_u32 == 1:
                good_open += 1
            uv = struct.unpack_from("<2f", data, off + 32)
            if not finite3((uv[0], uv[1], 0.0)):
                return None
    if good_normals < max(2, int(sample_n * 0.70)):
        return None
    # The cockpit path may differ in the open field, so record rather than require it.

    indices = []
    max_index = -1
    if full_indices:
        for i in range(tc):
            tri = struct.unpack_from("<3I", data, to + 4 + i * 12)
            if max(tri) >= vc:
                return None
            indices.append(tri)
            max_index = max(max_index, *tri)
    else:
        for i in range(min(tc, 64)):
            tri = struct.unpack_from("<3I", data, to + 4 + i * 12)
            if max(tri) >= vc:
                return None
            max_index = max(max_index, *tri)

    return {
        "offset": p,
        "header_hex": data[p:p + 13].hex(),
        "vertex_count": vc,
        "triangle_count": tc,
        "vertices": verts,
        "triangles": indices,
        "open_u32_one_sample_fraction": good_open / sample_n,
        "end": end,
        "max_sampled_or_full_index": max_index,
    }


def parse_external(data: bytes):
    names = mesh_names(data, EXTERNAL_META_START, EXTERNAL_GEOMETRY_START)
    if len(names) != 102:
        raise RuntimeError(("external mesh-name count", len(names)))
    p = EXTERNAL_GEOMETRY_START
    sections = []
    headers = []
    for _, name in names:
        sec = parse_section(data, p)
        if sec is None:
            raise RuntimeError(("external section parse", name, p))
        sec["name"] = name
        sections.append(sec)
        headers.append(bytes.fromhex(sec["header_hex"]))
        p = sec["end"]
    if p != EXTERNAL_GEOMETRY_END - 9:
        raise RuntimeError(("external geometry end", p, EXTERNAL_GEOMETRY_END - 9))
    fixed = []
    for j in range(13):
        vals = {h[j] for h in headers}
        if len(vals) == 1:
            fixed.append((j, next(iter(vals))))
    return names, sections, headers, fixed


def header_matches(data: bytes, p: int, fixed):
    if p + 13 > len(data):
        return False
    return all(data[p + j] == v for j, v in fixed)


def find_cockpit_geometry(data: bytes, cockpit_names, fixed):
    # Metadata should precede geometry. Search from the last MeshFile declaration forward.
    search_start = cockpit_names[-1][0] + 9 if cockpit_names else COCKPIT_START
    # Do not scan beyond a bounded 800 KiB window; cockpit DB is only ~1.34 MiB total.
    search_end = min(len(data) - 21, search_start + 800_000)
    target_n = len(cockpit_names)
    candidates = []
    p = search_start
    while p < search_end:
        if header_matches(data, p, fixed):
            first = parse_section(data, p, full_indices=False)
            if first is not None:
                q = p
                parsed = []
                ok = True
                for _ in range(target_n):
                    sec = parse_section(data, q)
                    if sec is None:
                        ok = False
                        break
                    parsed.append(sec)
                    q = sec["end"]
                if ok:
                    candidates.append((p, q, parsed))
                    # Exact-name-count chain is sufficiently strong; keep scanning only a
                    # little farther so an accidental earlier candidate cannot dominate.
                    if len(candidates) >= 4:
                        break
        p += 1
    if not candidates:
        return None, []
    # Prefer candidate with one-to-one MeshFile count and closest location after metadata.
    candidates.sort(key=lambda x: x[0])
    return candidates[0], [(a, b) for a, b, _ in candidates]


def bilateral_stats(vs, axis=0):
    # Translation-invariant about the point-cloud midplane, suitable for cockpit-local data.
    lo, hi = bounds(vs)
    mid = (lo[axis] + hi[axis]) * 0.5
    width = hi[axis] - lo[axis]
    if width <= 1e-12:
        return {"axis": axis, "mid": mid, "width": width, "median_reflect_nn": 0.0, "p90_reflect_nn": 0.0}
    reflected = []
    for v in vs:
        w = list(v)
        w[axis] = 2 * mid - w[axis]
        reflected.append(tuple(w))
    # Keep this bounded; deterministic thinning if a mesh is large.
    step = max(1, len(vs) // 500)
    ds = []
    for r in reflected[::step]:
        ds.append(math.sqrt(min(dist2(r, v) for v in vs)))
    return {
        "axis": axis,
        "mid": mid,
        "width": width,
        "median_reflect_nn": quantile(ds, 0.5),
        "p90_reflect_nn": quantile(ds, 0.9),
        "median_over_width": quantile(ds, 0.5) / width,
        "p90_over_width": quantile(ds, 0.9) / width,
    }


def triangle_side_counts(vs, tris, axis=0):
    if not tris:
        return None
    lo, hi = bounds(vs)
    mid = (lo[axis] + hi[axis]) * 0.5
    eps = max(1e-6, (hi[axis] - lo[axis]) * 0.02)
    out = {"negative": 0, "central": 0, "positive": 0, "mid": mid, "eps": eps}
    for tri in tris:
        c = sum(vs[i][axis] for i in tri) / 3.0
        if c < mid - eps:
            out["negative"] += 1
        elif c > mid + eps:
            out["positive"] += 1
        else:
            out["central"] += 1
    return out


def centered_nn_stats(a, b):
    ca, cb = centroid(a), centroid(b)
    aa = [tuple(v[i] - ca[i] for i in range(3)) for v in a]
    bb = [tuple(v[i] - cb[i] for i in range(3)) for v in b]
    step = max(1, len(aa) // 500)
    ds = [math.sqrt(min(dist2(v, w) for w in bb)) for v in aa[::step]]
    return {
        "median": quantile(ds, 0.5),
        "p90": quantile(ds, 0.9),
        "max": max(ds) if ds else None,
        "centroid_a": ca,
        "centroid_b": cb,
    }


def semantic_ascii(data: bytes, start: int):
    runs = []
    s = None
    for i in range(start, len(data)):
        c = data[i]
        good = 32 <= c < 127
        if good and s is None:
            s = i
        elif not good and s is not None:
            if i - s >= 4:
                text = data[s:i].decode("ascii", errors="ignore")
                low = text.lower()
                if any(k in low for k in ("hood", "wing", "cockpit", "chassis", "body", "gauge", "needle", "lever", "camera", ".dds")):
                    runs.append({"offset": s, "text": text[:240]})
            s = None
    return runs[:300]


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: woo_cockpit_hood_probe.py Global.pre report.json")
    src = Path(sys.argv[1])
    out = Path(sys.argv[2])
    digest = sha256(src)
    if digest != EXPECTED_SHA:
        raise RuntimeError(("Global.pre SHA-256 mismatch", digest))
    data = src.read_bytes()
    if len(data) != 12_401_519:
        raise RuntimeError(("Global.pre size mismatch", len(data)))

    ext_names, ext_sections, ext_headers, fixed = parse_external(data)
    ext_by_name = {s["name"]: s for s in ext_sections}

    # Cockpit MeshFile declarations are bounded to the second RAT scene only.
    cockpit_names = mesh_names(data, COCKPIT_START, len(data))
    geometry_candidate, candidate_ranges = find_cockpit_geometry(data, cockpit_names, fixed)

    report = {
        "schema": "woo_cockpit_hood_witness_probe_v1",
        "source": {
            "name": src.name,
            "size": len(data),
            "sha256": digest,
            "cockpit_rat_start": COCKPIT_START,
            "cockpit_signature_offset_expected": 11_059_031,
        },
        "external_parser_reproduction": {
            "mesh_sections": len(ext_sections),
            "geometry_start": EXTERNAL_GEOMETRY_START,
            "geometry_end_parsed": ext_sections[-1]["end"],
            "fixed_header_positions": fixed,
            "unique_header_hex_count": len(set(h.hex() for h in ext_headers)),
        },
        "cockpit_metadata": {
            "meshfile_count": len(cockpit_names),
            "meshfiles": [{"index": i, "metadata_offset": h, "name": n} for i, (h, n) in enumerate(cockpit_names)],
            "first_eight_contract_role": "cockpit hoods, same order as external part 9, per retail carparts.str" if len(cockpit_names) >= 8 else "NOT ESTABLISHED",
            "semantic_ascii": semantic_ascii(data, COCKPIT_START),
        },
        "geometry_candidate_ranges": candidate_ranges,
        "evidence_boundary": {
            "ratbag_direct": "raw cockpit names/transforms/geometry statistics from exact-hash retail Global.pre",
            "not_claimed": "exact shipped runtime preprocessing equation or DTC production cut boundary",
        },
    }

    if geometry_candidate is None:
        report["cockpit_geometry"] = {
            "status": "NO_ONE_TO_ONE_40_BYTE_STREAM_FOUND",
            "decision": "do not cut; cockpit geometry grammar requires another bounded decode",
        }
    else:
        gs, ge, sections = geometry_candidate
        for i, sec in enumerate(sections):
            sec["name"] = cockpit_names[i][1]
        report["cockpit_geometry"] = {
            "status": "ONE_TO_ONE_40_BYTE_STREAM_FOUND",
            "geometry_start": gs,
            "geometry_end": ge,
            "section_count": len(sections),
        }

        first_eight = []
        for i, sec in enumerate(sections[:8]):
            hit, name = cockpit_names[i]
            next_hit = cockpit_names[i + 1][0] if i + 1 < len(cockpit_names) else gs
            m = matrix_for_mesh(data, hit, max(hit + 4000, next_hit))
            vs = sec["vertices"]
            wvs = [apply34(v, m) for v in vs] if m is not None else None
            first_eight.append({
                "index": i,
                "name": name,
                "metadata_offset": hit,
                "geometry_offset": sec["offset"],
                "vertex_count": sec["vertex_count"],
                "triangle_count": sec["triangle_count"],
                "raw_bounds": bounds(vs),
                "raw_centroid": centroid(vs),
                "stored_matrix": m,
                "world_bounds_if_matrix_applied": bounds(wvs) if wvs else None,
                "world_centroid_if_matrix_applied": centroid(wvs) if wvs else None,
                "raw_bilateral_axis0": bilateral_stats(vs, 0),
                "world_bilateral_axis0": bilateral_stats(wvs, 0) if wvs else None,
                "raw_triangle_side_counts_axis0": triangle_side_counts(vs, sec["triangles"], 0),
                "world_triangle_side_counts_axis0": triangle_side_counts(wvs, sec["triangles"], 0) if wvs else None,
                "open_u32_one_sample_fraction": sec["open_u32_one_sample_fraction"],
            })
        report["cockpit_geometry"]["first_eight"] = first_eight

        # Reproduce external Beulah hood normalization and compare the second cockpit hood
        # (contract index 1) at the point-cloud level without inventing a mount equation.
        if len(sections) >= 2 and EXTERNAL_HOOD in ext_by_name and EXTERNAL_PANEL in ext_by_name:
            hood = ext_by_name[EXTERNAL_HOOD]
            panel = ext_by_name[EXTERNAL_PANEL]
            hmin, hmax = bounds(hood["vertices"])
            pmin, pmax = bounds(panel["vertices"])
            norm = (pmax[0] - hmax[0], pmin[1] - hmin[1], pmin[2] - hmin[2])
            hood_n = [tuple(v[j] + norm[j] for j in range(3)) for v in hood["vertices"]]
            ext_hit = next(h for h, n in ext_names if n == EXTERNAL_HOOD)
            ext_m = matrix_for_mesh(data, ext_hit, EXTERNAL_GEOMETRY_START)
            hood_world = [apply34(v, ext_m) for v in hood_n] if ext_m else hood_n

            csec = sections[1]
            chit = cockpit_names[1][0]
            cnext = cockpit_names[2][0] if len(cockpit_names) > 2 else gs
            cm = matrix_for_mesh(data, chit, max(chit + 4000, cnext))
            c_raw = csec["vertices"]
            c_world = [apply34(v, cm) for v in c_raw] if cm else c_raw

            report["beulah_contract_index_1_comparison"] = {
                "external_name": EXTERNAL_HOOD,
                "cockpit_index": 1,
                "cockpit_name": cockpit_names[1][1],
                "external_normalization_translation_internal_units": norm,
                "external_normalized_world_bounds": bounds(hood_world),
                "cockpit_raw_bounds": bounds(c_raw),
                "cockpit_world_bounds_if_matrix_applied": bounds(c_world),
                "centered_raw_cockpit_to_external_normalized_world_nn": centered_nn_stats(c_raw, hood_world),
                "centered_world_cockpit_to_external_normalized_world_nn": centered_nn_stats(c_world, hood_world),
                "cockpit_raw_axis0_symmetry": bilateral_stats(c_raw, 0),
                "cockpit_world_axis0_symmetry": bilateral_stats(c_world, 0),
                "interpretation_rule": "statistics are shape/witness diagnostics only; no runtime mount or production cut is inferred from them",
            }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report.get("cockpit_geometry", {}).get("status"),
        "cockpit_meshfile_count": len(cockpit_names),
        "report": str(out),
    }, indent=2))


if __name__ == "__main__":
    main()
