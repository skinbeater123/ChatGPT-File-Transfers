"""Bind a non-destructive DTC hood region on native v06.

Creates a world-baked v06 rollback, writes an exact FACE-domain boolean semantic
attribute to Frame_LOD0, and creates a separate visual guide mesh. No work-mesh
positions, topology, pivots, or detachable components may change.
"""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
import bpy
from mathutils import Vector
SOURCE='SOURCE_BIGANT_A01_LOCKED';WORK='DTC_SPRINT_A_WORK';BASES=tuple(f'DTC_SPRINT_A_BASELINE_V0{i}' for i in range(1,7));BASE6='DTC_SPRINT_A_BASELINE_V06';GUIDES='DTC_SEMANTIC_GUIDES_V07';ATTR='dtc_hood_candidate_b';INPUT='DTC_SPRINT_A_v06_BEULAH_FRONT_SHELL';OUTPUT='DTC_SPRINT_A_v07_HOOD_BOUNDARY_BINDING';BASIS='DTC_X_FORWARD_Y_LEFT_Z_UP_METRES_NORMALIZED';SRC_SHA='6621074f3048a4ee41606c6fd15b501bc3fd8723a423ee9a0b7368fb4f428bd6';EXPECTED=438
XMIN=.05;XMAX=1.45;ZMIN=-.15;YMAX=.50;MIN_AREA=.0005
WHEELS={'WheelLF_LOD0':(1.2359206676483154,.7039546370506287,-.32582324743270874),'WheelRF_LOD0':(1.2359206676483154,-.7039546370506287,-.32582324743270874),'WheelLR_LOD0':(-.9337295293807983,.6705295443534851,-.3061189353466034),'WheelRR_LOD0':(-.9337295293807983,-.6705295443534851,-.3061189353466034)}
def cli():
 p=argparse.ArgumentParser();p.add_argument('--in',dest='src',type=Path,required=True);p.add_argument('--out',dest='dst',type=Path,required=True);p.add_argument('--report',type=Path);a=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [];return p.parse_args(a)
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
def fp(o):
 h=hashlib.sha256();h.update(o.name.encode())
 for r in range(4):
  for c in range(4):h.update(float(o.matrix_world[r][c]).hex().encode())
 for v in o.data.vertices:
  for x in v.co:h.update(float(x).hex().encode())
 for p in o.data.polygons:h.update(str(tuple(p.vertices)).encode())
 return h.hexdigest()
def backup(w):
 if bpy.data.collections.get(BASE6):raise RuntimeError('v06 rollback exists')
 b=bpy.data.collections.new(BASE6);bpy.context.scene.collection.children.link(b)
 for o in meshes(w):
  M=o.matrix_world.copy();q=o.copy();q.parent=None;q.data=o.data.copy();q.data.transform(M);q.matrix_world=M.inverted()@M;q.hide_select=True;q['dtc.rollback_role']='V06_PRE_V07_WORLD_BAKED_BACKUP';q['dtc.source_object']=o.name;q['dtc.original_matrix_world']=[float(M[r][c]) for r in range(4) for c in range(4)];q['dtc.original_origin_m']=tuple(float(x) for x in M.translation);b.objects.link(q)
 b.hide_viewport=True;b.hide_render=True;b['dtc.locked_backup']=True;b['dtc.rollback_representation']='WORLD_BAKED_GEOMETRY_PLUS_ORIGINAL_MATRIX_METADATA';b['dtc.rollback_target']='DTC_SPRINT_A_WORK immediately before v07';b['dtc.authoring_basis']=BASIS;return b
def select_faces(o):
 M=o.matrix_world;sel=[]
 for p in o.data.polygons:
  if len(p.vertices)!=3:raise RuntimeError(('non-triangle',p.index,len(p.vertices)))
  a,b,c=[M@o.data.vertices[i].co for i in p.vertices];q=(a+b+c)/3.;area=(b-a).cross(c-a).length*.5
  if XMIN<=q.x<=XMAX and q.z>=ZMIN and abs(q.y)<=YMAX and area>MIN_AREA:sel.append(p.index)
 return sel
def bind(frame,selected):
 old=frame.data.attributes.get(ATTR)
 if old:frame.data.attributes.remove(old)
 a=frame.data.attributes.new(name=ATTR,type='BOOLEAN',domain='FACE');S=set(selected)
 for i,d in enumerate(a.data):d.value=i in S
 frame['dtc.v07_semantic']='MAIN_BODY_COMPILED_WITH_HOOD_BOUNDARY';frame['dtc.hood_boundary_attribute']=ATTR;frame['dtc.hood_boundary_face_count']=len(selected)
