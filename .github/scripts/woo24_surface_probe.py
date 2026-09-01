#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path

KEYWORDS = {
    "track": 8, "trackstate": 12, "trackcondition": 12, "trackgrip": 12, "dynamictrack": 12,
    "surface": 8, "surfacestate": 12, "dirt": 8, "grip": 10, "traction": 9, "friction": 8,
    "groove": 12, "slick": 12, "cushion": 12, "marble": 12, "marbles": 12,
    "moisture": 12, "water": 8, "wet": 7, "dry": 6, "drying": 10, "wear": 9,
    "rubber": 9, "dust": 8, "loose": 9, "rut": 9, "ruts": 9, "deform": 9,
    "terrain": 8, "condition": 6, "progress": 6, "progression": 8, "dynamic": 5,
    "lane": 7, "racingline": 11, "preferredline": 12, "preferred": 5, "line": 2,
    "cell": 6, "grid": 6, "raster": 8, "texture": 5, "vertex": 5, "spline": 7,
    "patch": 5, "sample": 3, "contact": 4, "wheel": 3, "tire": 4, "tyre": 4,
    "vehicle": 3, "traffic": 7, "compaction": 10, "compact": 7, "material": 4,
    "shader": 3, "decal": 4, "blend": 3, "session": 4, "race": 3, "heat": 2,
    "qualifying": 3, "practice": 2, "lap": 2, "physics": 4
}

