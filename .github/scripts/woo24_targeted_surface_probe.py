#!/usr/bin/env python3
import argparse
import json
import re
import struct
from bisect import bisect_right
from pathlib import Path

TARGET_TERMS = [
    "dynamicTrack", "DynamicTrack", "dirtAccumulation", "DirtAccumulation",
    "TrackWear", "track wear", "TrackTerrainProperties", "TerrainProperties",
    "racetrack_terrain", "grip_factor", "GripFactor", "surface grip",
    "GetIsDynamicTrackEnabled", "dynamic_track", "track_wear"
]

TYPE_NEEDLES = [
    "JimTrackWearSettings", "JimTrackWearSettingsData", "JimSingleTrackWearAlpha",
    "JimSingleTrackWearAlphaSelector", "MGIOptionsHub", "NativeGameOptions", "GameOptions",
    "TrackPhysicsAsset", "TrackTerrainProperties", "TerrainProperties", "MGIGameMaster",
    "PhysDLL", "TrackSettings", "TrackSettingsManagerSaveable", "TrackSettingsDefaults",
    "DirtAccumulationSettingInfo", "DirtAccumulationSetting", "TrackExtrusion",
    "TrackRacingLineFloater", "ChassisTrackData", "PhysWheelTrackData"
]

XREF_METHOD_NAMES = [
    "GetIsDynamicTrackEnabled", "set_dynamic_track", "set_dirt_accumulation",
    "push_track_terrain_property_to_dll", "ILResAddTrackTerrainProperties",
    "Update_Track_Materials", "GetStageTypeIndex", "GraduateRaceTrackWearOriginalSettings",
    "PhysicsBegin", "NotifyPhysicsStartup", "PushConfigToDLL"
]


def parse_types(text):
    parts = re.split(r'(?=// Namespace: )', text)
    out = []
    for part in parts:
        if not part.startswith('// Namespace: '):
            continue
        lines = part.splitlines()
        ns = lines[0][len('// Namespace: '):].strip()
        decl = None
        name = None
        for line in lines[1:35]:
            m = re.search(r'\b(class|struct|enum|interface)\s+([^\s:{]+)', line)
            if m:
                decl = line.strip()
                name = m.group(2)
                break
        if not name:
            continue
        idxm = re.search(r'// TypeDefIndex:\s*(\d+)', part)
        out.append({
            'namespace': ns, 'name': name, 'decl': decl,
            'typedef': int(idxm.group(1)) if idxm else None, 'block': part
        })
    return out


def parse_methods(types):
    methods = []
    for t in types:
        lines = t['block'].splitlines()
        pending = None
        for i, line in enumerate(lines):
            m = re.search(r'// RVA:\s*0x([0-9A-Fa-f]+)\s+Offset:\s*0x([0-9A-Fa-f]+)\s+VA:\s*0x([0-9A-Fa-f]+)', line)
            if m:
                pending = (int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16), i)
                continue
            if pending and '(' in line and ')' in line and not line.strip().startswith('//'):
                decl = line.strip()
                before = decl.split('(', 1)[0].strip()
                name = before.split()[-1] if before else '?'
                methods.append({
                    'type': t['name'], 'namespace': t['namespace'], 'typedef': t['typedef'],
                    'name': name, 'decl': decl, 'rva': pending[0], 'offset': pending[1], 'va': pending[2]
                })
                pending = None
            elif pending and i - pending[3] > 8:
                pending = None
    methods.sort(key=lambda x: (x['rva'], x['type'], x['name']))
    return methods


def find_type_matches(types):
    chosen = []
    for t in types:
        full = f"{t['namespace']}.{t['name']}" if t['namespace'] else t['name']
        if any(n.lower() in full.lower() or n.lower() in t['decl'].lower() for n in TYPE_NEEDLES):
            chosen.append(t)
    return chosen


def method_by_rva(methods):
    # Collapse duplicate generic/shared RVAs, preferring named non-generic declaration.
    d = {}
    for m in methods:
        d.setdefault(m['rva'], m)
    return d


def containing_method(methods, rva):
    uniq = sorted(method_by_rva(methods).values(), key=lambda m: m['rva'])
    starts = [m['rva'] for m in uniq]
    i = bisect_right(starts, rva) - 1
    if i < 0:
        return None
    m = uniq[i]
    # Conservative bound: callsite must be within 0x20000 of method start.
    if rva - m['rva'] > 0x20000:
        return None
    return m


