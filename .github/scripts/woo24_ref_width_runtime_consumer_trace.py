import sys,os
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM,X86_OP_IMM,X86_REG_RIP

p=sys.argv[1]; out=sys.argv[2]
pe=pefile.PE(p); raw=open(p,'rb').read(); base=pe.OPTIONAL_HEADER.ImageBase
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
targets={
 'front_ref_width':0x180273720+0xb8,
 'rear_ref_width':0x180273660+0xb8,
 'front_axle_cfg':0x180273720,
 'rear_axle_cfg':0x180273660,
}
ins=[]
for s in pe.sections:
    if s.Characteristics & 0x20000000:
        code=raw[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]
        ins.extend(md.disasm(code,base+s.VirtualAddress))
rev={v:k for k,v in targets.items()}
refs=[]
for idx,i in enumerate(ins):
    for op in i.operands:
        tgt=None
        if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
            tgt=i.address+i.size+op.mem.disp
        elif op.type==X86_OP_IMM:
            tgt=op.imm
        if tgt in rev:
            refs.append((idx,i.address,tgt,rev[tgt]))
print('targets', {k:hex(v) for k,v in targets.items()})
print('refs',[(hex(a),name,hex(t)) for _,a,t,name in refs])
with open(os.path.join(out,'global_ref_xrefs.txt'),'w') as f:
    for idx,a,t,name in refs:
        f.write(f'\n===== {name} xref {a:#x} -> {t:#x} =====\n')
        for q in ins[max(0,idx-100):min(len(ins),idx+220)]:
            f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')

# Also find code using RIP-relative addresses anywhere inside either axle config range.
ranges=[('rear',0x180273660,0x180273720),('front',0x180273720,0x1802737e0)]
rrefs=[]
for idx,i in enumerate(ins):
    for op in i.operands:
        if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
            t=i.address+i.size+op.mem.disp
            for name,lo,hi in ranges:
                if lo<=t<hi:
                    rrefs.append((idx,i.address,t,name,t-lo))
with open(os.path.join(out,'axle_block_rip_refs.txt'),'w') as f:
    for idx,a,t,name,off in rrefs:
        f.write(f'{a:#018x} {name}+{off:#x} -> {t:#x} : {ins[idx].mnemonic} {ins[idx].op_str}\n')
print('block refs',len(rrefs))
for _,a,t,n,o in rrefs: print(hex(a),n,hex(o),hex(t))
