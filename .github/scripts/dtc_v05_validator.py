"""Fresh-reload validator for DTC_SPRINT_A_v05_BEULAH_SHELL."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import bpy
from mathutils import Vector
SOURCE="SOURCE_BIGANT_A01_LOCKED";WORK="DTC_SPRINT_A_WORK";BASES=("DTC_SPRINT_A_BASELINE_V01","DTC_SPRINT_A_BASELINE_V02","DTC_SPRINT_A_BASELINE_V03","DTC_SPRINT_A_BASELINE_V04");BASIS="DTC_X_FORWARD_Y_LEFT_Z_UP_METRES_NORMALIZED";VERSION="DTC_SPRINT_A_v05_BEULAH_SHELL"
W={"WheelLF_LOD0":(1.2359206676483154,.7039546370506287,-.32582324743270874),"WheelRF_LOD0":(1.2359206676483154,-.7039546370506287,-.32582324743270874),"WheelLR_LOD0":(-.9337295293807983,.6705295443534851,-.3061189353466034),"WheelRR_LOD0":(-.9337295293807983,-.6705295443534851,-.3061189353466034)}
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
def pts(o):return[o.matrix_world@v.co for v in o.data.vertices]
def old(b4,n):a=[o for o in meshes(b4) if o.get('dtc.source_object')==n];assert len(a)==1,(n,[o.name for o in a]);return a[0]
def err(a,b):assert len(a)==len(b);return max(((x-y).length for x,y in zip(a,b)),default=0.)
def main():
 ns=cli();ns.pass_file.unlink(missing_ok=True);sc=bpy.context.scene;s=coll(SOURCE);w=coll(WORK);b1,b2,b3,b4=[coll(x) for x in BASES]
 assert sc.get('dtc.asset_version')==VERSION,sc.get('dtc.asset_version');assert sc.get('dtc.authoring_basis')==BASIS;assert w.get('dtc.authoring_basis')==BASIS;assert [len(meshes(c)) for c in(s,w,b1,b2,b3,b4)]==[92,16,16,16,16,16];assert b4.get('dtc.rollback_representation')=='WORLD_BAKED_GEOMETRY_PLUS_ORIGINAL_MATRIX_METADATA';assert not({id(o.data) for o in meshes(w)}&{id(o.data) for o in meshes(b4)})
 f=one(w,'Frame_LOD0');f0=old(b4,f.name);sh=[(b-a).length for a,b in zip(pts(f0),pts(f))];active=[x for x in sh if x>1e-6];changed=len(active);mx=max(active);mean=sum(active)/changed;assert changed==3892,changed;assert abs(mx-.021408345181858468)<5e-6,mx;assert abs(mean-.0101426986895303)<5e-6,mean
 pe={}
 for o in meshes(w):
  if o is f:continue
  e=err(pts(o),pts(old(b4,o.name)));pe[o.name]=e;assert e<2e-6,(o.name,e)
 piv={}
 for p,t in W.items():
  o=one(w,p);e=(o.matrix_world.translation-Vector(t)).length;piv[p]=e;assert e<2e-6,(p,e);orig=old(b4,o.name).get('dtc.original_origin_m');assert orig is not None;assert max(abs(float(orig[i])-t[i]) for i in range(3))<3e-6,(p,orig)
 flags=sorted(o.name for o in meshes(w) if o.get('dtc.v05_modified') is True);assert flags==[f.name],flags
 r={'schema':'dtc_sprint_a_v05_fresh_reload_validation_v1','status':'V05_FRESH_RELOAD_PASS','asset_version':VERSION,'authoring_basis':BASIS,'work_meshes':16,'v04_rollback_meshes':16,'changed_meshes':flags,'changed_vertices':changed,'max_vertex_shift_m':mx,'mean_changed_vertex_shift_m':mean,'max_protected_geometry_error_m':max(pe.values()),'wheel_pivot_errors_m':piv,'rollback_representation':b4.get('dtc.rollback_representation')}
 if ns.json_out:ns.json_out.write_text(json.dumps(r,indent=2)+'\n')
 ns.pass_file.write_text('V05_FRESH_RELOAD_PASS\n');print('V05_FRESH_RELOAD_PASS',json.dumps(r,sort_keys=True))
if __name__=='__main__':main()
