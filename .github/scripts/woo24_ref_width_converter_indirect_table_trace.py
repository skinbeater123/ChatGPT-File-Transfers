import sys,os,struct
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
from capstone.x86 import X86_OP_MEM,X86_OP_IMM,X86_REG_RIP
p=sys.argv[1]; out=sys.argv[2]
pe=pefile.PE(p); raw=open(p,'rb').read(); base=pe.OPTIONAL_HEADER.ImageBase
md=Cs(CS_ARCH_X86,CS_MODE_64); md.detail=True
target=base+0x2b30

def off2rva(o):
  for s in pe.sections:
    if s.PointerToRawData<=o<s.PointerToRawData+s.SizeOfRawData:
      return s.VirtualAddress+o-s.PointerToRawData
hits=[]
for label,pat in [('va64',struct.pack('<Q',target)),('rva32',struct.pack('<I',target-base))]:
  st=0
  while 1:
    o=raw.find(pat,st)
    if o<0: break
    r=off2rva(o); hits.append((label,o,r,base+r if r is not None else None)); st=o+1
print('target',hex(target),'hits',[(l,hex(o),hex(r) if r else None,hex(v) if v else None) for l,o,r,v in hits])
with open(os.path.join(out,'function_pointer_context.txt'),'w') as f:
  for h in hits:
    l,o,r,v=h
    f.write(f'\n===== {h} =====\n')
    for x in range(max(0,o-0x100),min(len(raw),o+0x180),8):
      q=struct.unpack_from('<Q',raw,x)[0]
      rr=off2rva(x)
      f.write(f'{x:#x} {hex(base+rr) if rr else None} q={q:#x}\n')

# all executable insns xref the data-cell addresses that contain target
ins=[]
for s in pe.sections:
  if s.Characteristics & 0x20000000:
    code=raw[s.PointerToRawData:s.PointerToRawData+s.SizeOfRawData]
    ins.extend(md.disasm(code,base+s.VirtualAddress))
cells={v for _,_,_,v in hits if v}
refs=[]
for idx,i in enumerate(ins):
  for op in i.operands:
    t=None
    if op.type==X86_OP_MEM and op.mem.base==X86_REG_RIP:t=i.address+i.size+op.mem.disp
    elif op.type==X86_OP_IMM:t=op.imm
    if t in cells: refs.append((idx,i.address,t,i.mnemonic,i.op_str))
print('cell refs',[(hex(a),hex(t),m,o) for _,a,t,m,o in refs])
with open(os.path.join(out,'function_pointer_cell_xrefs.txt'),'w') as f:
  for idx,a,t,m,o in refs:
    f.write(f'\n===== {a:#x} -> cell {t:#x} =====\n')
    for q in ins[max(0,idx-100):idx+180]:
      f.write(f'{q.address:#018x}: {q.mnemonic:8s} {q.op_str}\n')

# Find nearby pointers that point into .text and emit rough table.
for _,o,r,v in hits:
  if _!='va64': continue
  print('table around hit',hex(o))
  for x in range(o-0x80,o+0x100,8):
    q=struct.unpack_from('<Q',raw,x)[0]
    if base<=q<base+pe.OPTIONAL_HEADER.SizeOfImage:
      print(hex(x),hex(q),'rva',hex(q-base))
