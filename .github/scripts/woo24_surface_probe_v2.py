#!/usr/bin/env python3
import argparse, re, struct
from bisect import bisect_right
from pathlib import Path

FOCUS_TYPE_TERMS = ('track','terrain','surface','dirt','wear','grip','tearoff','tear_off','mud','dust','spline','decal','dynamic')
EXACT_TYPE_SUFFIXES = (
    'MGIOptionsHub.Configuration','MGIOptionsHub.FriendlyGameOptions','MGIOptionsHub.NativeGameOptions','MGIOptionsHub',
    'TrackSettingsConfig','TrackSettingsConfig.DirtAccumulationSetting','TrackSettingsConfig.DirtAccumulationSettingInfo',
    'MGIGameMaster','TrackPhysicsAsset','TrackPhysicsAsset.TrackSpline','PhysType.TrackTerrainProperties','PhysType.TerrainProperties',
    'PhysDLL','TearOffManager','JimSingleTrackWearAlphaSelector','JimSingleTrackWearAlpha','SettingsAddenda.WoO24Patch1Data',
    'TrackSettings.TrackSettingsManagerSaveable','MGI.GameState.TrackSettingsDefaults','NextChassis.PhysWheelAsset',
)
TARGET_NAMES = {
    'getisdynamictrackenabled','getdirtaccumulationsetting','makenativegameoptions','startup',
    'push_track_terrain_properties_to_dll','push_track_terrain_property_to_dll','ilresaddtrackterrainproperties',
    'construct','getdirtaccumulationfactor','getdirtaccumulationsettinginfo','getavailabledirtaccumulationsettings',
    'getstagetypeindex','update_track_materials','update','pushconfigtodll','export','.cctor','.ctor','reset'
}
DISPS = {0x10,0x18,0x20,0x38,0x44,0x5c,0x60,0x88,0x8c,0x90,0x94}

def parse_types(text):
    out=[]
    for part in re.split(r'(?=// Namespace: )', text):
        if not part.startswith('// Namespace: '): continue
        lines=part.splitlines(); ns=lines[0][len('// Namespace: '):].strip(); name=None; decl=''
        for line in lines[1:40]:
            m=re.search(r'\b(class|struct|enum|interface)\s+([^\s:{]+)', line)
            if m: name=m.group(2); decl=line.strip(); break
        if not name: continue
        idx=re.search(r'// TypeDefIndex:\s*(\d+)', part)
        out.append({'namespace':ns,'name':name,'decl':decl,'typedef':int(idx.group(1)) if idx else None,'block':part})
    return out

def parse_methods(types):
    out=[]
    for t in types:
        pending=None
        for i,line in enumerate(t['block'].splitlines()):
            m=re.search(r'// RVA:\s*0x([0-9A-Fa-f]+)\s+Offset:\s*0x([0-9A-Fa-f]+)\s+VA:\s*0x([0-9A-Fa-f]+)',line)
            if m:
                pending=(int(m.group(1),16),int(m.group(2),16),int(m.group(3),16),i); continue
            if pending and '(' in line and ')' in line and not line.strip().startswith('//'):
                decl=line.strip(); before=decl.split('(',1)[0].strip(); name=before.split()[-1] if before else '?'
                out.append({'namespace':t['namespace'],'type':t['name'],'name':name,'decl':decl,
                            'rva':pending[0],'offset':pending[1],'va':pending[2]}); pending=None
            elif pending and i-pending[3]>8: pending=None
    out.sort(key=lambda x:(x['rva'],x['namespace'],x['type'],x['name']))
    return out

def fulltype(x): return (x['namespace']+'.'+x['name']).strip('.')
def fullmethod(m): return ((m['namespace']+'.') if m['namespace'] else '')+m['type']+'::'+m['name']

def is_exact_type(t):
    f=fulltype(t)
    return any(f.endswith(s) or t['name'].endswith(s) for s in EXACT_TYPE_SUFFIXES)

def target_method(m):
    ft=((m['namespace']+'.') if m['namespace'] else '')+m['type']
    n=m['name'].lower(); low=(ft+' '+m['decl']).lower()
    if n not in TARGET_NAMES: return False
    return any(k in low for k in ('mgioptionshub','tracksettingsconfig','mgigamemaster','trackphysicsasset','trackterrainproperties','physdll','tearoff','jimsingletrackwear','physwheelasset','woo24patch1'))

def method_ranges(methods):
    by={}
    for m in methods: by.setdefault(m['rva'],m)
    uniq=sorted(by.values(),key=lambda x:x['rva'])
    for i,m in enumerate(uniq):
        end=uniq[i+1]['rva'] if i+1<len(uniq) else m['rva']+0x400
        m['_end']=end
    return uniq

def disasm_method(pe, m, max_ins=500):
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    size=max(16,min(m.get('_end',m['rva']+0x800)-m['rva'],0x5000))
    data=pe.get_data(m['rva'],size); md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
    return list(md.disasm(data,pe.OPTIONAL_HEADER.ImageBase+m['rva']))[:max_ins]

def fmt(ins): return f'0x{ins.address:X}: {ins.mnemonic} {ins.op_str}'.rstrip()

