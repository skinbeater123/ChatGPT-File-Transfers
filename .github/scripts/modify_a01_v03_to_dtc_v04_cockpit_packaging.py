"""Build DTC_SPRINT_A_v04_COCKPIT_PACKAGING from corrected native v03.
Creates locked BASELINE_V03 before lowering only upper/rear Frame_LOD0 plus
Driver_LOD0 and SteeringWheel_LOD0. Wheel hard-point pivots must already be the
corrected v03 pivots and are preserved unchanged.
"""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
import bpy
from mathutils import Vector
SOURCE='SOURCE_BIGANT_A01_LOCKED'; WORK='DTC_SPRINT_A_WORK'; B1='DTC_SPRINT_A_BASELINE_V01'; B2='DTC_SPRINT_A_BASELINE_V02'; B3='DTC_SPRINT_A_BASELINE_V03'; GUIDES='DTC_WOO_REFERENCE_GUIDES_V04'
SHA='6621074f3048a4ee41606c6fd15b501bc3fd8723a423ee9a0b7368fb4f428bd6'; LOWER=.18; XF=.05; XE=.35; ZS=.30; ZF=.72
def cli():
 p=argparse.ArgumentParser(); p.add_argument('--in',dest='src',required=True,type=Path); p.add_argument('--out',dest='dst',required=True,type=Path); p.add_argument('--report',type=Path); p.add_argument('--export-glb',type=Path); a=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []; return p.parse_args(a)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def coll(n):
 c=bpy.data.collections.get(n)
 if c is None: raise RuntimeError(f'missing {n}')
 return c
def objs(c):
 out=[];seen=set();stack=[c]
 while stack:
  x=stack.pop()
  for o in x.objects:
   if o.name not in seen:seen.add(o.name);out.append(o)
  stack.extend(x.children)
 return out
def meshes(c):return[o for o in objs(c) if o.type=='MESH']
def one(c,p):
 a=[o for o in meshes(c) if o.name.startswith(p)]
 if len(a)!=1:raise RuntimeError(f'{p}: {[x.name for x in a]}')
 return a[0]
def smooth(x):x=max(0,min(1,x));return x*x*(3-2*x)
def backup(w):
 if bpy.data.collections.get(B3):raise RuntimeError(f'{B3} exists')
 b=bpy.data.collections.new(B3);bpy.context.scene.collection.children.link(b);cp={}
 for o in objs(w):
  q=o.copy();q.data=o.data.copy() if o.data else None;q.hide_select=True;q['dtc.rollback_role']='V03_PRE_V04_COCKPIT_BACKUP';q['dtc.source_object']=o.name;b.objects.link(q);cp[o]=q
 for o,q in cp.items():
  if o.parent in cp:q.parent=cp[o.parent];q.matrix_parent_inverse=o.matrix_parent_inverse.copy()
 b.hide_viewport=True;b.hide_render=True;b['dtc.locked_backup']=True;b['dtc.rollback_target']='DTC_SPRINT_A_WORK immediately before v04';return b
def deform(o,fn,label):
 m=o.matrix_world.copy();inv=m.inverted();n=0;mx=0
 for v in o.data.vertices:
  p=m@v.co;q=fn(p);d=(q-p).length;n+=d>1e-9;mx=max(mx,d);v.co=inv@q
 o.data.update();o['dtc.v04_modified']=True;o['dtc.v04_change']=label;o['dtc.v04_changed_vertices']=n;o['dtc.v04_max_vertex_shift_m']=mx;return n,mx
def bounds(o):
 p=[o.matrix_world@v.co for v in o.data.vertices];return{'min':[min(x[i] for x in p) for i in range(3)],'max':[max(x[i] for x in p) for i in range(3)]}
def export(w,p):
 p.parent.mkdir(parents=True,exist_ok=True);bpy.ops.object.select_all(action='DESELECT');a=objs(w)
 for o in a:o.hide_set(False);o.select_set(True)
 if a:bpy.context.view_layer.objects.active=a[0]
 bpy.ops.export_scene.gltf(filepath=str(p),export_format='GLB',use_selection=True,export_apply=True)
