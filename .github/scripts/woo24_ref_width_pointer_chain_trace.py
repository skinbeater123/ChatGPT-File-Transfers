import sys,os,struct
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
def scanval(v,nbytes=8):
  pat=v.to_bytes(nbytes,'little'); a=[]; st=0
  while True:
    o=raw.find(pat,st)
    if o<0: break
    r=off2rva(o); a.append((o,r,base+r if r is not None else None)); st=o+1
  return a

targets={
 'front_base':0x180273720,
 'rear_base':0x180273660,
 'front_ref':0x1802737d8,
 'rear_ref':0x180273718,
}
allhits=[]
for n,v in targets.items():
  for kind,val,sz in [('va',v,8),('rva',v-base,4)]:
    hs=scanval(val,sz)
    print(n,kind,[(hex(o),hex(r) if r else None,hex(va) if va else None) for o,r,va in hs])
    for h in hs: allhits.append((n,kind,*h))

ins=[]
for s in pe.sections:
  if s.Characteristics & 0x20000000:
    code=raw[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]
    ins.extend(md.disasm(code,base+s.VirtualAddress))

cells={va:(n,k) for n,k,o,r,va in allhits if va}
refs=[]
for idx,i in enumerate(ins):
  for op in i.operands:
    tgt=None
    if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP: tgt=i.address+i.size+op.mem.disp
    elif op.type==X86_OP_IMM: tgt=op.imm
    if tgt in cells: refs.append((idx,i.address,tgt,*cells[tgt]))
print('cell refs',[(hex(a),hex(t),n,k) for _,a,t,n,k in refs])
with open(os.path.join(out,'pointer_chain_xrefs.txt'),'w') as f:
  for idx,a,t,n,k in refs:
    f.write(f'\n===== {n}/{k} cell {t:#x} xref {a:#x} =====\n')
    for q in ins[max(0,idx-100):idx+220]:
      f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')