def find_direct_calls(pe, targets, methods):
    base=pe.OPTIONAL_HEADER.ImageBase
    target_vas={m['va']:m for m in targets}
    out={va:[] for va in target_vas}
    uniq=method_ranges(methods); starts=[m['rva'] for m in uniq]
    def locate(rva):
        i=bisect_right(starts,rva)-1
        return uniq[i] if i>=0 and rva < uniq[i].get('_end',uniq[i]['rva']+0x400) else None
    for sec in pe.sections:
        if not (sec.Characteristics & 0x20000000): continue
        data=sec.get_data(); srva=sec.VirtualAddress; pos=0
        while True:
            i=data.find(b'\xE8',pos)
            if i<0 or i+5>len(data): break
            rel=struct.unpack_from('<i',data,i+1)[0]
            iva=base+srva+i; tv=iva+5+rel
            if tv in out: out[tv].append((srva+i,locate(srva+i)))
            pos=i+1
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--dump',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    root=Path(a.root); dd=Path(a.dump); od=Path(a.out); od.mkdir(parents=True,exist_ok=True)
    text=(dd/'dump.cs').read_text(encoding='utf-8',errors='replace'); types=parse_types(text); methods=parse_methods(types)
    game=next(root.rglob('GameAssembly.dll'))
    import pefile
    pe=pefile.PE(str(game),fast_load=False)
    uniq=method_ranges(methods)
    r=['WOO24 MODERN COMPARATIVE DIRECT — SURFACE TRACE V2','='*86,
       'Scope: close dynamic toggle/material gate; dirt-accumulation semantics; 256-sample terrain record; startup/native physics path','']

    r.append('A. EXACT CONFIG / SURFACE TYPE DEFINITIONS')
    for t in types:
        if is_exact_type(t):
            r.append(f'\n===== {fulltype(t)} TypeDef={t["typedef"]} =====')
            bl=t['block'].splitlines()
            if t['name'].endswith('PhysDLL') and len(bl)>600:
                for ln in bl:
                    if any(k in ln.lower() for k in ('track','terrain','surface','grip','wear','dirt')): r.append(ln)
            else: r.extend(bl[:900])

    r.append('\nB. SURFACE-SEMANTIC TYPE / METHOD NAME CENSUS')
    for t in types:
        f=fulltype(t); low=f.lower()
        if any(k in low for k in FOCUS_TYPE_TERMS): r.append(f'TYPE {f} TypeDef={t["typedef"]}')
    r.append('\n-- methods --')
    for m in methods:
        low=(fullmethod(m)+' '+m['decl']).lower()
        if any(k in low for k in ('dynamictrack','dirtaccum','trackterrain','trackwear','terrainpropert','surfacegrip','trackgrip','tearoff','mud','marble','slick','groove','cushion','moisture')):
            r.append(f'RVA=0x{m["rva"]:X} {fullmethod(m)} -- {m["decl"]}')

    targets=[m for m in uniq if target_method(m)]
    r.append('\nC. TARGETED DIRECT CALLERS')
    refs=find_direct_calls(pe,targets,methods)
    for m in targets:
        rr=refs.get(m['va'],[])
        r.append(f'\nTARGET RVA=0x{m["rva"]:X} {fullmethod(m)} xrefs={len(rr)}')
        for crva,caller in rr[:100]: r.append(f'  call@RVA=0x{crva:X} caller={fullmethod(caller) if caller else "UNKNOWN"}')

    r.append('\nD. TARGETED METHOD DISASSEMBLY')
    emitted=set()
    for m in targets:
        key=(m['rva'],fullmethod(m))
        if key in emitted: continue
        emitted.add(key)
        if m['name'] in ('.ctor','.cctor'):
            low=fullmethod(m).lower()
            if not any(x in low for x in ('tracksettingsconfig','dirtaccumulationsettinginfo','trackterrainproperties','woo24patch1')): continue
        r.append(f'\n--- RVA=0x{m["rva"]:X} {fullmethod(m)} ---\n{m["decl"]}')
        try:
            for ins in disasm_method(pe,m,650): r.append(fmt(ins))
        except Exception as e: r.append(f'DISASM ERROR {e!r}')

    r.append('\nE. OFFSET SIGNATURE SCAN FOR FRIENDLY GAME OPTIONS (+88/+8C/+90/+94)')
    sig={0x88,0x8c,0x90,0x94}
    from capstone.x86_const import X86_OP_MEM
    hits=[]
    for m in uniq:
        size=m.get('_end',m['rva']+0x100)-m['rva']
        if size<=0 or size>0x5000: continue
        try: insns=disasm_method(pe,m,900)
        except Exception: continue
        ds=set()
        for ins in insns:
            for op in ins.operands:
                if op.type==X86_OP_MEM and op.mem.disp in sig: ds.add(op.mem.disp)
        if len(ds)>=3: hits.append((m,ds,insns))
    for m,ds,insns in hits[:120]:
        r.append(f'\nMETHOD RVA=0x{m["rva"]:X} {fullmethod(m)} offsets={",".join(hex(x) for x in sorted(ds))}')
        for ins in insns:
            show=False
            for op in ins.operands:
                if op.type==X86_OP_MEM and op.mem.disp in sig: show=True
            if show: r.append('  '+fmt(ins))

    r.append('\nF. TERRAIN MARSHAL SIZE CHECK')
    r.append('Observed wrapper stack marshal size searched: 0x40C = 1036 = 12-byte TerrainProperties + 256*4-byte samples.')
    for m in uniq:
        if m['rva'] in (0x28EEC0,0x3C09B0,0x2A0300,0x28EA60,0x28ADB0):
            r.append(f'\n{fullmethod(m)} RVA=0x{m["rva"]:X}')
            for ins in disasm_method(pe,m,700):
                if '0x40c' in ins.op_str.lower() or '0x100' in ins.op_str.lower() or m['rva'] in (0x3C09B0,0x28EA60): r.append(fmt(ins))

    out=od/'surface_trace_v2.txt'; out.write_text('\n'.join(r)+'\n',encoding='utf-8')
    print('\n'.join(r))

if __name__=='__main__': main()
