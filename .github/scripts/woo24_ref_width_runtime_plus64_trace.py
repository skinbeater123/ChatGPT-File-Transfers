import sys,os
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM,X86_OP_IMM,X86_REG_RIP

p=sys.argv[1]; out=sys.argv[2]
pe=pefile.PE(p); raw=open(p,'rb').read(); base=pe.OPTIONAL_HEADER.ImageBase
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True

ins=[]
for s in pe.sections:
    if s.Characteristics & 0x20000000:
        code=raw[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]
        ins.extend(md.disasm(code,base+s.VirtualAddress))
addr_to_idx={i.address:n for n,i in enumerate(ins)}
target=base+0x2b30

# Direct calls/jumps to converter
callers=[]
for idx,i in enumerate(ins):
    for op in i.operands:
        if op.type==X86_OP_IMM and op.imm==target and i.mnemonic.startswith(('call','jmp')):
            callers.append((idx,i.address,i.mnemonic,i.op_str))
print('converter',hex(target),'direct callers',[(hex(a),m,o) for _,a,m,o in callers])
with open(os.path.join(out,'converter_callers.txt'),'w') as f:
    for idx,a,m,o in callers:
        f.write(f'\n===== CALLER SITE {a:#x} {m} {o} =====\n')
        for q in ins[max(0,idx-180):min(len(ins),idx+260)]:
            f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')

# Rank every +0x64 use by neighborhood evidence of same object base touching
# fields populated by converter. Runtime translated tail includes offsets:
# 0x08,0x0c,... through ~0x7c; exact ref_width = 0x64.
mapped=set(range(0x08,0x80,4))
runtime64=[]
for idx,i in enumerate(ins):
    for op in i.operands:
        if op.type!=X86_OP_MEM or op.mem.base in (0,X86_REG_RIP) or op.mem.disp!=0x64:
            continue
        br=op.mem.base
        touched=[]
        for q in ins[max(0,idx-100):min(len(ins),idx+160)]:
            for o in q.operands:
                if o.type==X86_OP_MEM and o.mem.base==br and -0x20<=o.mem.disp<=0x180:
                    touched.append((q.address,o.mem.disp,q.mnemonic,q.op_str))
        offs=sorted(set(x[1] for x in touched))
        score=sum(1 for x in offs if x in mapped)
        runtime64.append((score,idx,i.address,br,offs))
runtime64.sort(reverse=True,key=lambda x:x[0])
print('plus64 uses',len(runtime64))
for rank,(score,idx,a,br,offs) in enumerate(runtime64[:60],1):
    print(rank,hex(a),'score',score,'baseReg',br,'offs',[hex(x) for x in offs])

with open(os.path.join(out,'runtime_plus64_ranked.txt'),'w') as f:
    for rank,(score,idx,a,br,offs) in enumerate(runtime64[:30],1):
        f.write(f'\n===== RANK {rank} addr {a:#x} score {score} baseReg {br} offs {[hex(x) for x in offs]} =====\n')
        for q in ins[max(0,idx-150):min(len(ins),idx+260)]:
            f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')

# function-boundary heuristic: look backward to common prologue/alignment after RET.
def approx_start(idx):
    for j in range(idx-1,max(-1,idx-500),-1):
        if ins[j].mnemonic in ('ret','int3'):
            k=j+1
            while k<idx and ins[k].mnemonic=='int3': k+=1
            return ins[k].address if k<idx else ins[idx].address
    return ins[max(0,idx-500)].address

summary=[]
for score,idx,a,br,offs in runtime64:
    summary.append((a,approx_start(idx),score,br,offs))
with open(os.path.join(out,'runtime_plus64_summary.txt'),'w') as f:
    for a,st,sc,br,offs in summary:
        f.write(f'use={a:#x} approx_fn={st:#x} score={sc} baseReg={br} offs={",".join(hex(x) for x in offs)}\n')

# Export nearest below candidates for contextual naming.
exports=[]
if hasattr(pe,'DIRECTORY_ENTRY_EXPORT'):
    for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        if e.name:
            exports.append((base+e.address,e.name.decode(errors='replace')))
exports.sort()
with open(os.path.join(out,'candidate_nearest_exports.txt'),'w') as f:
    for score,idx,a,br,offs in runtime64[:60]:
        prev=[x for x in exports if x[0]<=a]
        nxt=[x for x in exports if x[0]>a]
        f.write(f'{a:#x} score={score} prev={prev[-1] if prev else None} next={nxt[0] if nxt else None}\n')
