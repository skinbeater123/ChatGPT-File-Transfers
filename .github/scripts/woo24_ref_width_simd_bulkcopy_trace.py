import sys,os
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_READ
from capstone.x86 import X86_OP_MEM,X86_REG_RIP
p=sys.argv[1]; out=sys.argv[2]
pe=pefile.PE(p); raw=open(p,'rb').read(); base=pe.OPTIONAL_HEADER.ImageBase
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
ins=[]
for s in pe.sections:
  if s.Characteristics & 0x20000000:
    code=raw[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]
    ins.extend(md.disasm(code,base+s.VirtualAddress))

# Candidate reads that cover translated ref_width byte range 0x64..0x67,
# including vector/qword loads beginning earlier.
c=[]
for idx,i in enumerate(ins):
  try: regs_read,regs_write=i.regs_access()
  except: regs_read=[];regs_write=[]
  for oi,op in enumerate(i.operands):
    if op.type!=X86_OP_MEM or op.mem.base in (0,X86_REG_RIP): continue
    d=op.mem.disp; sz=max(1,op.size)
    if d <= 0x64 and d+sz > 0x64:
      # infer read if mnemonic destination isn't this mem operand
      isread = oi!=0 or i.mnemonic in ('cmp','comiss','ucomiss','mulss','addss','subss','divss','minss','maxss','andps','orps','xorps','movups','movaps','movdqu','movdqa','movss','movsd')
      if isread:
        br=op.mem.base
        # scan nearby same-base memory offsets and access widths
        touches=[]
        for q in ins[max(0,idx-120):min(len(ins),idx+180)]:
          for qo,oo in enumerate(q.operands):
            if oo.type==X86_OP_MEM and oo.mem.base==br and 0<=oo.mem.disp<=0x140:
              touches.append((q.address,oo.mem.disp,oo.size,q.mnemonic,q.op_str))
        coverage=set()
        for _,dd,ss,_,_ in touches:
          for b in range(dd,dd+max(1,ss)):
            if 0<=b<0x140: coverage.add(b)
        score=sum(1 for b in range(0x08,0xb9) if b in coverage)
        c.append((score,idx,i.address,br,d,sz,touches))
c.sort(reverse=True,key=lambda x:x[0])
print('covering reads',len(c))
for rank,(score,idx,a,br,d,sz,t) in enumerate(c[:50],1):
  print(rank,hex(a),'disp',hex(d),'size',sz,'score',score,'ins',ins[idx].mnemonic,ins[idx].op_str)

with open(os.path.join(out,'covering_refwidth_reads.txt'),'w') as f:
  for rank,(score,idx,a,br,d,sz,t) in enumerate(c[:30],1):
    f.write(f'\n===== rank {rank} addr {a:#x} disp={d:#x} size={sz} score={score} baseReg={br} =====\n')
    for q in ins[max(0,idx-150):min(len(ins),idx+260)]:
      f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')

# Search immediate constants that look like translated struct sizes/copy lengths.
sizes=[0xb8,0xbc,0xc0,0x100,0x108,0x10c,0x118]
with open(os.path.join(out,'struct_size_immediates.txt'),'w') as f:
  for idx,i in enumerate(ins):
    vals=[op.imm for op in i.operands if op.type==2]
    if any(v in sizes for v in vals):
      f.write(f'\n=== {i.address:#x}: {i.mnemonic} {i.op_str} ===\n')
      for q in ins[max(0,idx-30):min(len(ins),idx+50)]:
        f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')
