"""Build native DTC_SPRINT_A_v05_BEULAH_SHELL from corrected v04 authority."""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
import bpy
from mathutils import Vector
SOURCE="SOURCE_BIGANT_A01_LOCKED";WORK="DTC_SPRINT_A_WORK";B1="DTC_SPRINT_A_BASELINE_V01";B2="DTC_SPRINT_A_BASELINE_V02";B3="DTC_SPRINT_A_BASELINE_V03";B4="DTC_SPRINT_A_BASELINE_V04";GUIDES="DTC_WOO_REFERENCE_GUIDES_V05"
BASIS="DTC_X_FORWARD_Y_LEFT_Z_UP_METRES_NORMALIZED";INPUT="DTC_SPRINT_A_v04_COCKPIT_PACKAGING";OUTPUT="DTC_SPRINT_A_v05_BEULAH_SHELL";SRC_SHA="6621074f3048a4ee41606c6fd15b501bc3fd8723a423ee9a0b7368fb4f428bd6"
NATIVE_CHANGED=3838;NATIVE_MAX=.0214083495500494;NATIVE_MEAN=.01018749668792615
WHEELS={"WheelLF_LOD0":(1.2359206676483154,.7039546370506287,-.32582324743270874),"WheelRF_LOD0":(1.2359206676483154,-.7039546370506287,-.32582324743270874),"WheelLR_LOD0":(-.9337295293807983,.6705295443534851,-.3061189353466034),"WheelRR_LOD0":(-.9337295293807983,-.6705295443534851,-.3061189353466034)}
PROTECTED=("BumperFront_DMG0_LOD0","BumperLeft_DMG0_LOD0","BumperRear_DMG0_LOD0","BumperRight_DMG0_LOD0","Driver_LOD0","Frame_engine_struts_LOD0","FrontWing_LOD0_DMG0","SteeringWheel_LOD0","TopWing_LOD0_DMG0","WheelLF_LOD0","WheelLR_LOD0","WheelRF_LOD0","WheelRR_LOD0")
def cli():
 p=argparse.ArgumentParser();p.add_argument('--in',dest='src',required=True,type=Path);p.add_argument('--out',dest='dst',required=True,type=Path);p.add_argument('--report',type=Path);p.add_argument('--export-glb',type=Path);a=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [];return p.parse_args(a)
def sha(p):
 h=hashlib.sha256();
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
def one(c,p):
 a=[o for o in meshes(c) if o.name.startswith(p)]
 if len(a)!=1:raise RuntimeError((p,[o.name for o in a]))
 return a[0]
def ss(x):x=max(0.,min(1.,x));return x*x*(3-2*x)
def bounds(o):
 p=[o.matrix_world@v.co for v in o.data.vertices];return Vector(tuple(min(x[i] for x in p) for i in range(3))),Vector(tuple(max(x[i] for x in p) for i in range(3)))
def fp(o):
 h=hashlib.sha256();h.update(o.name.encode())
 for r in range(4):
  for c in range(4):h.update(float(o.matrix_world[r][c]).hex().encode())
 for v in o.data.vertices:
  for x in v.co:h.update(float(x).hex().encode())
 for p in o.data.polygons:h.update(str(tuple(p.vertices)).encode())
 return h.hexdigest()
def backup(w):
 if bpy.data.collections.get(B4):raise RuntimeError('v04 rollback exists')
 b=bpy.data.collections.new(B4);bpy.context.scene.collection.children.link(b)
 for o in meshes(w):
  M=o.matrix_world.copy();q=o.copy();q.parent=None;q.data=o.data.copy();q.data.transform(M);q.matrix_world=M.inverted()@M;q.hide_select=True;q['dtc.rollback_role']='V04_PRE_V05_WORLD_BAKED_BACKUP';q['dtc.source_object']=o.name;q['dtc.original_matrix_world']=[float(M[r][c]) for r in range(4) for c in range(4)];q['dtc.original_origin_m']=tuple(float(x) for x in M.translation);b.objects.link(q)
 b.hide_viewport=True;b.hide_render=True;b['dtc.locked_backup']=True;b['dtc.rollback_representation']='WORLD_BAKED_GEOMETRY_PLUS_ORIGINAL_MATRIX_METADATA';b['dtc.rollback_target']='DTC_SPRINT_A_WORK immediately before v05';b['dtc.authoring_basis']=BASIS;return b
def deform(o):
 mn,mx=bounds(o);cy=(mn.y+mx.y)*.5;M=o.matrix_world.copy();inv=M.inverted();sh=[];changed=0
 for v in o.data.vertices:
  p=M@v.co;q=p.copy();wz=ss((p.z+.12)/.54);wc=1-.35*ss((abs(p.x-.05)-.85)/.55);wc=max(.65,min(1.,wc));q.y=cy+(p.y-cy)*(1-.055*wz*wc);wf=ss((p.x-.25)/1.30)*ss(p.z/.45);q.z-=.035*wf;q.x-=.018*wf;d=(q-p).length
  if d>1e-6:changed+=1;sh.append(float(d))
  v.co=inv@q
 o.data.update();o['dtc.v05_modified']=True;o['dtc.v05_semantic']='MAIN_BODY_COMPILED';return {'center_y_m':float(cy),'changed_vertices':changed,'max_vertex_shift_m':max(sh),'mean_changed_vertex_shift_m':sum(sh)/len(sh)}
