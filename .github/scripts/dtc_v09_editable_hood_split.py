#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, sys
from collections import Counter
from pathlib import Path
import bmesh, bpy

V08_SHA='ad9080c7bc7b9475547edda3ad1eb2ca9fabed6cbd2341b2ac339683b32a6456'
WORK='DTC_SPRINT_A_WORK'; BROAD_ATTR='dtc_hood_candidate_b'; EXPECTED_HOOD_FACES=438
ROLLBACK_COLL='DTC_SPRINT_A_BASELINE_V08_PRACTICAL'; BODY_NAME='DTC_Body_LOD0'; HOOD_NAME='DTC_Hood'
ASSET_VERSION='DTC_SPRINT_A_v09_EDITABLE_HOOD_SPLIT'

def sha256(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for c in iter(lambda:f.read(1<<20),b''): h.update(c)
 return h.hexdigest()

def objs(c):
 out=[]; seen=set(); stack=[c]
 while stack:
  x=stack.pop()
  for o in x.objects:
   if o.name not in seen: seen.add(o.name); out.append(o)
  stack.extend(x.children)
 return out

def meshes(c): return [o for o in objs(c) if o.type=='MESH']
def one(c,prefix):
 a=[o for o in meshes(c) if o.name.startswith(prefix)]
 if len(a)!=1: raise RuntimeError((prefix,[o.name for o in a]))
 return a[0]

def sig(obj,poly,d=8):
 vv=[]
 for vi in poly.vertices:
  w=obj.matrix_world@obj.data.vertices[vi].co
  vv.append(tuple(round(float(w[k]),d) for k in range(3)))
 return tuple(sorted(vv))
def multiset(o): return Counter(sig(o,p) for p in o.data.polygons)
def selected(mesh,name):
 a=mesh.attributes.get(name)
 if not a or a.domain!='FACE' or a.data_type!='BOOLEAN': raise RuntimeError(name)
 return [i for i,x in enumerate(a.data) if bool(x.value)]
def filter_faces(obj,ids,keep):
 wanted=set(ids); bm=bmesh.new(); bm.from_mesh(obj.data); bm.faces.ensure_lookup_table()
 doomed=[f for f in bm.faces if ((f.index in wanted)!=keep)]
 bmesh.ops.delete(bm,geom=doomed,context='FACES'); bm.to_mesh(obj.data); bm.free(); obj.data.update()
def args():
 p=argparse.ArgumentParser(); p.add_argument('--blend',type=Path,required=True); p.add_argument('--out-blend',type=Path,required=True); p.add_argument('--report',type=Path,required=True)
 return p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])

def main():
 ns=args()
 if sha256(ns.blend)!=V08_SHA: raise RuntimeError('v08 hash gate')
 bpy.ops.wm.open_mainfile(filepath=str(ns.blend))
 work=bpy.data.collections.get(WORK)
 if not work: raise RuntimeError('work collection missing')
 frame=one(work,'Frame_LOD0')
 hood_ids=selected(frame.data,BROAD_ATTR)
 if len(hood_ids)!=EXPECTED_HOOD_FACES: raise RuntimeError(('hood faces',len(hood_ids)))
 original_faces=len(frame.data.polygons); original_verts=len(frame.data.vertices); original=multiset(frame)

 # Complete in-file v08 work rollback (all 16 work meshes), while the exact v08 .blend remains external authority too.
 if bpy.data.collections.get(ROLLBACK_COLL): raise RuntimeError('rollback collection already exists')
 rb=bpy.data.collections.new(ROLLBACK_COLL); bpy.context.scene.collection.children.link(rb)
 for o in meshes(work):
  q=o.copy(); q.data=o.data.copy(); q.name='V08_'+o.name; q.data.name=q.name+'_Mesh'; q.hide_select=True; rb.objects.link(q)
 rb.hide_viewport=True; rb.hide_render=True; rb['dtc.rollback_role']='COMPLETE_V08_WORK_ROLLBACK'; rb['dtc.locked_backup']=True

 # Working body is the existing frame; hood is a true independent mesh object.
 hood=frame.copy(); hood.data=frame.data.copy(); hood.name=HOOD_NAME; hood.data.name=HOOD_NAME+'_Mesh'; work.objects.link(hood)
 filter_faces(hood,hood_ids,True)
 filter_faces(frame,hood_ids,False)
 frame.name=BODY_NAME; frame.data.name=BODY_NAME+'_Mesh'
 for o in (frame,hood):
  for n in ('dtc_hood_candidate_b','dtc_hood_reference_core'):
   a=o.data.attributes.get(n)
   if a: o.data.attributes.remove(a)
 frame['dtc_role']='working_body'; frame['dtc_editable']=True
 hood['dtc_role']='detachable_hood'; hood['dtc_editable']=True; hood['dtc_component']='hood'; hood['dtc_forensic_claim']=False
 hood['dtc_boundary_policy']='modeller_defined_from_v08_438_face_visual_envelope'

 body_ms=multiset(frame); hood_ms=multiset(hood)
 if body_ms+hood_ms!=original: raise RuntimeError('geometry conservation failed')
 if sum((body_ms&hood_ms).values())!=0: raise RuntimeError('body/hood overlap')
 if len(frame.data.polygons)+len(hood.data.polygons)!=original_faces or len(hood.data.polygons)!=438: raise RuntimeError('face conservation failed')

 st=bpy.data.collections.get('DTC_COMPONENT_STAGING_V08')
 if st: st.hide_viewport=True; st.hide_render=True
 sc=bpy.context.scene
 sc['dtc.asset_version']=ASSET_VERSION; sc['dtc.parent_asset']='DTC_SPRINT_A_v08_HOOD_COMPONENT_STAGE'; sc['dtc.parent_sha256']=V08_SHA
 sc['dtc.modelling_policy']='practical_modeller_defined_components'; sc['dtc.production_hood_cut']=True; sc['dtc.forensic_hood_boundary_claim']=False
 sc['dtc.rollback_collection']=ROLLBACK_COLL; sc['dtc.body_object']=BODY_NAME; sc['dtc.hood_object']=HOOD_NAME
 ns.out_blend.parent.mkdir(parents=True,exist_ok=True); bpy.ops.wm.save_as_mainfile(filepath=str(ns.out_blend)); out_sha=sha256(ns.out_blend)
 r={'schema':'dtc_sprint_a_v09_editable_hood_split_v1','status':'V09_NATIVE_BUILD_PASS','asset_version':ASSET_VERSION,'parent_sha256':V08_SHA,
    'policy':{'operation':'practical modelling split','forensic_boundary_claim':False,'boundary_source':'v08 438-face visual envelope','rollback_preserved':True},
    'source':{'frame_object':frame.name,'vertices':original_verts,'faces':original_faces,'work_meshes':16},
    'result':{'rollback_collection':ROLLBACK_COLL,'rollback_meshes':len(meshes(rb)),'body_object':BODY_NAME,'hood_object':HOOD_NAME,
              'body_faces':len(frame.data.polygons),'hood_faces':len(hood.data.polygons),'face_total':len(frame.data.polygons)+len(hood.data.polygons),
              'face_geometry_conserved_exactly':True,'body_hood_overlap_faces':0,'production_cut':True,'output_sha256':out_sha},
    'next_modelling_focus':['visually inspect/clean hood-body seam','cockpit position/proportions','fuel tank','cage/side panels','wing geometry/mounting']}
 ns.report.write_text(json.dumps(r,indent=2)+'\n'); print('DTC_SPRINT_A_V09_NATIVE_BUILD_PASS',json.dumps(r,sort_keys=True))
if __name__=='__main__': main()
