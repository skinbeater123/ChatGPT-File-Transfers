from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import bpy
from mathutils import Vector
SOURCE='SOURCE_BIGANT_A01_LOCKED';WORK='DTC_SPRINT_A_WORK';BASES=tuple(f'DTC_SPRINT_A_BASELINE_V0{i}' for i in range(1,8));STAGE='DTC_COMPONENT_STAGING_V08';BROAD='dtc_hood_candidate_b';CORE='dtc_hood_reference_core';VERSION='DTC_SPRINT_A_v08_HOOD_COMPONENT_STAGE';BROAD_N=438;CORE_N=171
W={'WheelLF_LOD0':(1.2359206676483154,.7039546370506287,-.32582324743270874),'WheelRF_LOD0':(1.2359206676483154,-.7039546370506287,-.32582324743270874),'WheelLR_LOD0':(-.9337295293807983,.6705295443534851,-.3061189353466034),'WheelRR_LOD0':(-.9337295293807983,-.6705295443534851,-.3061189353466034)}
def cli():p=argparse.ArgumentParser();p.add_argument('--pass-file',type=Path,required=True);p.add_argument('--json',dest='out',type=Path);a=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [];return p.parse_args(a)
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
def old(b,n):a=[o for o in meshes(b) if o.get('dtc.source_object')==n];assert len(a)==1;return a[0]
def maxerr(a,b):assert len(a)==len(b);return max(((x-y).length for x,y in zip(a,b)),default=0.)
def main():
 ns=cli();ns.pass_file.unlink(missing_ok=True);sc=bpy.context.scene;s=coll(SOURCE);w=coll(WORK);bases=[coll(x) for x in BASES];b7=bases[-1];g=coll(STAGE)
 assert sc.get('dtc.asset_version')==VERSION;assert [len(meshes(x)) for x in(s,w,*bases)]==[92,16,16,16,16,16,16,16,16];assert len(meshes(g))==2;assert b7.get('dtc.rollback_representation')=='WORLD_BAKED_GEOMETRY_PLUS_ORIGINAL_MATRIX_METADATA'
 frame=one(w,'Frame_LOD0');ba=frame.data.attributes.get(BROAD);ca=frame.data.attributes.get(CORE);assert ba and ca;broad=[i for i,d in enumerate(ba.data) if d.value];core=[i for i,d in enumerate(ca.data) if d.value];assert len(broad)==BROAD_N and len(core)==CORE_N and set(core)<=set(broad)
 errs={}
 for o in meshes(w):
  e=maxerr(pts(o),pts(old(b7,o.name)));errs[o.name]=e;assert e<2e-6,(o.name,e);assert len(o.data.polygons)==len(old(b7,o.name).data.polygons)
 st={o.name:len(o.data.polygons) for o in meshes(g)};assert st=={'DTC_HOOD_STAGE_ENVELOPE':BROAD_N,'DTC_HOOD_REFERENCE_CORE_STAGE':CORE_N},st
 piv={}
 for p,t in W.items():o=one(w,p);e=(o.matrix_world.translation-Vector(t)).length;piv[p]=e;assert e<2e-6
 r={'schema':'dtc_sprint_a_v08_fresh_reload_validation_v1','status':'V08_FRESH_RELOAD_PASS','asset_version':VERSION,'work_geometry_changed':False,'max_work_geometry_error_m':max(errs.values()),'broad_faces':len(broad),'reference_core_faces':len(core),'stage_objects':st,'wheel_pivot_errors_m':piv,'production_cut':False}
 if ns.out:ns.out.write_text(json.dumps(r,indent=2)+'\n')
 ns.pass_file.write_text('V08_FRESH_RELOAD_PASS\n');print('V08_FRESH_RELOAD_PASS',json.dumps(r,sort_keys=True))
if __name__=='__main__':main()
