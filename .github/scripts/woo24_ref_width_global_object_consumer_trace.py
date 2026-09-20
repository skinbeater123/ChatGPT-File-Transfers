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
slot=0x18026c698
refs=[]
for idx,i in enumerate(ins):
  for op in i.operands:
    if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
      tgt=i.address+i.size+op.mem.disp
      if tgt==slot: refs.append((idx,i.address,i.mnemonic,i.op_str))
print('global slot',hex(slot),'refs',len(refs))
for x in refs: print(hex(x[1]),x[2],x[3])
with open(os.path.join(out,'global_object_slot_xrefs.txt'),'w') as f:
  for idx,a,m,o in refs:
    f.write(f'\n===== slot xref {a:#x} {m} {o} =====\n')
    for q in ins[max(0,idx-100):min(len(ins),idx+260)]:
      f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')

# For each xref, track destination register of mov reg,[rip+slot] within next 120 instructions.
# Then report memory accesses based on that reg, especially +0x64.
with open(os.path.join(out,'tracked_slot_consumers.txt'),'w') as f:
  for idx,a,m,o in refs:
    i=ins[idx]
    # capstone operand 0 register for mov
    if i.mnemonic not in ('mov','lea') or len(i.operands)<2 or i.operands[0].type!=1: continue
    reg=i.operands[0].reg
    f.write(f'\n===== LOAD {a:#x} into reg {reg} =====\n')
    for q in ins[idx:min(len(ins),idx+180)]:
      hit=[]
      for op in q.operands:
        if op.type==X86_OP_MEM and op.mem.base==reg:
          hit.append(op.mem.disp)
      if hit:
        f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}   OFFS={",".join(hex(x) for x in hit)}\n')

# Look for references to the qword slot as a literal pointer in data.
import struct
pat=struct.pack('<Q',slot); st=0; dh=[]
while True:
  o=raw.find(pat,st)
  if o<0: break
  # map
  r=None
  for s in pe.sections:
    if s.PointerToRawData<=o<s.PointerToRawData+s.SizeOfRawData:
      r=s.VirtualAddress+o-s.PointerToRawData; break
  dh.append((o,r,base+r if r is not None else None)); st=o+1
print('data qword refs',[(hex(o),hex(r) if r else None,hex(v) if v else None) for o,r,v in dh])
