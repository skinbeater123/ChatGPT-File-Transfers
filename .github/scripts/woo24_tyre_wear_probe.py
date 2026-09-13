#!/usr/bin/env python3
import argparse, json, re, struct, hashlib
from pathlib import Path

TERMS = [
    'tirewear','tyrewear','tire wear','tyre wear','wearconfig','wear config','wear',
    'tire','tyre','wheel','gfxwheel','material','renderer','speed','dirt','rubber',
    'temperature','pressure','grip','life','laps','tread','compound'
]
HIGH = ['tirewear','tyrewear','wearconfig','wear','tire','tyre','gfxwheel','wheel']


def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for c in iter(lambda:f.read(1<<20),b''): h.update(c)
    return h.hexdigest()


def parse_dump(path):
    text=Path(path).read_text(encoding='utf-8',errors='replace')
    blocks=[]
    for part in re.split(r'(?=// Namespace: )',text):
        if not part.startswith('// Namespace: '): continue
        lines=part.splitlines()
        ns=lines[0][len('// Namespace: '):].strip()
        name='?'; kind='?'
        for line in lines[1:35]:
            m=re.search(r'\b(class|struct|enum|interface)\s+([A-Za-z0-9_`<>.+]+)',line)
            if m:
                kind,name=m.group(1),m.group(2); break
        idxm=re.search(r'// TypeDefIndex:\s*(\d+)',part)
        idx=int(idxm.group(1)) if idxm else None
        blocks.append({'ns':ns,'name':name,'full':f'{ns}.{name}' if ns else name,'kind':kind,'idx':idx,'block':part})
    return blocks


def method_lines(block):
    lines=block.splitlines(); out=[]; pending=None
    for i,line in enumerate(lines):
        m=re.search(r'// RVA:\s*0x([0-9A-Fa-f]+).*VA:\s*0x([0-9A-Fa-f]+)',line)
        if m:
            pending=(m.group(1),m.group(2),i); continue
        if pending and '(' in line and ')' in line and not line.strip().startswith('//'):
            out.append((pending[0],pending[1],line.strip())); pending=None
        elif pending and i-pending[2]>8:
            pending=None
    return out


def printable_strings(path,minlen=4):
    data=Path(path).read_bytes(); out=[]
    for m in re.finditer(rb'[ -~]{%d,}'%minlen,data):
        out.append(m.group().decode('ascii','ignore'))
    for m in re.finditer(rb'(?:[ -~]\x00){%d,}'%minlen,data):
        try: out.append(m.group().decode('utf-16le'))
        except: pass
    return out


def relevant(s):
    low=s.lower().replace('_',' ')
    return any(t in low for t in TERMS)


def exports(path):
    try:
        import pefile
        pe=pefile.PE(str(path),fast_load=False)
        rows=[]
        if hasattr(pe,'DIRECTORY_ENTRY_EXPORT'):
            for sym in pe.DIRECTORY_ENTRY_EXPORT.symbols:
                name=(sym.name or b'').decode('ascii','ignore')
                if relevant(name): rows.append((name,sym.address))
        return rows
    except Exception as e:
        return [('ERROR:'+repr(e),0)]


