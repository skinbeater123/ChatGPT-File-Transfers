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
idx={i.address:n for n,i in enumerate(ins)}

def approx_fn_start(iidx):
  for j in range(iidx-1,max(-1,iidx-800),-1):
    if ins[j].mnemonic in ('ret','int3'):
      k=j+1
      while k<iidx and ins[k].mnemonic=='int3':k+=1
      return ins[k].address
  return ins[max(0,iidx-800)].address

# Gather direct call graph from PhysicsCreateCar for depth 3
root=base+0x956a0
queue=[(root,0)]; seen=set(); functions=[]
while queue:
  a,d=queue.pop(0)
  if a in seen or d>3 or a not in idx: continue
  seen.add(a)
  start=approx_fn_start(idx[a]); si=idx.get(start,idx[a])
  # walk until ret then allow at most 3000 ins
  body=[]
  for k in range(si,min(len(ins),si+3000)):
    q=ins[k]; body.append(q)
    if q.mnemonic=='ret' and k>si+2:break
  functions.append((a,start,d,body))
  for q in body:
    if q.mnemonic=='call':
      for op in q.operands:
        if op.type==X86_OP_IMM and base<=op.imm<base+pe.OPTIONAL_HEADER.SizeOfImage:
          if op.imm in idx: queue.append((op.imm,d+1))

with open(os.path.join(out,'createcar_callgraph.txt'),'w') as f:
  for a,start,d,body in functions:
    f.write(f'\n===== depth={d} entry={a:#x} approx_start={start:#x} =====\n')
    for q in body:
      tags=[]
      for op in q.operands:
        if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
          t=q.address+q.size+op.mem.disp
          if 0x180273000<=t<0x180274000: tags.append(f'CONFIG_NEAR={t:#x}')
      f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}' + (('  ; '+','.join(tags)) if tags else '')+'\n')

# Global scan for refs to 0x180273000..0x180274000 with exact target.
refs=[]
for n,q in enumerate(ins):
  for op in q.operands:
    if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
      t=q.address+q.size+op.mem.disp
      if 0x180273000<=t<0x180274000:
        refs.append((n,q.address,t,q.mnemonic,q.op_str,approx_fn_start(n)))
print('config-neighborhood refs',len(refs))
for _,a,t,m,o,st in refs:
  print(hex(a),'->',hex(t),'fn',hex(st),m,o)
with open(os.path.join(out,'config_neighborhood_refs.txt'),'w') as f:
  for n,a,t,m,o,st in refs:
    f.write(f'\n===== {a:#x} -> {t:#x} fn={st:#x} =====\n')
    for q in ins[max(0,n-60):min(len(ins),n+120)]:
      f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')
