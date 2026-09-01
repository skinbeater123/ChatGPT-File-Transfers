"""Fresh-reload validator for DTC_SPRINT_A_v07_HOOD_BOUNDARY_BINDING."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import bpy
from mathutils import Vector
SOURCE='SOURCE_BIGANT_A01_LOCKED';WORK='DTC_SPRINT_A_WORK';BASES=tuple(f'DTC_SPRINT_A_BASELINE_V0{i}' for i in range(1,7));GUIDES='DTC_SEMANTIC_GUIDES_V07';ATTR='dtc_hood_candidate_b';VERSION='DTC_SPRINT_A_v07_HOOD_BOUNDARY_BINDING';BASIS='DTC_X_FORWARD_Y_LEFT_Z_UP_METRES_NORMALIZED';EXPECTED=438
XMIN=.05;XMAX=1.45;ZMIN=-.15;YMAX=.50;MIN_AREA=.0005
W={'WheelLF_LOD0':(1.2359206676483154,.7039546370506287,-.32582324743270874),'WheelRF_LOD0':(1.2359206676483154,-.7039546370506287,-.32582324743270874),'WheelLR_LOD0':(-.9337295293807983,.6705295443534851,-.3061189353466034),'WheelRR_LOD0':(-.9337295293807983,-.6705295443534851,-.3061189353466034)}
def cli():
 p=argparse.ArgumentParser();p.add_argument('--pass-file',type=Path,required=True);p.add_argument('--json',dest='json_out',type=Path);a=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [];return p.parse_args(a)
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
def old(b,n):a=[o for o in meshes(b) if o.get('dtc.source_object')==n];assert len(a)==1,(n,[o.name for o in a]);return a[0]
def pts(o):return[o.matrix_world@v.co for v in o.data.vertices]
def maxerr(a,b):assert len(a)==len(b);return max(((x-y).length for x,y in zip(a,b)),default=0.)
def selected(o):
 M=o.matrix_world;out=[]
 for p in o.data.polygons:
  assert len(p.vertices)==3,(p.index,len(p.vertices));a,b,c=[M@o.data.vertices[i].co for i in p.vertices];q=(a+b+c)/3.;area=(b-a).cross(c-a).length*.5
  if XMIN<=q.x<=XMAX and q.z>=ZMIN and abs(q.y)<=YMAX and area>MIN_AREA:out.append(p.index)
 return out
def main():
 ns=cli();ns.pass_file.unlink(missing_ok=True);sc=bpy.context.scene;s=coll(SOURCE);w=coll(WORK);bases=[coll(x) for x in BASES];b6=bases[-1];g=coll(GUIDES)
 assert sc.get('dtc.asset_version')==VERSION;assert sc.get('dtc.authoring_basis')==BASIS;assert w.get('dtc.authoring_basis')==BASIS
 assert [len(meshes(c)) for c in (s,w,*bases)]==[92,16,16,16,16,16,16,16];assert len(meshes(g))==1;assert b6.get('dtc.rollback_representation')=='WORLD_BAKED_GEOMETRY_PLUS_ORIGINAL_MATRIX_METADATA'
 frame=one(w,'Frame_LOD0');sel=selected(frame);assert len(sel)==EXPECTED,len(sel);attr=frame.data.attributes.get(ATTR);assert attr is not None;assert attr.domain=='FACE';assert attr.data_type=='BOOLEAN';bound=[i for i,d in enumerate(attr.data) if d.value];assert bound==sel,(len(bound),len(sel))
 errs={}
 for o in meshes(w):
  e=maxerr(pts(o),pts(old(b6,o.name)));errs[o.name]=e;assert e<2e-6,(o.name,e);assert len(o.data.polygons)==len(old(b6,o.name).data.polygons)
 piv={}
 for p,t in W.items():
  o=one(w,p);e=(o.matrix_world.translation-Vector(t)).length;piv[p]=e;assert e<2e-6,(p,e)
 guide=meshes(g)[0];assert guide.name.startswith('DTC_HOOD_BOUNDARY_CANDIDATE_B_GUIDE');assert len(guide.data.polygons)==EXPECTED;assert guide.get('dtc.guide_only') is True
 r={'schema':'dtc_sprint_a_v07_fresh_reload_validation_v1','status':'V07_FRESH_RELOAD_PASS','asset_version':VERSION,'work_meshes':16,'v06_rollback_meshes':16,'hood_attribute':ATTR,'hood_faces':len(sel),'guide_faces':len(guide.data.polygons),'max_work_geometry_error_m':max(errs.values()),'wheel_pivot_errors_m':piv,'geometry_changed':False,'rollback_representation':b6.get('dtc.rollback_representation'),'ratbag_external_hood_mount':'OPEN'}
 if ns.json_out:ns.json_out.write_text(json.dumps(r,indent=2)+'\n')
 ns.pass_file.write_text('V07_FRESH_RELOAD_PASS\n');print('V07_FRESH_RELOAD_PASS',json.dumps(r,sort_keys=True))
if __name__=='__main__':main()
