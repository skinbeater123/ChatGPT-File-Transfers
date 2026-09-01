from __future__ import annotations
import argparse,json,sys,hashlib
from pathlib import Path
import bpy
from mathutils import Vector
SOURCE='SOURCE_BIGANT_A01_LOCKED';WORK='DTC_SPRINT_A_WORK';BASES=tuple(f'DTC_SPRINT_A_BASELINE_V0{i}' for i in range(1,8));BASE7='DTC_SPRINT_A_BASELINE_V07';STAGE='DTC_COMPONENT_STAGING_V08';BASIS='DTC_X_FORWARD_Y_LEFT_Z_UP_METRES_NORMALIZED';INPUT='DTC_SPRINT_A_v07_HOOD_BOUNDARY_BINDING';OUTPUT='DTC_SPRINT_A_v08_HOOD_COMPONENT_STAGE';BROAD='dtc_hood_candidate_b';CORE='dtc_hood_reference_core';BROAD_N=438;CORE_N=171
W={'WheelLF_LOD0':(1.2359206676483154,.7039546370506287,-.32582324743270874),'WheelRF_LOD0':(1.2359206676483154,-.7039546370506287,-.32582324743270874),'WheelLR_LOD0':(-.9337295293807983,.6705295443534851,-.3061189353466034),'WheelRR_LOD0':(-.9337295293807983,-.6705295443534851,-.3061189353466034)}
def cli():
 p=argparse.ArgumentParser();p.add_argument('--in',dest='src',type=Path,required=True);p.add_argument('--out',dest='dst',type=Path,required=True);p.add_argument('--core-json',type=Path,required=True);p.add_argument('--report',type=Path);a=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [];return p.parse_args(a)
def coll(n):c=bpy.data.collections.get(n);assert c is not None,n;return c
def objs(c):
 out=[];seen=set();stack=[c]
 while stack:
  x=stack.pop()
  for o in x.objects:
   if o.name not in seen:seen.add(o.name);out.append(o)
  stack.extend(x.children)
 return out
def meshes(c):return[o for o in objs(c) if o.type=='MESH']
def one(c,p):a=[o for o in meshes(c) if o.name.startswith(p)];assert len(a)==1,(p,[o.name for o in a]);return a[0]
def pts(o):return[o.matrix_world@v.co for v in o.data.vertices]
def fp(o):
 h=hashlib.sha256()
 for p in pts(o):
  for x in p:h.update(float(x).hex().encode())
 for f in o.data.polygons:h.update(str(tuple(f.vertices)).encode())
 return h.hexdigest()
def backup(w):
 assert bpy.data.collections.get(BASE7) is None
 b=bpy.data.collections.new(BASE7);bpy.context.scene.collection.children.link(b)
 for o in meshes(w):
  M=o.matrix_world.copy();q=o.copy();q.parent=None;q.data=o.data.copy();q.data.transform(M);q.matrix_world=M.inverted()@M;q.hide_select=True;q['dtc.rollback_role']='V07_PRE_V08_WORLD_BAKED_BACKUP';q['dtc.source_object']=o.name;q['dtc.original_origin_m']=tuple(float(x) for x in M.translation);b.objects.link(q)
 b.hide_viewport=True;b.hide_render=True;b['dtc.locked_backup']=True;b['dtc.rollback_representation']='WORLD_BAKED_GEOMETRY_PLUS_ORIGINAL_MATRIX_METADATA';b['dtc.rollback_target']='DTC_SPRINT_A_WORK immediately before v08';b['dtc.authoring_basis']=BASIS;return b
def selected_attr(frame,name):
 a=frame.data.attributes.get(name);assert a and a.domain=='FACE' and a.data_type=='BOOLEAN',name;return [i for i,d in enumerate(a.data) if d.value]
def bind_core(frame,idx):
 a=frame.data.attributes.get(CORE)
 if a:frame.data.attributes.remove(a)
 a=frame.data.attributes.new(name=CORE,type='BOOLEAN',domain='FACE');S=set(idx)
 for i,d in enumerate(a.data):d.value=i in S
 frame['dtc.v08_core_attribute']=CORE;frame['dtc.v08_core_faces']=len(idx)
