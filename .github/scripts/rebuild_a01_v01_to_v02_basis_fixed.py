"""Rebuild DTC Sprint A v02 from immutable v01 with normalized Blender/DTC basis."""
from __future__ import annotations
import argparse,hashlib,json,math,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
IN=.0254
SOURCE='SOURCE_BIGANT_A01_LOCKED';WORK='DTC_SPRINT_A_WORK';BASE='DTC_SPRINT_A_BASELINE_V01';GUIDES='DTC_WOO_REFERENCE_GUIDES_V02'
WOO=dict(top_wing_span_in=62.3471,top_wing_long_in=78.2231,top_wing_wb_fraction=.31294,front_wing_span_in=40.2439,front_wing_long_in=21.9439,front_wing_ahead_front_in=7.3339,nerf_outer_width_in=55.5684,nerf_long_in=21.6712,nerf_wb_fraction=.37169,wheelbase_in=85.4193)
BA=dict(top_wing_span_in=64.6983,top_wing_long_in=83.6137,top_wing_wb_fraction=.27916,front_wing_span_in=39.2526,front_wing_long_in=24.7943,front_wing_ahead_front_in=10.3745,nerf_outer_width_in=58.1518,nerf_long_in=19.0521,nerf_wb_fraction=.33268,wheelbase_in=88.3457)
def cli():
 p=argparse.ArgumentParser();p.add_argument('--in',dest='src',required=True,type=Path);p.add_argument('--out',dest='dst',required=True,type=Path);p.add_argument('--report',type=Path);p.add_argument('--export-glb',type=Path);a=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [];return p.parse_args(a)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def coll(n):
 c=bpy.data.collections.get(n)
 if c is None:raise RuntimeError(f'missing {n}')
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
def match(c,p):
 a=[o for o in meshes(c) if o.name.startswith(p)]
 if not a:raise RuntimeError(f'no {p}')
 return a
def bounds(os):
 pts=[o.matrix_world@v.co for o in os for v in o.data.vertices];mn=Vector(tuple(min(p[i] for p in pts) for i in range(3)));mx=Vector(tuple(max(p[i] for p in pts) for i in range(3)));return mn,mx
def center(os):
 a,b=bounds(os);return(a+b)*.5
def roots(c):
 ss=set(objs(c));return[o for o in ss if o.parent not in ss]
def normalize(work):
 R=Matrix.Rotation(math.radians(-90),4,'X');rr=roots(work)
 for o in rr:o.matrix_world=R@o.matrix_world
 work['dtc.authoring_basis']='DTC_X_FORWARD_Y_LEFT_Z_UP_METRES_NORMALIZED';work['dtc.basis_fix']='GLTF_IMPORT_X_NEGZ_Y_TO_DTC_ROT_X_NEG90';return[o.name for o in rr]
def backup(work):
 if bpy.data.collections.get(BASE):raise RuntimeError(f'{BASE} exists')
 b=bpy.data.collections.new(BASE);bpy.context.scene.collection.children.link(b);cp={}
 for o in objs(work):
  q=o.copy();q.data=o.data.copy() if o.data else None;q.hide_select=True;q['dtc.rollback_role']='NORMALIZED_V01_PRE_V02_BACKUP';q['dtc.source_object']=o.name;b.objects.link(q);cp[o]=q
 for o,q in cp.items():
  if o.parent in cp:q.parent=cp[o.parent];q.matrix_parent_inverse=o.matrix_parent_inverse.copy()
 b.hide_viewport=True;b.hide_render=True;b['dtc.locked_backup']=True;b['dtc.rollback_target']='normalized Big Ant A01 before v02 visual edits';b['dtc.authoring_basis']='DTC_X_FORWARD_Y_LEFT_Z_UP_METRES_NORMALIZED';return b
def deform_group(os,sx=1,sy=1,sz=1,delta=(0,0,0),label=''):
 c=center(os);d=Vector(delta)
 for o in os:
  m=o.matrix_world.copy();inv=m.inverted()
  for v in o.data.vertices:
   p=m@v.co;q=Vector((c.x+(p.x-c.x)*sx,c.y+(p.y-c.y)*sy,c.z+(p.z-c.z)*sz))+d;v.co=inv@q
  o.data.update();o['dtc.v02_modified']=True;o['dtc.v02_change']=label
def export(work,p):
 p.parent.mkdir(parents=True,exist_ok=True);bpy.ops.object.select_all(action='DESELECT');a=objs(work)
 for o in a:o.hide_set(False);o.select_set(True)
 if a:bpy.context.view_layer.objects.active=a[0]
 bpy.ops.export_scene.gltf(filepath=str(p),export_format='GLB',use_selection=True,export_apply=True)