def make_guide(frame,selected):
 if bpy.data.collections.get(GUIDES):raise RuntimeError('guide collection exists')
 g=bpy.data.collections.new(GUIDES);bpy.context.scene.collection.children.link(g);g['dtc.guide_only']=True;g['dtc.semantic']='HOOD_BOUNDARY_CANDIDATE_B';g['dtc.production_geometry']=False
 M=frame.matrix_world;verts=[];faces=[]
 for pi in selected:
  p=frame.data.polygons[pi];a,b,c=[M@frame.data.vertices[i].co for i in p.vertices];n=(b-a).cross(c-a).normalized();base=len(verts);verts.extend([tuple(a+n*.002),tuple(b+n*.002),tuple(c+n*.002)]);faces.append((base,base+1,base+2))
 me=bpy.data.meshes.new('DTC_HOOD_BOUNDARY_CANDIDATE_B_GUIDE_MESH');me.from_pydata(verts,[],faces);me.update();o=bpy.data.objects.new('DTC_HOOD_BOUNDARY_CANDIDATE_B_GUIDE',me);g.objects.link(o);o.show_in_front=True;o.display_type='SOLID';o.color=(1.,.05,.05,1.);o['dtc.guide_only']=True;o['dtc.source_frame']=frame.name;o['dtc.face_count']=len(selected);return o
def main():
 ns=cli();bpy.ops.wm.open_mainfile(filepath=str(ns.src));sc=bpy.context.scene;s=coll(SOURCE);w=coll(WORK);prior=[coll(x) for x in BASES[:-1]]
 if sc.get('dtc.asset_version')!=INPUT:raise RuntimeError(('version',sc.get('dtc.asset_version')))
 if sc.get('dtc.authoring_basis')!=BASIS or w.get('dtc.authoring_basis')!=BASIS:raise RuntimeError('bad basis')
 if sc.get('dtc.source_pssg_sha256')!=SRC_SHA:raise RuntimeError('bad donor')
 if [len(meshes(x)) for x in (s,w,*prior)]!=[92,16,16,16,16,16,16]:raise RuntimeError('census')
 for p,t in WHEELS.items():
  if (one(w,p).matrix_world.translation-Vector(t)).length>2e-6:raise RuntimeError(('pivot',p))
 before={o.name:fp(o) for o in meshes(w)};b6=backup(w);frame=one(w,'Frame_LOD0');sel=select_faces(frame)
 if len(sel)!=EXPECTED:raise RuntimeError(('hood face count',len(sel),EXPECTED))
 bind(frame,sel);guide=make_guide(frame,sel)
 if before!={o.name:fp(o) for o in meshes(w)}:raise RuntimeError('work geometry changed')
 parent=sha(ns.src);sc['dtc.asset_version']=OUTPUT;sc['dtc.parent_blend_sha256']=parent;sc['dtc.v07_scope']='non-destructive semantic hood boundary only';sc['dtc.v07_hood_face_count']=len(sel);sc['dtc.physics_authority']='NONE_G2_003_OWNS_SIMULATION';b6['dtc.parent_blend_sha256']=parent
 bpy.ops.wm.save_as_mainfile(filepath=str(ns.dst))
 r={'schema':'dtc_sprint_a_v07_hood_boundary_report_v1','status':'V07_NATIVE_BUILD_PASS','parent':{'sha256':parent,'asset_version':INPUT},'work_meshes':len(meshes(w)),'geometry_changed':False,'hood_attribute':ATTR,'selected_faces':len(sel),'selection_rule_dtc_m':{'centroid_x':[XMIN,XMAX],'centroid_z_min':ZMIN,'centroid_abs_y_max':YMAX,'triangle_area_min_m2':MIN_AREA},'guide':{'collection':GUIDES,'object':guide.name,'faces':len(guide.data.polygons),'offset_m':.002,'production_geometry':False},'rollback':{'collection':BASE6,'meshes':len(meshes(b6)),'representation':b6.get('dtc.rollback_representation')},'wheel_pivots_retained':{k:list(v) for k,v in WHEELS.items()},'ratbag_external_hood_mount':'OPEN','physics_authority':'NONE — G2-003 owns simulation'}
 if ns.report:ns.report.write_text(json.dumps(r,indent=2)+'\n')
 print('DTC_SPRINT_A_V07_NATIVE_BUILD_PASS',json.dumps({'selected_faces':len(sel),'work_geometry_changed':False},sort_keys=True))
if __name__=='__main__':main()
