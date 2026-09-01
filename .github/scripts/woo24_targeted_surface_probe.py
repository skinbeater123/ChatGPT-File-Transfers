#!/usr/bin/env python3
import argparse, re, struct
from bisect import bisect_right
from pathlib import Path

EXACT_TYPES = {
    'JimTrackWearSettings','JimTrackWearSettingsData','JimSingleTrackWearAlpha',
    'JimSingleTrackWearAlphaSelector','MGIOptionsHub','NativeGameOptions','GameOptions',
    'TrackPhysicsAsset','TrackTerrainProperties','TerrainProperties','MGIGameMaster','PhysDLL',
    'TrackExtrusion','TrackRacingLineFloater','ChassisTrackData','PhysWheelTrackData'
}
TYPE_FRAGMENTS = ('TrackPhysicsAsset.TrackSpline','DirtAccumulationSetting','DirtAccumulationSettingInfo',
                  'TrackSettingsManagerSaveable','TrackSettingsDefaults')
TERMS = ['dynamicTrack','dirtAccumulation','TrackWear','TrackTerrainProperties','racetrack_terrain',
         'grip_factor','GetIsDynamicTrackEnabled','dynamic_track','groove','slick','cushion','marble',
         'moisture','water','loose','compaction','rubber']


def parse_types(text):
    out=[]
    for part in re.split(r'(?=// Namespace: )', text):
        if not part.startswith('// Namespace: '): continue
        lines=part.splitlines(); ns=lines[0][len('// Namespace: '):].strip(); name=None; decl=''
        for line in lines[1:35]:
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
    out.sort(key=lambda x:(x['rva'],x['type'],x['name']))
    return out


def selected_type(t):
    simple=t['name'].split('.')[-1]
    full=(t['namespace']+'.'+t['name']) if t['namespace'] else t['name']
    return simple in EXACT_TYPES or t['name'] in EXACT_TYPES or any(f.lower() in full.lower() for f in TYPE_FRAGMENTS)


def selected_method(m):
    typ=m['type'].lower(); n=m['name'].lower(); d=m['decl'].lower()
    if 'mgioptionshub' in typ and ('dynamic' in n or 'dirtaccum' in n or 'track' in n): return True
    if 'options_adjustsettings' in typ and n in ('set_dynamic_track','set_dirt_accumulation'): return True
    if 'mgigamemaster' in typ and 'track_terrain' in n: return True
    if typ.endswith('physdll') and ('trackterrain' in n or 'terrain' in n and 'track' in n): return True
    if 'jimsingletrackwear' in typ and n in ('update_track_materials','getstagetypeindex','update','startit','setracetrackwearsettings','getracetrackwearsettings','graduateracetrackwearoriginalsettings'): return True
    if 'nativegameoptions' in typ and any(x in (n+' '+d) for x in ('dynamic','dirt','track','wear')): return True
    if 'tracksettings' in typ and any(x in (n+' '+d) for x in ('dynamic','dirtaccum','trackwear')): return True
    if 'physwheelasset' in typ and n in ('pushconfigtodll','export'): return True
    return False


def build_method_locator(methods):
    by_rva={}
    for m in methods: by_rva.setdefault(m['rva'],m)
    uniq=sorted(by_rva.values(), key=lambda x:x['rva']); starts=[m['rva'] for m in uniq]
    def locate(rva):
        i=bisect_right(starts,rva)-1
        if i<0: return None
        m=uniq[i]
        return m if rva-m['rva']<=0x20000 else None
    return uniq,starts,locate


def xrefs(game, methods, targets):
    import pefile
    pe=pefile.PE(str(game),fast_load=False); base=pe.OPTIONAL_HEADER.ImageBase
    sec=next(s for s in pe.sections if s.Name.rstrip(b'\0')==b'.text'); data=sec.get_data(); srva=sec.VirtualAddress
    target_vas={m['va'] for m in targets}; out={va:[] for va in target_vas}; _,_,locate=build_method_locator(methods)
    for i in range(len(data)-5):
        if data[i]!=0xE8: continue
        rel=struct.unpack_from('<i',data,i+1)[0]; iva=base+srva+i; target=iva+5+rel
        if target in out:
            crva=srva+i; out[target].append((crva,iva,locate(crva)))
    return out