def dup_faces(frame,indices,name,collection,offset=0.0):
 M=frame.matrix_world;verts=[];faces=[]
 for pi in indices:
  p=frame.data.polygons[pi];tri=[M@frame.data.vertices[i].co for i in p.vertices];n=(tri[1]-tri[0]).cross(tri[2]-tri[0]).normalized();base=len(verts);verts.extend([tuple(v+n*offset) for v in tri]);faces.append((base,base+1,base+2))
 me=bpy.data.meshes.new(name+'_MESH');me.from_pydata(verts,[],faces);me.update();o=bpy.data.objects.new(name,me);collection.objects.link(o);o.show_in_front=True;o['dtc.component_stage']=True;o['dtc.production_geometry']=False;o['dtc.source_frame']=frame.name;o['dtc.face_count']=len(indices);return o
def main():
 ns=cli();cfg=json.loads(ns.core_json.read_text());assert cfg['broad_faces']==BROAD_N and cfg['core_faces']==CORE_N and cfg['production_cut_authority'] is False;core=[int(x) for x in cfg['frame_polygon_indices']];assert len(core)==CORE_N
 bpy.ops.wm.open_mainfile(filepath=str(ns.src));sc=bpy.context.scene;s=coll(SOURCE);w=coll(WORK);prior=[coll(x) for x in BASES[:-1]]
 assert sc.get('dtc.asset_version')==INPUT;assert sc.get('dtc.authoring_basis')==BASIS and w.get('dtc.authoring_basis')==BASIS;assert [len(meshes(x)) for x in(s,w,*prior)]==[92,16,16,16,16,16,16,16]
 frame=one(w,'Frame_LOD0');broad=selected_attr(frame,BROAD);assert len(broad)==BROAD_N;assert set(core)<=set(broad)
 before={o.name:fp(o) for o in meshes(w)};b7=backup(w);bind_core(frame,core)
 assert bpy.data.collections.get(STAGE) is None;g=bpy.data.collections.new(STAGE);bpy.context.scene.collection.children.link(g);g['dtc.staging_only']=True;g['dtc.production_geometry']=False
 env=dup_faces(frame,broad,'DTC_HOOD_STAGE_ENVELOPE',g,0.0);env.display_type='WIRE';core_o=dup_faces(frame,core,'DTC_HOOD_REFERENCE_CORE_STAGE',g,.0015);core_o.display_type='SOLID'
 assert before=={o.name:fp(o) for o in meshes(w)}
 for p,t in W.items():assert (one(w,p).matrix_world.translation-Vector(t)).length<2e-6
 sc['dtc.asset_version']=OUTPUT;sc['dtc.v08_scope']='non-destructive independent hood component staging';sc['dtc.geometry_authority']='v06';sc['dtc.semantic_parent']='v07';sc['dtc.production_hood_cut']=False;sc['dtc.physics_authority']='NONE_G2_003_OWNS_SIMULATION'
 bpy.ops.wm.save_as_mainfile(filepath=str(ns.dst))
 r={'schema':'dtc_sprint_a_v08_hood_component_stage_report_v1','status':'V08_NATIVE_BUILD_PASS','asset_version':OUTPUT,'work_geometry_changed':False,'work_meshes':16,'rollback_v07_meshes':len(meshes(b7)),'broad_faces':len(broad),'reference_core_faces':len(core),'stage_objects':{env.name:len(env.data.polygons),core_o.name:len(core_o.data.polygons)},'production_cut':False,'wheel_pivots_retained':{k:list(v) for k,v in W.items()},'physics_authority':'NONE — G2-003 owns simulation'}
 if ns.report:ns.report.write_text(json.dumps(r,indent=2)+'\n')
 print('DTC_SPRINT_A_V08_NATIVE_BUILD_PASS',json.dumps(r,sort_keys=True))
if __name__=='__main__':main()
