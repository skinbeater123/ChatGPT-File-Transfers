import sys,os
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM,X86_REG_RIP

p=sys.argv[1]; out=sys.argv[2]
pe=pefile.PE(p); raw=open(p,'rb').read(); base=pe.OPTIONAL_HEADER.ImageBase
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
ins=[]
for s in pe.sections:
  if s.Characteristics & 0x20000000:
    code=raw[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]
    ins.extend(md.disasm(code,base+s.VirtualAddress))

# Find each non-RIP memory access at +0xb8 and score neighborhood for same base register
# touching offsets characteristic of AxleConfig tail.
wanted=set(range(0x50,0xbc,4))
cands=[]
for idx,i in enumerate(ins):
  for op in i.operands:
    if op.type!=X86_OP_MEM or op.mem.base in (0,X86_REG_RIP) or op.mem.disp!=0xb8: continue
    br=op.mem.base
    touched=[]
    for q in ins[max(0,idx-120):min(len(ins),idx+180)]:
      for o in q.operands:
        if o.type==X86_OP_MEM and o.mem.base==br and 0<=o.mem.disp<=0x140:
          touched.append((q.address,o.mem.disp,q.mnemonic,q.op_str))
    offs=sorted(set(x[1] for x in touched))
    score=sum(1 for x in offs if x in wanted)
    cands.append((score,idx,i.address,br,offs,touched))
cands.sort(reverse=True,key=lambda x:x[0])
print('candidate count',len(cands))
for rank,c in enumerate(cands[:40],1):
  score,idx,a,br,offs,touched=c
  print(rank,hex(a),'baseReg',br,'score',score,'offs',[hex(x) for x in offs])

with open(os.path.join(out,'ranked_b8_candidates.txt'),'w') as f:
  for rank,c in enumerate(cands[:20],1):
    score,idx,a,br,offs,touched=c
    f.write(f'\n===== rank {rank} addr {a:#x} baseReg {br} score {score} offs {[hex(x) for x in offs]} =====\n')
    for q in ins[max(0,idx-140):min(len(ins),idx+220)]:
      f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')