def export(w,p):
 bpy.ops.object.select_all(action='DESELECT');a=objs(w)
 for o in a:o.hide_set(False);o.select_set(True)
 if a:bpy.context.view_layer.objects.active=a[0]
 bpy.ops.export_scene.gltf(filepath=str(p),export_format='GLB',use_selection=True,export_apply=True)
def main():
 ns=cli();bpy.ops.wm.open_mainfile(filepath=str(ns.src));sc=bpy.context.scene;s=coll(SOURCE);w=coll(WORK);b1,b2,b3=coll(B1),coll(B2),coll(B3)
 if sc.get('dtc.asset_version')!=INPUT:raise RuntimeError(('version',sc.get('dtc.asset_version')))
 if sc.get('dtc.authoring_basis')!=BASIS or w.get('dtc.authoring_basis')!=BASIS:raise RuntimeError('bad basis')
 if sc.get('dtc.source_pssg_sha256')!=SRC_SHA:raise RuntimeError('bad donor')
 if [len(meshes(x)) for x in(s,w,b1,b2,b3)]!=[92,16,16,16,16]:raise RuntimeError('census')
 for p,t in WHEELS.items():
  if (one(w,p).matrix_world.translation-Vector(t)).length>2e-6:raise RuntimeError(('pre pivot',p))
 frame=one(w,'Frame_LOD0');protected=[o for o in meshes(w) if o is not frame]
 if len(protected)!=15 or not all(any(o.name.startswith(p) for p in PROTECTED) for o in protected):raise RuntimeError('protected set')
 before={o.name:fp(o) for o in protected};b4=backup(w)
 for o in meshes(w):o['dtc.v05_modified']=False
 st=deform(frame);flags=sorted(o.name for o in meshes(w) if o.get('dtc.v05_modified') is True)
 if flags!=[frame.name]:raise RuntimeError(('flags',flags))
 if before!={o.name:fp(o) for o in protected}:raise RuntimeError('protected changed')
 for p,t in WHEELS.items():
  if (one(w,p).matrix_world.translation-Vector(t)).length>2e-6:raise RuntimeError(('post pivot',p))
 if st['changed_vertices']!=NATIVE_CHANGED or abs(st['max_vertex_shift_m']-NATIVE_MAX)>5e-6 or abs(st['mean_changed_vertex_shift_m']-NATIVE_MEAN)>5e-6:raise RuntimeError(('native preview formula mismatch',st))
 parent=sha(ns.src);sc['dtc.asset_version']=OUTPUT;sc['dtc.parent_blend_sha256']=parent;sc['dtc.v05_scope']='Frame_LOD0 only; conservative Beulah-referenced shell pass';sc['dtc.v05_preview_equivalence']='formula-equivalent; GLB export vertex seams checked separately';sc['dtc.physics_authority']='NONE_G2_003_OWNS_SIMULATION';b4['dtc.parent_blend_sha256']=parent
 if bpy.data.collections.get(GUIDES) is None:
  g=bpy.data.collections.new(GUIDES);bpy.context.scene.collection.children.link(g);g['dtc.reference_authority']='WoO Beulah lower-tier visual direction; Maxim sibling retained as contrast';g['dtc.physics_authority']='NONE_G2_003_OWNS_SIMULATION'
 bpy.ops.wm.save_as_mainfile(filepath=str(ns.dst));
 if ns.export_glb:export(w,ns.export_glb)
 r={'schema':'dtc_sprint_a_v05_beulah_shell_report_v1','status':'V05_NATIVE_BUILD_PASS','parent':{'sha256':parent,'asset_version':INPUT},'authoring_basis':BASIS,'rollback':{'v04':B4,'representation':b4.get('dtc.rollback_representation'),'meshes':len(meshes(b4))},'changes':{'modified_meshes':flags,'upper_body_max_lateral_reduction_pct':5.5,'front_upper_shell_max_lowering_m':.035,'front_upper_shell_max_rearward_m':.018,**st},'representation_note':'Native Blender vertex count differs from GLB export because glTF splits seam/normal vertices; accepted preview has 3892 changed exported entries while native source has 3838 changed vertices.','protected_fingerprints_unchanged':True,'wheel_pivots_retained':{k:list(v) for k,v in WHEELS.items()},'physics_authority':'NONE — G2-003 owns simulation'}
 if ns.report:Path(ns.report).write_text(json.dumps(r,indent=2)+'\n')
 print('DTC_SPRINT_A_V05_NATIVE_BUILD_PASS',json.dumps(r['changes'],sort_keys=True))
if __name__=='__main__':main()