def main():
 ns=cli();bpy.ops.wm.open_mainfile(filepath=str(ns.src));s=coll(SOURCE);w=coll(WORK)
 if len(meshes(s))!=92 or len(meshes(w))!=16:raise RuntimeError('v01 census failed')
 if not s.get('dtc.locked_source'):raise RuntimeError('source lock missing')
 parent=sha(ns.src);r=normalize(w);lf=match(w,'WheelLF_LOD0')[0];rf=match(w,'WheelRF_LOD0')[0]
 if not(lf.matrix_world.translation.y>0 and rf.matrix_world.translation.y<0 and lf.matrix_world.translation.z<0):raise RuntimeError('basis normalization sanity failed')
 b=backup(w)
 for o in meshes(w):o['dtc.v02_modified']=False
 top=match(w,'TopWing_LOD0_DMG0');ts=WOO['top_wing_span_in']/BA['top_wing_span_in'];tl=WOO['top_wing_long_in']/BA['top_wing_long_in'];tdx=(WOO['top_wing_wb_fraction']*WOO['wheelbase_in']-BA['top_wing_wb_fraction']*BA['wheelbase_in'])*IN;deform_group(top,sx=tl,sy=ts,delta=(tdx,0,0),label='WoO top-wing longitudinal/span envelope; DTC basis')
 fw=match(w,'FrontWing_LOD0_DMG0');fs=WOO['front_wing_span_in']/BA['front_wing_span_in'];fl=WOO['front_wing_long_in']/BA['front_wing_long_in'];fdx=(WOO['front_wing_ahead_front_in']-BA['front_wing_ahead_front_in'])*IN;deform_group(fw,sx=fl,sy=fs,delta=(fdx,0,0),label='WoO front-wing longitudinal/span envelope; current axle')
 le=match(w,'BumperLeft_DMG0_LOD0');ri=match(w,'BumperRight_DMG0_LOD0');nl=WOO['nerf_long_in']/BA['nerf_long_in'];ndx=(WOO['nerf_wb_fraction']*WOO['wheelbase_in']-BA['nerf_wb_fraction']*BA['wheelbase_in'])*IN;nin=(BA['nerf_outer_width_in']-WOO['nerf_outer_width_in'])*IN/2;deform_group(le,sx=nl,delta=(ndx,-nin,0),label='WoO left nerf');deform_group(ri,sx=nl,delta=(ndx,+nin,0),label='WoO right nerf')
 scene=bpy.context.scene;scene['dtc.asset_version']='DTC_SPRINT_A_v02';scene['dtc.authoring_basis']='DTC_X_FORWARD_Y_LEFT_Z_UP_METRES_NORMALIZED';scene['dtc.basis_fix']='GLTF_IMPORT_X_NEGZ_Y_TO_DTC_ROT_X_NEG90';scene['dtc.parent_v01_sha256']=parent;scene['dtc.physics_authority']='NONE_G2_003_OWNS_SIMULATION';b['dtc.parent_v01_sha256']=parent
 ns.dst.parent.mkdir(parents=True,exist_ok=True);bpy.ops.wm.save_as_mainfile(filepath=str(ns.dst))
 if ns.export_glb:export(w,ns.export_glb)
 tb=bounds(top);fb=bounds(fw);nb=bounds(le+ri);changed=sorted(o.name for o in meshes(w) if o.get('dtc.v02_modified') is True)
 rep={'schema':'dtc_sprint_a_v02_basis_fixed_report_v1','status':'V02_BASIS_FIXED_BLENDER_PASS','parent_v01_sha256':parent,'normalized_roots':r,'authoring_basis':scene['dtc.authoring_basis'],'rollback':{'v01':BASE,'meshes':len(meshes(b))},'changes':{'changed_meshes':changed,'top_ext_m':list(tb[1]-tb[0]),'front_ext_m':list(fb[1]-fb[0]),'nerf_ext_m':list(nb[1]-nb[0]),'top_dx_m':tdx,'front_dx_m':fdx,'nerf_dx_m':ndx,'nerf_inset_each_m':nin}}
 if ns.report:ns.report.parent.mkdir(parents=True,exist_ok=True);ns.report.write_text(json.dumps(rep,indent=2)+'\n',encoding='utf-8')
 print('DTC_V02_BASIS_FIXED_PASS',json.dumps(rep['changes'],sort_keys=True))
if __name__=='__main__':main()