def disasm(path,rva,limit=80):
    try:
        import pefile
        from capstone import Cs,CS_ARCH_X86,CS_MODE_64
        pe=pefile.PE(str(path),fast_load=False)
        va=pe.OPTIONAL_HEADER.ImageBase+rva
        data=pe.get_data(rva,512)
        md=Cs(CS_ARCH_X86,CS_MODE_64)
        out=[]
        for i,x in enumerate(md.disasm(data,va)):
            out.append(f'0x{x.address:X}: {x.mnemonic} {x.op_str}'.rstrip())
            if i>=limit-1: break
        return out
    except Exception as e:
        return ['DISASM_ERROR '+repr(e)]


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--dump',required=True); ap.add_argument('--phys',required=False); ap.add_argument('--out',required=True)
    a=ap.parse_args(); root=Path(a.root); dump=Path(a.dump); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    report=[]
    report += ['WOO24 TYRE/TIRE WEAR FORENSIC PROBE','='*78,'Evidence domain: direct runtime metadata/native binaries; visual-wear question','']
    game=next(root.rglob('GameAssembly.dll'),None); meta=next(root.rglob('global-metadata.dat'),None)
    if game: report.append(f'GameAssembly.dll sha256={sha256(game)} size={game.stat().st_size}')
    if meta: report.append(f'global-metadata.dat sha256={sha256(meta)} size={meta.stat().st_size}')
    report.append('')
    blocks=parse_dump(dump/'dump.cs')
    scored=[]
    for b in blocks:
        low=b['block'].lower().replace('_',' ')
        hits=[t for t in TERMS if t in low]
        name_low=b['full'].lower().replace('_',' ')
        score=sum((20 if t in name_low else 1) for t in hits) + sum(40 for t in ['tirewear','tyrewear','wearconfig'] if t in low.replace(' ',''))
        if hits: scored.append((score,hits,b))
    scored.sort(key=lambda x:(-x[0],x[2]['full']))
    report += ['HIGH-SIGNAL MANAGED TYPE CENSUS']
    for score,hits,b in scored[:120]:
        if score<4 and not any(h in b['full'].lower() for h in HIGH): continue
        report.append(f"score={score:3d} TypeDef={b['idx']} {b['full']} hits={','.join(hits)}")
    report.append('')
    report.append('FULL DECLARATION EXCERPTS FOR TYRE/WHEEL/WEAR TYPES')
    chosen=[]
    for score,hits,b in scored:
        nl=b['full'].lower()
        bl=b['block'].lower().replace('_','')
        if any(k in nl for k in ['tire','tyre','wheel','wear']) or 'wearconfig' in bl or 'tirewear' in bl or 'tyrewear' in bl:
            chosen.append(b)
    seen=set()
    for b in chosen[:80]:
        if b['full'] in seen: continue
        seen.add(b['full']); report += ['',f"--- {b['full']} TypeDef={b['idx']} ---"]
        for line in b['block'].splitlines():
            lo=line.lower().replace('_',' ')
            if (line.strip().startswith('// Namespace:') or 'TypeDefIndex' in line or any(t in lo for t in TERMS) or any(x in line for x in ['Material','Renderer','Texture','Mesh','Color','Float','float','bool','int'])):
                report.append(line[:700])
        ml=method_lines(b['block'])
        if ml:
            report.append('METHOD_RVAS:')
            for rva,va,decl in ml[:80]: report.append(f'  RVA 0x{rva} VA 0x{va} {decl}')
    # stringliteral json if present
    report += ['','STRING LITERAL HITS']
    lit=dump/'stringliteral.json'
    if lit.exists():
        try:
            j=json.loads(lit.read_text(encoding='utf-8',errors='replace'))
            items=j if isinstance(j,list) else j.get('ScriptString',j.get('strings',[])) if isinstance(j,dict) else []
            vals=[]
            for x in items:
                s=x.get('value') if isinstance(x,dict) else str(x)
                if s and relevant(s): vals.append(s)
            for s in sorted(set(vals))[:500]: report.append(s[:1000])
        except Exception as e: report.append('stringliteral parse error '+repr(e))
    if game:
        report += ['','GAMEASSEMBLY PRINTABLE STRING HITS']
        vals=[]
        for s in printable_strings(game,4):
            if relevant(s): vals.append(s)
        for s in sorted(set(vals))[:700]: report.append(s[:1000])
    # phys exports/disassembly
    physroot=Path(a.phys) if a.phys else None
    if physroot and physroot.exists():
        report += ['','PHYSICS DLL EXPORTS / WEAR CONFIG']
        for p in sorted(list(physroot.rglob('*.dll'))):
            ex=exports(p)
            if not ex: continue
            report.append(f'FILE {p.name} sha256={sha256(p)}')
            for name,rva in ex:
                report.append(f'  {name} RVA=0x{rva:X}')
                if 'wear' in name.lower():
                    for ln in disasm(p,rva,60): report.append('    '+ln)
    (out/'woo24_tyre_wear_probe.txt').write_text('\n'.join(report),encoding='utf-8')
    print('\n'.join(report))

if __name__=='__main__': main()
