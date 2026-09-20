import sys,os
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM,X86_OP_IMM,X86_REG_RIP

p=sys.argv[1]; out=sys.argv[2]
pe=pefile.PE(p); raw=open(p,'rb').read(); base=pe.OPTIONAL_HEADER.ImageBase
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True; md.skipdata=True
ins=[]
for s in pe.sections:
  if s.Characteristics & 0x20000000:
    code=raw[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]
    ins.extend(md.disasm(code,base+s.VirtualAddress))
print('decoded_insns',len(ins),'first',hex(ins[0].address),'last',hex(ins[-1].address))
front=0x180273720; rear=0x180273660
front_ref=front+0xb8; rear_ref=rear+0xb8
ranges=[('rear',rear,rear+0xbc),('front',front,front+0xbc)]\n\ndef ops(i):\n  try: return i.operands\n  except Exception: return []
refs=[]
for idx,i in enumerate(ins):
  for op in ops(i):
    t=None
    if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
      t=i.address+i.size+op.mem.disp
    elif op.type==X86_OP_IMM:
      t=op.imm
    if t is None: continue
    for name,lo,hi in ranges:
      if lo<=t<hi:
        refs.append((idx,i.address,t,name,t-lo,i.mnemonic,i.op_str))
print('block refs',len(refs))
for _,a,t,n,o,m,s in refs:
  print(hex(a),n,hex(o),'->',hex(t),m,s)
with open(os.path.join(out,'axle_block_refs_full.txt'),'w') as f:
  for idx,a,t,n,o,m,s in refs:
    f.write(f'\n===== {a:#x} {n}+{o:#x} -> {t:#x} {m} {s} =====\n')
    for q in ins[max(0,idx-80):min(len(ins),idx+160)]:
      f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')

# direct exact ref_width global refs
exact=[x for x in refs if x[2] in (front_ref,rear_ref)]
print('exact ref refs',len(exact))
for x in exact:print('EXACT',hex(x[1]),x[3],x[5],x[6])

# CreateCar direct decode and call targets
create=base+0x956a0
# locate nearest decoded index
nearest=min(range(len(ins)),key=lambda k:abs(ins[k].address-create))
print('create nearest',hex(ins[nearest].address),ins[nearest].mnemonic,ins[nearest].op_str)
with open(os.path.join(out,'createcar_direct.txt'),'w') as f:
  for q in ins[nearest:min(len(ins),nearest+1000)]:
    f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')
    if q.mnemonic=='ret' and q.address>create+5: break

# scan all RIP refs to wider config globals, with focus createcar-related upper text too
wide=[]
for idx,i in enumerate(ins):
  for op in ops(i):
    if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:
      t=i.address+i.size+op.mem.disp
      if 0x180273000<=t<0x180274000:
        wide.append((idx,i.address,t,i.mnemonic,i.op_str))
print('wide refs',len(wide))
for _,a,t,m,s in wide[:300]:print('WIDE',hex(a),hex(t),m,s)