def main():
 ns=cli();ns.dst.parent.mkdir(parents=True,exist_ok=True);bpy.ops.wm.open_mainfile(filepath=str(ns.src));s=coll(SOURCE);w=coll(WORK);b1=coll(B1);b2=coll(B2)
 if [len(meshes(x)) for x in(s,w,b1,b2)]!=[92,16,16,16]:raise RuntimeError('v03 census failed')
 if not s.get('dtc.locked_source') or not b1.get('dtc.locked_backup') or not b2.get('dtc.locked_backup'):raise RuntimeError('rollback/source lock missing')
 if bpy.context.scene.get('dtc.source_pssg_sha256')!=SHA:raise RuntimeError('wrong donor source')
 if bpy.context.scene.get('dtc.asset_version')!='DTC_SPRINT_A_v03_HARDPOINT':raise RuntimeError('v04 requires corrected v03')
 for p in('WheelLF_LOD0','WheelRF_LOD0','WheelLR_LOD0','WheelRR_LOD0'):
  o=one(w,p)
  if o.get('dtc.v03_pivot_relocated') is not True:raise RuntimeError(f'{p}: corrected v03 pivot missing')
 parent=sha(ns.src);b3=backup(w)
 for o in meshes(w):o['dtc.v04_modified']=False
 f=one(w,'Frame_LOD0');d=one(w,'Driver_LOD0');st=one(w,'SteeringWheel_LOD0');pre={'frame':bounds(f),'driver':bounds(d),'steering':bounds(st)}
 def ff(p):
  wx=1-smooth((p.x-XF)/(XE-XF));wz=smooth((p.z-ZS)/(ZF-ZS));return Vector((p.x,p.y,p.z-LOWER*wx*wz))
 fc,fm=deform(f,ff,'localized WoO-biased upper cage/cowl lowering');dc,dm=deform(d,lambda p:Vector((p.x,p.y,p.z-LOWER)),'lower driver package');sc,sm=deform(st,lambda p:Vector((p.x,p.y,p.z-LOWER)),'follow lowered driver package')
 changed=sorted(o.name for o in meshes(w) if o.get('dtc.v04_modified') is True)
 if len(changed)!=3 or not all(any(n.startswith(p) for n in changed) for p in('Frame_LOD0','Driver_LOD0','SteeringWheel_LOD0')):raise RuntimeError(f'bad v04 boundary {changed}')
 if bpy.data.collections.get(GUIDES):raise RuntimeError(f'{GUIDES} exists')
 g=bpy.data.collections.new(GUIDES);bpy.context.scene.collection.children.link(g);g['dtc.reference_authority']='WoO 2002 retail axle-aligned driver/cage comparison';g['dtc.physics_authority']='NONE_G2_003_OWNS_SIMULATION'
 scene=bpy.context.scene;scene['dtc.asset_version']='DTC_SPRINT_A_v04_COCKPIT_PACKAGING';scene['dtc.parent_blend_sha256']=parent;scene['dtc.v04_scope']='upper cage/cowl + driver/steering only';scene['dtc.v04_max_lowering_m']=LOWER;scene['dtc.physics_authority']='NONE_G2_003_OWNS_SIMULATION';b3['dtc.parent_blend_sha256']=parent
 bpy.ops.wm.save_as_mainfile(filepath=str(ns.dst))
 if ns.export_glb:export(w,ns.export_glb)
 rep={'schema':'dtc_sprint_a_v04_cockpit_packaging_report_v1','status':'V04_COCKPIT_PACKAGING_BLENDER_PASS','parent_sha256':parent,'rollback':{'v01':B1,'v02':B2,'v03':B3,'v03_meshes':len(meshes(b3))},'changes':{'changed_meshes':changed,'frame_changed_vertices':fc,'frame_max_shift_m':fm,'driver_max_shift_m':dm,'steering_max_shift_m':sm},'bounds_before':pre,'bounds_after':{'frame':bounds(f),'driver':bounds(d),'steering':bounds(st)},'next_gate':'resolve WoO hood/tank assembly transforms before body silhouette edits'}
 if ns.report:ns.report.parent.mkdir(parents=True,exist_ok=True);ns.report.write_text(json.dumps(rep,indent=2)+'\n',encoding='utf-8')
 print('DTC_SPRINT_A_V04_COCKPIT_PACKAGING_PASS',json.dumps(rep['changes'],sort_keys=True))
if __name__=='__main__':main()