def disasm(game, rva, size):
    import pefile
    from capstone import Cs,CS_ARCH_X86,CS_MODE_64
    pe=pefile.PE(str(game),fast_load=False); base=pe.OPTIONAL_HEADER.ImageBase; data=pe.get_data(rva,min(size,4096))
    md=Cs(CS_ARCH_X86,CS_MODE_64); out=[]
    for ins in md.disasm(data,base+rva):
        out.append(f'0x{ins.address:X}: {ins.mnemonic} {ins.op_str}'.rstrip())
        if len(out)>=320: break
    return out


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--dump',required=True); ap.add_argument('--out',required=True); a=ap.parse_args()
    root=Path(a.root); dd=Path(a.dump); od=Path(a.out); od.mkdir(parents=True,exist_ok=True)
    text=(dd/'dump.cs').read_text(encoding='utf-8',errors='replace'); lines=text.splitlines(); types=parse_types(text); methods=parse_methods(types); game=next(root.rglob('GameAssembly.dll'))
    r=['WOO24 MODERN COMPARATIVE DIRECT — TARGETED SURFACE RUNTIME TRACE','='*78,
       'Scope: dynamic-track toggle -> runtime reader; dirt accumulation; track-wear stages; spatial terrain/grip; native consumers','']

    r.append('A. REQUESTED TOKEN CENSUS')
    for term in TERMS: r.append(f'{term}: {len(re.findall(re.escape(term),text,flags=re.I))}')

    r.append('\nB. EXACT TERM CONTEXT')
    lowterms=[t.lower() for t in TERMS]
    emitted={t:0 for t in TERMS}
    for i,line in enumerate(lines):
        ll=line.lower()
        for term,lt in zip(TERMS,lowterms):
            if emitted[term]<10 and lt in ll:
                lo=max(0,i-5); hi=min(len(lines),i+6); r.append(f'\n--- {term} around dump.cs line {i+1} ---'); r.extend(lines[lo:hi]); emitted[term]+=1

    r.append('\nC. HIGH-SIGNAL TYPE DEFINITIONS')
    for t in types:
        if selected_type(t):
            full=(t['namespace']+'.'+t['name']) if t['namespace'] else t['name']; r.append(f'\n===== {full} TypeDef={t["typedef"]} =====')
            bl=t['block'].splitlines()
            if len(bl)<=500: r.extend(bl)
            else:
                r.append(t['decl'])
                for line in bl:
                    ll=line.lower()
                    if any(x in ll for x in ('dynamic','dirt','terrain','trackwear','grip','surface','racingline','wear','physics','stage','session')): r.append(line)

    targets=[m for m in methods if selected_method(m)]
    # dedupe exact method identity
    seen=set(); targets=[m for m in targets if not ((m['rva'],m['type'],m['name']) in seen or seen.add((m['rva'],m['type'],m['name'])))]
    r.append('\nD. TARGET METHOD MAP')
    for m in targets: r.append(f'RVA=0x{m["rva"]:X} VA=0x{m["va"]:X} {m["namespace"]}.{m["type"]}::{m["name"]} -- {m["decl"]}')

    refs=xrefs(game,methods,targets)
    r.append('\nE. DIRECT CALL XREFS')
    for m in targets:
        rr=refs.get(m['va'],[]); r.append(f'\nTARGET {m["namespace"]}.{m["type"]}::{m["name"]} RVA=0x{m["rva"]:X} xrefs={len(rr)}')
        for crva,cva,caller in rr[:80]:
            if caller: r.append(f'  call RVA=0x{crva:X} caller={caller["namespace"]}.{caller["type"]}::{caller["name"]} callerRVA=0x{caller["rva"]:X}')
            else: r.append(f'  call RVA=0x{crva:X} caller=UNKNOWN')

    uniq,starts,_=build_method_locator(methods); rvaseq=[m['rva'] for m in uniq]
    r.append('\nF. BOUNDED TARGET DISASSEMBLY')
    dis_names={'getisdynamictrackenabled','set_dynamic_track','set_dirt_accumulation','push_track_terrain_property_to_dll','ilresaddtrackterrainproperties','update_track_materials','getstagetypeindex','graduateracetrackwearoriginalsettings'}
    for m in targets:
        if m['name'].lower() not in dis_names: continue
        i=bisect_right(rvaseq,m['rva']); end=rvaseq[i] if i<len(rvaseq) else m['rva']+1024; size=max(32,end-m['rva'])
        r.append(f'\n--- {m["namespace"]}.{m["type"]}::{m["name"]} RVA=0x{m["rva"]:X} ---'); r.append(m['decl']); r.extend(disasm(game,m['rva'],size))

    out=od/'targeted_surface_trace.txt'; out.write_text('\n'.join(r)+'\n',encoding='utf-8'); print('\n'.join(r))

if __name__=='__main__': main()
