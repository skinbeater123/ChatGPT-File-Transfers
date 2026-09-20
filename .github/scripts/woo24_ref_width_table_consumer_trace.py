import sys,os,struct,json
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM,X86_OP_IMM,X86_REG_RIP

p=sys.argv[1]; out=sys.argv[2]
pe=pefile.PE(p); raw=open(p,'rb').read(); base=pe.OPTIONAL_HEADER.ImageBase
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True

def off2rva(o):
    for s in pe.sections:
        if s.PointerToRawData<=o<s.PointerToRawData+s.SizeOfRawData:
            return s.VirtualAddress+o-s.PointerToRawData
def rva2off(r):
    try:return pe.get_offset_from_rva(r)
    except:return None
def disasm_rva(rva,n):
    o=rva2off(rva)
    if o is None:return []
    return list(md.disasm(raw[o:o+n],base+rva))

# exact known string
so=raw.find(b'ref_width\x00')
srva=off2rva(so); sva=base+srva
print('ref_width',hex(so),hex(srva),hex(sva))
# all qword/dword pointers to string VA/RVA
hits=[]
for label,pat in [('va64',struct.pack('<Q',sva)),('rva32',struct.pack('<I',srva))]:
    st=0
    while True:
        o=raw.find(pat,st)
        if o<0: break
        r=off2rva(o)
        hits.append((label,o,r,base+r if r else None))
        st=o+1
open(os.path.join(out,'ref_width_pointer_hits.txt'),'w').write('\n'.join(map(str,hits)))
print('pointer hits',hits)

# dump around pointer hits
with open(os.path.join(out,'ref_width_pointer_context.hex.txt'),'w') as f:
    for h in hits:
        _,o,r,va=h
        lo=max(0,o-0x100); hi=min(len(raw),o+0x180)
        f.write(f'\n=== {h} ===\n')
        for x in range(lo,hi,16):
            b=raw[x:x+16]
            f.write(f'{x:08x}  '+b.hex(' ')+'  '+''.join(chr(c) if 32<=c<127 else '.' for c in b)+'\n')

# dump known config parser and front/rear setter regions
regions=[('parser_38d40',0x38800,0x1000),('front_setter',0x3b900,0x900),('rear_setter',0x3bc00,0x900),('wheel_setter',0x3b600,0x900)]
with open(os.path.join(out,'target_disasm.txt'),'w') as f:
    for name,rva,n in regions:
        f.write(f'\n===== {name} RVA {rva:#x} =====\n')
        for i in disasm_rva(rva,n):
            f.write(f'{i.address:#018x}: {i.mnemonic:8s} {i.op_str}\n')

# Decode all executable instructions and find RIP refs to pointer-hit VAs, and references to pointer table neighbors.
ins=[]
for s in pe.sections:
    if s.Characteristics & 0x20000000:
        code=raw[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]
        ins.extend(md.disasm(code,base+s.VirtualAddress))
ph_vas={h[3] for h in hits if h[3]}
refs=[]
for idx,i in enumerate(ins):
    for op in i.operands:
        tgt=None
        if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP: tgt=i.address+i.size+op.mem.disp
        elif op.type==X86_OP_IMM: tgt=op.imm
        if tgt in ph_vas:
            refs.append((idx,i.address,tgt))
with open(os.path.join(out,'pointer_xrefs.txt'),'w') as f:
    for idx,a,t in refs:
        f.write(f'\n=== xref {a:#x} -> {t:#x} ===\n')
        for q in ins[max(0,idx-50):idx+100]:
            f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')
print('code refs to pointer hit',[(hex(a),hex(t)) for _,a,t in refs])

# collect memory displacement histogram in likely tyre-force compute region entire text, highlight plausible small struct offsets
from collections import Counter
cnt=Counter(); examples={}
for i in ins:
    for op in i.operands:
        if op.type==X86_OP_MEM and op.mem.base not in (0,X86_REG_RIP):
            d=op.mem.disp
            if 0<=d<=0x800:
                cnt[d]+=1; examples.setdefault(d,[]).append((i.address,i.mnemonic,i.op_str))
with open(os.path.join(out,'mem_disp_histogram.txt'),'w') as f:
    for d,c in cnt.most_common():
        f.write(f'{d:#x} {c}\n')
        for e in examples[d][:5]: f.write('  '+repr(e)+'\n')
