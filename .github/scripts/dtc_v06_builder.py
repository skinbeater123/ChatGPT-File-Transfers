"""Build DTC_SPRINT_A_v06_BEULAH_FRONT_SHELL from native v05."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
import bpy
from mathutils import Vector
SOURCE="SOURCE_BIGANT_A01_LOCKED";WORK="DTC_SPRINT_A_WORK";BASES=("DTC_SPRINT_A_BASELINE_V01","DTC_SPRINT_A_BASELINE_V02","DTC_SPRINT_A_BASELINE_V03","DTC_SPRINT_A_BASELINE_V04");BASE5="DTC_SPRINT_A_BASELINE_V05";BASIS="DTC_X_FORWARD_Y_LEFT_Z_UP_METRES_NORMALIZED";INPUT="DTC_SPRINT_A_v05_BEULAH_SHELL";OUTPUT="DTC_SPRINT_A_v06_BEULAH_FRONT_SHELL";SRC_SHA="6621074f3048a4ee41606c6fd15b501bc3fd8723a423ee9a0b7368fb4f428bd6"
LOWER=.15;REARWARD=.03;NARROW=.06;X0=0.;XRANGE=1.45;Z0=.02;ZRANGE=.38
WHEELS={"WheelLF_LOD0":(1.2359206676483154,.7039546370506287,-.32582324743270874),"WheelRF_LOD0":(1.2359206676483154,-.7039546370506287,-.32582324743270874),"WheelLR_LOD0":(-.9337295293807983,.6705295443534851,-.3061189353466034),"WheelRR_LOD0":(-.9337295293807983,-.6705295443534851,-.3061189353466034)}
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
def one(c,p):
 a=[o for o in meshes(c) if o.name.startswith(p)]
 if len(a)!=1:raise RuntimeError((p,[o.name for o in a]))
 return a[0]
def ss(x):x=max(0.,min(1.,x));return x*x*(3-2*x)
def fp(o):
 h=hashlib.sha256();h.update(o.name.encode())
 for r in range(4):
  for c in range(4):h.update(float(o.matrix_world[r][c]).hex().encode())
 for v in o.data.vertices:
  for x in v.co:h.update(float(x).hex().encode())
 for p in o.data.polygons:h.update(str(tuple(p.vertices)).encode())
 return h.hexdigest()
def backup(w):
 if bpy.data.collections.get(BASE5):raise RuntimeError('v05 rollback exists')
 b=bpy.data.collections.new(BASE5);bpy.context.scene.collection.children.link(b)
 for o in meshes(w):
  M=o.matrix_world.copy();q=o.copy();q.parent=None;q.data=o.data.copy();q.data.transform(M);q.matrix_world=M.inverted()@M;q.hide_select=True;q['dtc.rollback_role']='V05_PRE_V06_WORLD_BAKED_BACKUP';q['dtc.source_object']=o.name;q['dtc.original_matrix_world']=[float(M[r][c]) for r in range(4) for c in range(4)];q['dtc.original_origin_m']=tuple(float(x) for x in M.translation);b.objects.link(q)
 b.hide_viewport=True;b.hide_render=True;b['dtc.locked_backup']=True;b['dtc.rollback_representation']='WORLD_BAKED_GEOMETRY_PLUS_ORIGINAL_MATRIX_METADATA';b['dtc.rollback_target']='DTC_SPRINT_A_WORK immediately before v06';b['dtc.authoring_basis']=BASIS;return b
def bounds(o):
 p=[o.matrix_world@v.co for v in o.data.vertices];return Vector(tuple(min(x[i] for x in p) for i in range(3))),Vector(tuple(max(x[i] for x in p) for i in range(3)))
def target(p,cy):
 wx=ss((p.x-X0)/XRANGE);wz=ss((p.z-Z0)/ZRANGE);w=wx*wz;return Vector((p.x-REARWARD*w,cy+(p.y-cy)*(1-NARROW*w),p.z-LOWER*w))
def deform(frame):
 mn,mx=bounds(frame);cy=(mn.y+mx.y)*.5;M=frame.matrix_world.copy();inv=M.inverted();sh=[]
 for v in frame.data.vertices:
  p=M@v.co;q=target(p,cy);d=(q-p).length
  if d>1e-6:sh.append(float(d))
  v.co=inv@q
 frame.data.update();frame['dtc.v06_modified']=True;frame['dtc.v06_semantic']='MAIN_BODY_COMPILED_FRONT_SHELL';return {'center_y_m':float(cy),'changed_vertices':len(sh),'max_vertex_shift_m':max(sh) if sh else 0.0,'mean_changed_vertex_shift_m':sum(sh)/len(sh) if sh else 0.0}
def export(w,p):
 bpy.ops.object.select_all(action='DESELECT');a=objs(w)
 for o in a:o.hide_set(False);o.select_set(True)
 if a:bpy.context.view_layer.objects.active=a[0]
 bpy.ops.export_scene.gltf(filepath=str(p),export_format='GLB',use_selection=True,export_apply=True)
def main():
 ns=cli();bpy.ops.wm.open_mainfile(filepath=str(ns.src));sc=bpy.context.scene;s=coll(SOURCE);w=coll(WORK);prior=[coll(x) for x in BASES]
 if sc.get('dtc.asset_version')!=INPUT:raise RuntimeError(('version',sc.get('dtc.asset_version')))
 if sc.get('dtc.authoring_basis')!=BASIS or w.get('dtc.authoring_basis')!=BASIS:raise RuntimeError('bad basis')
 if sc.get('dtc.source_pssg_sha256')!=SRC_SHA:raise RuntimeError('bad donor')
 if [len(meshes(x)) for x in (s,w,*prior)]!=[92,16,16,16,16,16]:raise RuntimeError('census')
 if not s.get('dtc.locked_source') or not all(x.get('dtc.locked_backup') for x in prior):raise RuntimeError('source/rollback lock')
 for p,t in WHEELS.items():
  if (one(w,p).matrix_world.translation-Vector(t)).length>2e-6:raise RuntimeError(('pre pivot',p))
 frame=one(w,'Frame_LOD0');protected=[o for o in meshes(w) if o is not frame];before={o.name:fp(o) for o in protected};b5=backup(w)
 for o in meshes(w):o['dtc.v06_modified']=False
 st=deform(frame);flags=sorted(o.name for o in meshes(w) if o.get('dtc.v06_modified') is True)
 if flags!=[frame.name]:raise RuntimeError(('edit boundary',flags))
 if before!={o.name:fp(o) for o in protected}:raise RuntimeError('protected changed')
 if st['max_vertex_shift_m']>.08:raise RuntimeError(('v06 displacement too large',st))
 for p,t in WHEELS.items():
  if (one(w,p).matrix_world.translation-Vector(t)).length>2e-6:raise RuntimeError(('post pivot',p))
 parent=sha(ns.src);sc['dtc.asset_version']=OUTPUT;sc['dtc.parent_blend_sha256']=parent;sc['dtc.v06_scope']='Frame_LOD0 front upper cowl/nose only';sc['dtc.v06_parameters']=json.dumps({'lower_m':LOWER,'rearward_m':REARWARD,'narrow_fraction':NARROW,'x0':X0,'xrange':XRANGE,'z0':Z0,'zrange':ZRANGE});sc['dtc.physics_authority']='NONE_G2_003_OWNS_SIMULATION';b5['dtc.parent_blend_sha256']=parent
 bpy.ops.wm.save_as_mainfile(filepath=str(ns.dst))
 if ns.export_glb:export(w,ns.export_glb)
 r={'schema':'dtc_sprint_a_v06_beulah_front_shell_report_v1','status':'V06_NATIVE_BUILD_PASS','parent':{'sha256':parent,'asset_version':INPUT},'authoring_basis':BASIS,'rollback':{'v05':BASE5,'representation':b5.get('dtc.rollback_representation'),'meshes':len(meshes(b5))},'parameters':{'lower_m':LOWER,'rearward_m':REARWARD,'narrow_fraction':NARROW,'x0':X0,'xrange':XRANGE,'z0':Z0,'zrange':ZRANGE},'changes':{'modified_meshes':flags,**st},'protected_fingerprints_unchanged':True,'wheel_pivots_retained':{k:list(v) for k,v in WHEELS.items()},'physics_authority':'NONE — G2-003 owns simulation'}
 if ns.report:Path(ns.report).write_text(json.dumps(r,indent=2)+'\n')
 print('DTC_SPRINT_A_V06_NATIVE_BUILD_PASS',json.dumps(r['changes'],sort_keys=True))
if __name__=='__main__':main()
