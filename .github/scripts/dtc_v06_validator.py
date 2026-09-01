"""Fresh-reload validator for DTC_SPRINT_A_v06_BEULAH_FRONT_SHELL."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import bpy
from mathutils import Vector
SOURCE="SOURCE_BIGANT_A01_LOCKED";WORK="DTC_SPRINT_A_WORK";BASES=("DTC_SPRINT_A_BASELINE_V01","DTC_SPRINT_A_BASELINE_V02","DTC_SPRINT_A_BASELINE_V03","DTC_SPRINT_A_BASELINE_V04","DTC_SPRINT_A_BASELINE_V05");BASIS="DTC_X_FORWARD_Y_LEFT_Z_UP_METRES_NORMALIZED";VERSION="DTC_SPRINT_A_v06_BEULAH_FRONT_SHELL";LOWER=.15;REARWARD=.03;NARROW=.06;X0=0.;XRANGE=1.45;Z0=.02;ZRANGE=.38
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
def old(b,n):a=[o for o in meshes(b) if o.get('dtc.source_object')==n];assert len(a)==1,(n,[o.name for o in a]);return a[0]
def pts(o):return[o.matrix_world@v.co for v in o.data.vertices]
def ss(x):x=max(0.,min(1.,x));return x*x*(3-2*x)
def expected(p,cy):
 wx=ss((p.x-X0)/XRANGE);wz=ss((p.z-Z0)/ZRANGE);q=wx*wz;return Vector((p.x-REARWARD*q,cy+(p.y-cy)*(1-NARROW*q),p.z-LOWER*q))
def maxerr(a,b):assert len(a)==len(b);return max(((x-y).length for x,y in zip(a,b)),default=0.)
def main():
 ns=cli();ns.pass_file.unlink(missing_ok=True);sc=bpy.context.scene;s=coll(SOURCE);w=coll(WORK);bases=[coll(x) for x in BASES];b5=bases[-1]
 assert sc.get('dtc.asset_version')==VERSION,sc.get('dtc.asset_version');assert sc.get('dtc.authoring_basis')==BASIS;assert w.get('dtc.authoring_basis')==BASIS;assert [len(meshes(c)) for c in (s,w,*bases)]==[92,16,16,16,16,16,16];assert s.get('dtc.locked_source') is True;assert all(c.get('dtc.locked_backup') is True for c in bases);assert b5.get('dtc.rollback_representation')=='WORLD_BAKED_GEOMETRY_PLUS_ORIGINAL_MATRIX_METADATA';assert not({id(o.data) for o in meshes(w)}&{id(o.data) for o in meshes(b5)})
 frame=one(w,'Frame_LOD0');before=pts(old(b5,frame.name));after=pts(frame);assert len(before)==len(after);ys=[p.y for p in before];cy=(min(ys)+max(ys))*.5;exp=[expected(p,cy) for p in before];formula_error=maxerr(exp,after);assert formula_error<2e-6,formula_error
 shifts=[(b-a).length for a,b in zip(before,after)];active=[x for x in shifts if x>1e-6];changed=len(active);mx=max(active);mean=sum(active)/changed;assert mx<.08,mx
 protected={}
 for o in meshes(w):
  if o is frame:continue
  e=maxerr(pts(o),pts(old(b5,o.name)));protected[o.name]=e;assert e<2e-6,(o.name,e)
 piv={}
 for p,t in W.items():
  o=one(w,p);e=(o.matrix_world.translation-Vector(t)).length;piv[p]=e;assert e<2e-6,(p,e);orig=old(b5,o.name).get('dtc.original_origin_m');assert orig is not None;assert max(abs(float(orig[i])-t[i]) for i in range(3))<3e-6,(p,orig)
 flags=sorted(o.name for o in meshes(w) if o.get('dtc.v06_modified') is True);assert flags==[frame.name],flags
 r={'schema':'dtc_sprint_a_v06_fresh_reload_validation_v1','status':'V06_FRESH_RELOAD_PASS','asset_version':VERSION,'authoring_basis':BASIS,'work_meshes':16,'v05_rollback_meshes':16,'changed_meshes':flags,'native_changed_vertices':changed,'native_max_vertex_shift_m':mx,'native_mean_changed_vertex_shift_m':mean,'formula_max_error_m':formula_error,'max_protected_geometry_error_m':max(protected.values()),'wheel_pivot_errors_m':piv,'rollback_representation':b5.get('dtc.rollback_representation')}
 if ns.json_out:ns.json_out.write_text(json.dumps(r,indent=2)+'\n')
 ns.pass_file.write_text('V06_FRESH_RELOAD_PASS\n');print('V06_FRESH_RELOAD_PASS',json.dumps(r,sort_keys=True))
if __name__=='__main__':main()
