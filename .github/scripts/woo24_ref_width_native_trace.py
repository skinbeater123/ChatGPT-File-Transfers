import sys, os, json, struct
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64
from capstone.x86 import X86_OP_MEM, X86_OP_IMM, X86_REG_RIP

path=sys.argv[1]; outdir=sys.argv[2]
pe=pefile.PE(path, fast_load=False)
base=pe.OPTIONAL_HEADER.ImageBase
raw=open(path,'rb').read()

def off_to_rva(off):
    for s in pe.sections:
        lo=s.PointerToRawData; hi=lo+s.SizeOfRawData
        if lo <= off < hi:
            return s.VirtualAddress + off-lo
    return None

def rva_to_off(rva):
    try:return pe.get_offset_from_rva(rva)
    except:return None

def sec_for_rva(rva):
    for s in pe.sections:
        lo=s.VirtualAddress; hi=lo+max(s.Misc_VirtualSize,s.SizeOfRawData)
        if lo<=rva<hi:return s
    return None

terms=[b'ref_width',b'frict_load1',b'frict_k1',b'frict_load2',b'frict_k2',b'stiff_load1',b'stiff_c1',b'stiff_load2',b'stiff_c2',b'camber_stiff',b'camber_grip',b'camber_peak',b'long_stiff',b'long_frict',b'magic_b',b'magic_c',b'magic_d',b'magic_e',b'grip_fade_start',b'grip_fade_stop',b'grip_fade']
strings=[]
for t in terms:
    start=0
    while True:
        o=raw.find(t,start)
        if o<0:break
        r=off_to_rva(o)
        strings.append({'term':t.decode(),'file_off':o,'rva':r,'va':base+r if r is not None else None})
        start=o+1
open(os.path.join(outdir,'string_locations.json'),'w').write(json.dumps(strings,indent=2))

md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
insns=[]
for s in pe.sections:
    if not (s.Characteristics & 0x20000000): continue
    code=raw[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]
    va=base+s.VirtualAddress
    insns.extend(md.disasm(code,va))

str_by_va={x['va']:x['term'] for x in strings if x['va'] is not None}
refs=[]
for idx,ins in enumerate(insns):
    for op in ins.operands:
        tgt=None
        if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
            tgt=ins.address+ins.size+op.mem.disp
        elif op.type==X86_OP_IMM:
            tgt=op.imm
        if tgt in str_by_va:
            refs.append((idx,ins.address,tgt,str_by_va[tgt]))

with open(os.path.join(outdir,'string_xrefs.txt'),'w') as f:
    for idx,addr,tgt,term in refs:
        f.write(f'\n=== {term} string VA {tgt:#x} xref insn {addr:#x} ===\n')
        for j in range(max(0,idx-35),min(len(insns),idx+70)):
            q=insns[j]; mark='>>' if j==idx else '  '
            f.write(f'{mark} {q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')

def s_end_off(s): return s.PointerToRawData+s.SizeOfRawData
def decode_window(center,before=0x500,after=0x900):
    start=max(base,center-before); off=rva_to_off(start-base)
    if off is None:return []
    sec=sec_for_rva(start-base)
    if sec is None:return []
    maxlen=min(before+after,s_end_off(sec)-off)
    return list(md.disasm(raw[off:off+maxlen],start))

uniq=[]; seen=set()
for _,addr,_,term in refs:
    bucket=addr//0x100
    if bucket in seen:continue
    seen.add(bucket); uniq.append((addr,term))
with open(os.path.join(outdir,'xref_windows.txt'),'w') as f:
    for addr,term in uniq:
        f.write(f'\n===== WINDOW around {term} xref {addr:#x} =====\n')
        for q in decode_window(addr):
            f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')

vals=[304.0,500.0,1/304.0,1/500.0,304/500,500/304,0.304,0.5]
const_hits=[]
for v in vals:
    pat=struct.pack('<f',v); st=0
    while True:
        o=raw.find(pat,st)
        if o<0:break
        r=off_to_rva(o)
        const_hits.append({'value':v,'file_off':o,'rva':r,'va':base+r if r is not None else None})
        st=o+1
open(os.path.join(outdir,'known_float_hits.json'),'w').write(json.dumps(const_hits,indent=2))

exports=[]
if hasattr(pe,'DIRECTORY_ENTRY_EXPORT'):
    for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        exports.append({'name':e.name.decode(errors='replace') if e.name else None,'ordinal':e.ordinal,'rva':e.address,'va':base+e.address})
open(os.path.join(outdir,'exports.json'),'w').write(json.dumps(exports,indent=2))

print('image_base',hex(base),'machine',hex(pe.FILE_HEADER.Machine),'strings',len(strings),'xrefs',len(refs),'exports',len(exports))
for _,a,t,n in refs: print(hex(a),n,'->',hex(t))