def pe_text_section(path):
    import pefile
    pe = pefile.PE(str(path), fast_load=False)
    image_base = pe.OPTIONAL_HEADER.ImageBase
    for s in pe.sections:
        name = s.Name.rstrip(b'\0').decode('ascii', 'replace')
        if name == '.text':
            return pe, s, image_base
    raise RuntimeError('.text not found')


def direct_call_xrefs(game, methods, target_vas):
    pe, sec, image_base = pe_text_section(game)
    data = sec.get_data()
    sec_rva = sec.VirtualAddress
    by_target = {va: [] for va in target_vas}
    for i in range(0, len(data) - 5):
        if data[i] != 0xE8:
            continue
        rel = struct.unpack_from('<i', data, i + 1)[0]
        insn_va = image_base + sec_rva + i
        target = insn_va + 5 + rel
        if target in by_target:
            call_rva = sec_rva + i
            caller = containing_method(methods, call_rva)
            by_target[target].append((call_rva, insn_va, caller))
    return by_target


def disasm_range(game, start_rva, end_rva, max_bytes=4096):
    import pefile
    from capstone import Cs, CS_ARCH_X86, CS_MODE_64
    pe = pefile.PE(str(game), fast_load=False)
    image_base = pe.OPTIONAL_HEADER.ImageBase
    size = max(1, min(max_bytes, end_rva - start_rva if end_rva > start_rva else max_bytes))
    data = pe.get_data(start_rva, size)
    md = Cs(CS_ARCH_X86, CS_MODE_64)
    out = []
    for ins in md.disasm(data, image_base + start_rva):
        out.append(f"0x{ins.address:X}: {ins.mnemonic} {ins.op_str}".rstrip())
        if len(out) >= 500:
            break
    return out


def next_method_rva(methods, rva):
    vals = sorted({m['rva'] for m in methods if m['rva'] > rva})
    return vals[0] if vals else rva + 4096