CATEGORY_TERMS = {
    "physics_surface": ["grip", "traction", "friction", "surface", "terrain", "contact", "physics"],
    "live_track": ["dynamictrack", "trackstate", "trackcondition", "wear", "groove", "slick", "cushion", "marble", "loose", "rut", "deform", "compaction"],
    "moisture_environment": ["moisture", "water", "wet", "dry", "drying", "dust"],
    "spatial_representation": ["cell", "grid", "raster", "texture", "vertex", "spline", "patch", "lane", "sample"],
    "traffic_writer": ["wheel", "tire", "tyre", "vehicle", "traffic", "lap", "contact", "car"],
    "preferred_line": ["racingline", "preferredline", "preferred", "lane", "line"],
    "presentation": ["material", "shader", "texture", "decal", "blend", "render", "mesh"],
    "macro_session": ["session", "race", "heat", "qualifying", "practice", "condition", "progress"]
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def find_one(root: Path, name: str):
    matches = [p for p in root.rglob(name) if p.is_file()]
    return sorted(matches, key=lambda p: (len(p.parts), str(p)))[0] if matches else None


def heap_str(v):
    if v is None:
        return ""
    for attr in ("value", "Value"):
        if hasattr(v, attr):
            x = getattr(v, attr)
            if isinstance(x, bytes):
                return x.decode('utf-8', 'replace')
            return str(x)
    s = str(v)
    if s.startswith("'") and s.endswith("'"):
        s = s[1:-1]
    return s


def assembly_csharp_types(dummy_dll: Path):
    names = set()
    simples = set()
    if not dummy_dll.exists():
        return names, simples, "DummyDll/Assembly-CSharp.dll missing"
    try:
        import dnfile
        pe = dnfile.dnPE(str(dummy_dll))
        rows = getattr(getattr(pe, 'net', None), 'mdtables', None)
        rows = getattr(rows, 'TypeDef', None)
        rows = getattr(rows, 'rows', rows)
        if rows is None:
            return names, simples, "dnfile TypeDef table unavailable"
        for row in rows:
            n = heap_str(getattr(row, 'TypeName', ''))
            ns = heap_str(getattr(row, 'TypeNamespace', ''))
            if not n or n == '<Module>':
                continue
            full = f"{ns}.{n}" if ns else n
            names.add(full)
            simples.add(n.split('`')[0])
        return names, simples, f"{len(names)} TypeDef rows from Assembly-CSharp.dll"
    except Exception as e:
        return names, simples, f"dnfile failed: {type(e).__name__}: {e}"


def parse_dump(dump_path: Path):
    if not dump_path.exists():
        return []
    text = dump_path.read_text(encoding='utf-8', errors='replace')
    parts = re.split(r'(?=// Namespace: )', text)
    out = []
    for part in parts:
        if not part.startswith('// Namespace: '):
            continue
        first = part.splitlines()[:30]
        ns = first[0][len('// Namespace: '):].strip()
        type_name = None
        kind = None
        for line in first[1:]:
            m = re.search(r'\b(class|struct|enum|interface)\s+([A-Za-z0-9_`<>.+]+)', line)
            if m:
                kind, type_name = m.group(1), m.group(2)
                break
        if not type_name:
            continue
        idxm = re.search(r'// TypeDefIndex:\s*(\d+)', part)
        typedef_index = int(idxm.group(1)) if idxm else None
        simple = type_name.split('<')[0].split('`')[0].split('.')[-1]
        full = f"{ns}.{simple}" if ns else simple
        out.append({"namespace": ns, "name": simple, "full": full, "kind": kind,
                    "typedef_index": typedef_index, "block": part})
    return out


def score_block(rec):
    block = rec['block']
    name_low = rec['full'].lower().replace('_', '')
    low = block.lower().replace('_', '')
    score = 0
    hits = []
    for term, weight in KEYWORDS.items():
        t = term.replace('_', '')
        c = low.count(t)
        if c:
            mult = 3 if t in name_low else 1
            score += weight * min(c, 6) * mult
            hits.append((term, c, mult))
    cats = []
    rawlow = block.lower().replace('_', '')
    for cat, terms in CATEGORY_TERMS.items():
        if any(t.replace('_', '') in rawlow for t in terms):
            cats.append(cat)
    return score, hits, cats


def extract_methods(rec):
    lines = rec['block'].splitlines()
    methods = []
    pending = None
    for i, line in enumerate(lines):
        m = re.search(r'// RVA:\s*0x([0-9A-Fa-f]+)\s+Offset:\s*0x([0-9A-Fa-f]+)\s+VA:\s*0x([0-9A-Fa-f]+)', line)
        if m:
            pending = (int(m.group(1), 16), int(m.group(2), 16), int(m.group(3), 16), i)
            continue
        if pending and '(' in line and ')' in line and not line.strip().startswith('//'):
            decl = line.strip()
            before = decl.split('(', 1)[0].strip()
            method_name = before.split()[-1] if before else "?"
            methods.append({"rva": pending[0], "offset": pending[1], "va": pending[2],
                            "line": pending[3], "name": method_name, "decl": decl})
            pending = None
        elif pending and i - pending[3] > 8:
            pending = None
    return methods


def printable_strings(path: Path, min_len=4):
    data = path.read_bytes()
    ascii_hits = [m.group().decode('ascii', 'ignore') for m in re.finditer(rb'[ -~]{%d,}' % min_len, data)]
    # bounded UTF-16LE extraction
    utf16_hits = []
    for m in re.finditer(rb'(?:[ -~]\x00){%d,}' % min_len, data):
        try:
            utf16_hits.append(m.group().decode('utf-16le'))
        except Exception:
            pass
    return ascii_hits, utf16_hits


def keyword_string_hits(strings):
    out = []
    for s in strings:
        low = s.lower().replace('_', '')
        terms = [t for t in KEYWORDS if t.replace('_', '') in low]
        if terms:
            out.append((s, terms))
    return out


def disassemble_methods(gameassembly: Path, methods, limit=30):
    out = []
    try:
        import pefile
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_MODE_32
        pe = pefile.PE(str(gameassembly), fast_load=False)
        machine = pe.FILE_HEADER.Machine
        mode = CS_MODE_64 if machine == 0x8664 else CS_MODE_32
        md = Cs(CS_ARCH_X86, mode)
        for item in methods[:limit]:
            try:
                data = pe.get_data(item['rva'], 192)
                ins = []
                for n, x in enumerate(md.disasm(data, item['va'])):
                    ins.append(f"0x{x.address:X}: {x.mnemonic} {x.op_str}".rstrip())
                    if n >= 29:
                        break
                out.append((item, ins))
            except Exception as e:
                out.append((item, [f"DISASM_ERROR {e}"]))
        return out, f"PE machine=0x{machine:04X}"
    except Exception as e:
        return out, f"disassembly unavailable: {type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--dump', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    root, dump_dir, out_dir = Path(args.root), Path(args.dump), Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    wanted = ['GameAssembly.dll', 'global-metadata.dat', 'WorldOfOutlaws24.exe', 'ScriptingAssemblies.json', 'boot.config']
    files = {n: find_one(root, n) for n in wanted}
    report = []
    report.append('WOO24 MODERN COMPARATIVE DIRECT — IL2CPP SURFACE PROBE')
    report.append('=' * 72)
    report.append('Evidence domain: MODERN WOO24 COMPARATIVE DIRECT')
    report.append('Scope: track/surface/grip architecture only')
    report.append('')
    report.append('FILE INVENTORY / HASHES')
    for n in wanted:
        p = files[n]
        if p:
            report.append(f"{n}: size={p.stat().st_size} sha256={sha256(p)} path={p}")
        else:
            report.append(f"{n}: MISSING")

    meta = files['global-metadata.dat']
    if meta:
        data = meta.read_bytes()[:16]
        if len(data) >= 8:
            magic, version = struct.unpack_from('<II', data, 0)
            report.append('')
            report.append(f"METADATA HEADER: magic=0x{magic:08X} version={version} valid_magic={magic == 0xFAB11BAF}")

    scripting = files['ScriptingAssemblies.json']
    if scripting:
        try:
            j = json.loads(scripting.read_text(encoding='utf-8-sig'))
            names = j.get('names', [])
            report.append(f"SCRIPTING ASSEMBLIES: count={len(names)} Assembly-CSharp.dll={'Assembly-CSharp.dll' in names}")
            report.append('Selected modules: ' + ', '.join(x for x in names if any(k in x for k in ['Assembly-CSharp','Physics','Terrain','Vehicles','Wind','FMOD'])))
        except Exception as e:
            report.append(f"ScriptingAssemblies parse error: {e}")

    dump_cs = dump_dir / 'dump.cs'
    dummy = dump_dir / 'DummyDll' / 'Assembly-CSharp.dll'
    ac_full, ac_simple, ac_note = assembly_csharp_types(dummy)
    report.append('')
    report.append('ASSEMBLY-CSharp TYPE ENUMERATION')
    report.append(ac_note)
    report.append(f"dump.cs present={dump_cs.exists()} size={dump_cs.stat().st_size if dump_cs.exists() else 0}")

    records = parse_dump(dump_cs)
    report.append(f"dump.cs total type blocks={len(records)}")
    filtered = []
    for r in records:
        if ac_full:
            in_ac = r['full'] in ac_full or r['name'] in ac_simple
        else:
            in_ac = not (r['namespace'].startswith(('System','UnityEngine','Unity','TMPro','FMOD','Microsoft')))
        if not in_ac:
            continue
        score, hits, cats = score_block(r)
        if score > 0:
            r = dict(r)
            r.update(score=score, hits=hits, categories=cats, methods=extract_methods(r))
            filtered.append(r)
    filtered.sort(key=lambda x: (-x['score'], x['full']))

    report.append(f"keyword/semantic candidate types in Assembly-CSharp={len(filtered)}")
    report.append('')
    report.append('TOP SURFACE-RELATED TYPE CENSUS')
    for i, r in enumerate(filtered[:100], 1):
        hits = ','.join(f"{t}:{c}" for t,c,_ in r['hits'][:10])
        report.append(f"{i:03d} score={r['score']:4d} TypeDef={r['typedef_index']} {r['full']} [{','.join(r['categories'])}] hits={hits}")

    # Neighbouring type context around highest scored candidates.
    by_idx = {r['typedef_index']: r for r in records if r['typedef_index'] is not None}
    report.append('')
    report.append('NEIGHBOURING TYPE CONTEXT (top 30 candidates, +/-3 TypeDef)')
    seen = set()
    for r in filtered[:30]:
        idx = r['typedef_index']
        if idx is None:
            continue
        neigh = []
        for j in range(idx-3, idx+4):
            q = by_idx.get(j)
            if q:
                neigh.append(f"{j}:{q['full']}")
        line = f"{idx}:{r['full']} -> " + ' | '.join(neigh)
        if line not in seen:
            report.append(line)
            seen.add(line)

    # Candidate field/property/method excerpts.
    report.append('')
    report.append('TOP TYPE DECLARATION EXCERPTS')
    for r in filtered[:35]:
        report.append('')
        report.append(f"--- {r['full']} score={r['score']} TypeDef={r['typedef_index']} ---")
        lines = r['block'].splitlines()
        emitted = 0
        for line in lines:
            low = line.lower().replace('_', '')
            if line.strip().startswith('// Namespace:') or 'TypeDefIndex' in line or any(t.replace('_','') in low for t in KEYWORDS):
                report.append(line[:500])
                emitted += 1
                if emitted >= 45:
                    break

    # Method RVA census ranked by parent type score and method semantic hits.
    method_candidates = []
    for r in filtered:
        for m in r['methods']:
            low = (m['name'] + ' ' + m['decl']).lower().replace('_','')
            mhits = [t for t in KEYWORDS if t.replace('_','') in low]
            bonus = sum(KEYWORDS[t] for t in mhits)
            item = dict(m)
            item.update(type=r['full'], parent_score=r['score'], semantic_hits=mhits,
                        rank=r['score'] + bonus * 8)
            method_candidates.append(item)
    method_candidates.sort(key=lambda x: (-x['rank'], x['rva']))
    report.append('')
    report.append('RELEVANT METHOD RVA / NATIVE ADDRESS CENSUS')
    for i, m in enumerate(method_candidates[:120], 1):
        report.append(f"{i:03d} rank={m['rank']:4d} {m['type']}::{m['name']} RVA=0x{m['rva']:X} Offset=0x{m['offset']:X} VA=0x{m['va']:X} hits={','.join(m['semantic_hits'])} decl={m['decl'][:260]}")

    # String literals emitted by Il2CppDumper.
    lit_path = dump_dir / 'stringliteral.json'
    report.append('')
    report.append('MANAGED STRING LITERAL SURFACE HITS')
    if lit_path.exists():
        try:
            lits = json.loads(lit_path.read_text(encoding='utf-8', errors='replace'))
            shown = 0
            for item in lits if isinstance(lits, list) else []:
                s = str(item.get('value', item.get('Value', '')))
                low = s.lower().replace('_','')
                terms = [t for t in KEYWORDS if t.replace('_','') in low]
                if terms:
                    report.append(f"{terms}: {s[:500]}")
                    shown += 1
                    if shown >= 120:
                        break
            report.append(f"managed literal hits shown={shown}")
        except Exception as e:
            report.append(f"stringliteral parse error: {e}")
    else:
        report.append('stringliteral.json missing')

    # Direct printable strings in supplied binaries, bounded to semantically relevant matches.
    for binary_name in ['GameAssembly.dll', 'WorldOfOutlaws24.exe']:
        p = files[binary_name]
        report.append('')
        report.append(f"DIRECT PRINTABLE STRING HITS — {binary_name}")
        if not p:
            report.append('missing')
            continue
        try:
            a, u = printable_strings(p)
            hits = keyword_string_hits(a + u)
            report.append(f"surface-related printable strings={len(hits)}")
            for s, terms in hits[:120]:
                report.append(f"{terms}: {s[:500]}")
        except Exception as e:
            report.append(f"string scan error: {e}")

    # Native code snippets for top semantically useful methods.
    game = files['GameAssembly.dll']
    report.append('')
    report.append('TARGETED NATIVE DISASSEMBLY — TOP CANDIDATE METHODS')
    if game and method_candidates:
        dis, note = disassemble_methods(game, method_candidates, limit=30)
        report.append(note)
        for m, ins in dis:
            report.append('')
            report.append(f"--- {m['type']}::{m['name']} RVA=0x{m['rva']:X} VA=0x{m['va']:X} rank={m['rank']} ---")
            report.extend(ins)
    else:
        report.append('native disassembly unavailable: GameAssembly or method candidates missing')

    # Machine-readable candidate index, excluding full class blocks.
    machine = []
    for r in filtered[:200]:
        machine.append({
            'full': r['full'], 'namespace': r['namespace'], 'name': r['name'],
            'typedef_index': r['typedef_index'], 'score': r['score'],
            'categories': r['categories'], 'hits': r['hits'],
            'methods': r['methods']
        })
    (out_dir / 'surface_candidates.json').write_text(json.dumps(machine, indent=2), encoding='utf-8')
    (out_dir / 'summary.txt').write_text('\n'.join(report) + '\n', encoding='utf-8')
    print('\n'.join(report))

if __name__ == '__main__':
    main()