def term_context(text, term, radius=16, cap=30):
    lines = text.splitlines()
    hits = []
    lowterm = term.lower()
    for i, line in enumerate(lines):
        if lowterm in line.lower():
            lo, hi = max(0, i-radius), min(len(lines), i+radius+1)
            hits.append((i+1, '\n'.join(lines[lo:hi])))
            if len(hits) >= cap:
                break
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--dump', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    root, dump_dir, out_dir = Path(args.root), Path(args.dump), Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    dump = (dump_dir/'dump.cs').read_text(encoding='utf-8', errors='replace')
    game = next(root.rglob('GameAssembly.dll'))
    types = parse_types(dump)
    methods = parse_methods(types)
    report = []
    report += [
        'WOO24 MODERN COMPARATIVE DIRECT — TARGETED SURFACE RUNTIME TRACE',
        '='*78,
        'Scope: dynamic track toggle, dirt accumulation, track-wear state, spatial terrain/grip, native consumers',
        ''
    ]

    report.append('A. EXACT TERM CONTEXT')
    for term in TARGET_TERMS:
        ctx = term_context(dump, term, radius=8, cap=12)
        report.append(f"\n### TERM {term!r}: {len(ctx)} contexts")
        for line_no, body in ctx:
            report.append(f"--- around dump.cs line {line_no} ---")
            report.append(body)

    report.append('\nB. HIGH-SIGNAL TYPE DEFINITIONS')
    chosen = find_type_matches(types)
    for t in chosen:
        full = f"{t['namespace']}.{t['name']}" if t['namespace'] else t['name']
        report.append(f"\n===== TYPE {full} TypeDef={t['typedef']} =====")
        # Full block, but cap huge monolithic manager types to relevant lines plus method headers.
        lines = t['block'].splitlines()
        if len(lines) <= 450:
            report.extend(lines)
        else:
            report.append(t['decl'])
            for line in lines:
                low = line.lower()
                if any(x.lower() in low for x in [
                    'dynamic', 'dirt', 'terrain', 'trackwear', 'track wear', 'grip', 'surface',
                    'racewear', 'wearfactor', 'racingline', 'preferred', 'moisture', 'water',
                    'marble', 'slick', 'cushion', 'groove', 'loose', 'physicsbegin',
                    'trackphysics', 'tracksettings', 'session', 'stage'
                ]):
                    report.append(line)

    report.append('\nC. ALL METHODS WHOSE TYPE/DECL MATCHES SURFACE RUNTIME TERMS')
    mm = []
    for m in methods:
        hay = f"{m['namespace']} {m['type']} {m['decl']}".lower()
        if any(x in hay for x in [
            'dynamictrack','dynamic_track','dirtaccum','trackwear','track wear','trackterrain',
            'terrainpropert','grip','surface','racetrack_terrain','trackphysics','racingline',
            'marble','slick','cushion','moisture','water','loose','groove'
        ]):
            mm.append(m)
    for m in mm[:600]:
        report.append(f"RVA=0x{m['rva']:X} VA=0x{m['va']:X} {m['namespace']}.{m['type']}::{m['name']} -- {m['decl']}")

    # Find exact targets by name and also selected high-signal methods in classes.
    targets = []
    for m in methods:
        if m['name'] in XREF_METHOD_NAMES:
            targets.append(m)
        elif m['type'].endswith('NativeGameOptions') and any(x in m['name'].lower() for x in ['construct','gameoption','physics','wear','track','dirt']):
            targets.append(m)
        elif m['type'].endswith('MGIOptionsHub') and any(x in m['name'].lower() for x in ['dynamic','dirt','track']):
            targets.append(m)
    # Deduplicate by (rva,type,name)
    seen=set(); targets=[m for m in targets if not ((m['rva'],m['type'],m['name']) in seen or seen.add((m['rva'],m['type'],m['name'])))]
    target_vas = {m['va'] for m in targets}
    xrefs = direct_call_xrefs(game, methods, target_vas)

    report.append('\nD. DIRECT MANAGED NATIVE-CODE CALL XREFS')
    for t in sorted(targets, key=lambda x:(x['type'],x['name'],x['rva'])):
        refs = xrefs.get(t['va'], [])
        report.append(f"\nTARGET {t['namespace']}.{t['type']}::{t['name']} RVA=0x{t['rva']:X} VA=0x{t['va']:X} xrefs={len(refs)}")
        report.append(t['decl'])
        for call_rva, call_va, caller in refs[:100]:
            if caller:
                report.append(f"  callsite RVA=0x{call_rva:X} VA=0x{call_va:X} caller={caller['namespace']}.{caller['type']}::{caller['name']} callerRVA=0x{caller['rva']:X}")
            else:
                report.append(f"  callsite RVA=0x{call_rva:X} VA=0x{call_va:X} caller=UNKNOWN")

    report.append('\nE. FULLER DISASSEMBLY OF HIGH-SIGNAL TARGETS')
    # Keep bounded: only selected semantic targets, max 4096 bytes each.
    dis_names = {
        'GetIsDynamicTrackEnabled','set_dynamic_track','set_dirt_accumulation',
        'push_track_terrain_property_to_dll','ILResAddTrackTerrainProperties',
        'Update_Track_Materials','GetStageTypeIndex','GraduateRaceTrackWearOriginalSettings',
        'NotifyPhysicsStartup','PushConfigToDLL'
    }
    dis_targets=[]
    for m in targets:
        if m['name'] in dis_names:
            dis_targets.append(m)
    # Add NativeGameOptions methods with dynamic/track/wear relevance by declaration.
    for m in methods:
        if m['type'].endswith('NativeGameOptions') and any(x in m['decl'].lower() for x in ['dynamic','track','wear','physics','gameoption']):
            dis_targets.append(m)
    seen=set()
    for m in sorted(dis_targets,key=lambda x:x['rva']):
        key=(m['rva'],m['type'],m['name'])
        if key in seen: continue
        seen.add(key)
        end = next_method_rva(methods, m['rva'])
        ins = disasm_range(game, m['rva'], end, max_bytes=4096)
        report.append(f"\n--- {m['namespace']}.{m['type']}::{m['name']} RVA=0x{m['rva']:X} next=0x{end:X} insns={len(ins)} ---")
        report.append(m['decl'])
        report.extend(ins)

    # Simple explicit absence/presence census for requested semantics in Assembly-CSharp dump.
    report.append('\nF. REQUESTED SEMANTIC TOKEN CENSUS IN DUMP.CS')
    for term in ['groove','slick','cushion','marble','marbles','moisture','water','wet','dry','drying','loose','compaction','rubber','dynamicTrack','dirtAccumulation','TrackWear']:
        count = len(re.findall(re.escape(term), dump, flags=re.I))
        report.append(f"{term}: {count}")

    out=(out_dir/'targeted_surface_trace.txt')
    out.write_text('\n'.join(report)+'\n',encoding='utf-8')
    print('\n'.join(report))

if __name__ == '__main__':
    main()
