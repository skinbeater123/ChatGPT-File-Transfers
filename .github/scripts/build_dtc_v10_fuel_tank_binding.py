#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,struct,sys
from pathlib import Path
import bpy
from mathutils import Vector

V09_SHA='b746681f99acce179ffdf60faadf2ee5337d0b5936745f91a0e265e5071765fa'
WORK='DTC_SPRINT_A_WORK';ROLLBACK='DTC_SPRINT_A_BASELINE_V09';ASSET='DTC_SPRINT_A_v10_FUEL_TANK_REAR_BINDING'
TANK_PREFIX='BumperRear_DMG0_LOD0__07';BUMPER_PREFIX='BumperRear_DMG0_LOD0__08';TANK='DTC_FuelTank_RearShell';BUMPER='DTC_RearBumper';LOC='mount_fuel_tank_rear'
W={'WheelLF_LOD0':(1.2359206676483154,.7039546370506287,-.32582324743270874),'WheelRF_LOD0':(1.2359206676483154,-.7039546370506287,-.32582324743270874),'WheelLR_LOD0':(-.9337295293807983,.6705295443534851,-.3061189353466034),'WheelRR_LOD0':(-.9337295293807983,-.6705295443534851,-.3061189353466034)}

def cli():
 p=argparse.ArgumentParser();p.add_argument('--blend',type=Path,required=True);p.add_argument('--out-blend',type=Path,required=True);p.add_argument('--report',type=Path,required=True);return p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for c in iter(lambda:f.read(1<<20),b''):h.update(c)
 return h.hexdigest()
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
 if len(a)!=1:raise RuntimeError((p,[x.name for x in a]))
 return a[0]
def digest(o):
 h=hashlib.sha256()
 for v in o.data.vertices:
  p=o.matrix_world@v.co;h.update(struct.pack('<3d',p.x,p.y,p.z))
 for f in o.data.polygons:
  h.update(struct.pack('<I',len(f.vertices)))
  for i in f.vertices:h.update(struct.pack('<I',i))
 return h.hexdigest()
def bounds(o):
 p=[o.matrix_world@v.co for v in o.data.vertices];lo=Vector(tuple(min(x[k] for x in p) for k in range(3)));hi=Vector(tuple(max(x[k] for x in p) for k in range(3)));return lo,hi
def backup(work):
 if bpy.data.collections.get(ROLLBACK):raise RuntimeError('v09 rollback exists')
 b=bpy.data.collections.new(ROLLBACK);bpy.context.scene.collection.children.link(b)
 for o in meshes(work):
  q=o.copy();q.data=o.data.copy();q.name='V09_'+o.name;q.data.name=q.name+'_Mesh';q.hide_select=True;b.objects.link(q)
 b.hide_viewport=True;b.hide_render=True;b['dtc.locked_backup']=True;b['dtc.rollback_role']='COMPLETE_V09_WORK_ROLLBACK';b['dtc.rollback_representation']='INDEPENDENT_MESH_DATABLOCKS_SAME_TRANSFORMS';return b

def main():
 ns=cli()
 if sha(ns.blend)!=V09_SHA:raise RuntimeError('v09 hash gate')
 bpy.ops.wm.open_mainfile(filepath=str(ns.blend));sc=bpy.context.scene;work=bpy.data.collections.get(WORK)
 if not work:raise RuntimeError('work collection missing')
 if sc.get('dtc.asset_version')!='DTC_SPRINT_A_v09_EDITABLE_HOOD_SPLIT':raise RuntimeError(sc.get('dtc.asset_version'))
 tank=one(work,TANK_PREFIX);bumper=one(work,BUMPER_PREFIX)
 if len(tank.data.polygons)!=418 or len(bumper.data.polygons)!=455:raise RuntimeError('rear object census changed')
 before={o.name:digest(o) for o in meshes(work)};rb=backup(work)
 tlo,thi=bounds(tank);centre=(tlo+thi)*.5
 tank.name=TANK;tank.data.name=TANK+'_Mesh';tank['dtc.semantic_id']='FUEL_TANK_REAR';tank['dtc.damage']='WOO_CANON_STAGED_REAR_TANK_CRUSH';tank['dtc.detach_gameplay']='DISABLED_WOO_NOT_DEMONSTRATED';tank['dtc.source_art_node_role']='Big Ant rear body damage group';tank['dtc.editable']=True
 bumper.name=BUMPER;bumper.data.name=BUMPER+'_Mesh';bumper['dtc.semantic_id']='BUMPER_REAR';bumper['dtc.damage']='DTC_PROVISIONAL';bumper['dtc.detach_gameplay']='DISABLED_UNTIL_DAMAGE_GATE'
 e=bpy.data.objects.get(LOC)
 if e:raise RuntimeError('tank locator exists')
 e=bpy.data.objects.new(LOC,None);work.objects.link(e);e.empty_display_type='SPHERE';e.empty_display_size=.08;e.location=centre;e['dtc.semantic_id']='FUEL_TANK_REAR';e['dtc.physics_authority']='NONE_G2_003_OWNS_SIMULATION';e['dtc.locator_role']='visual_damage_component_reference'
 after={o.name:digest(o) for o in meshes(work)}
 # Compare digests independent of renamed keys.
 if sorted(before.values())!=sorted(after.values()):raise RuntimeError('mesh geometry changed during semantic binding')
 for p,t in W.items():
  o=one(work,p)
  if (o.matrix_world.translation-Vector(t)).length>2e-6:raise RuntimeError((p,o.matrix_world.translation,t))
 sc['dtc.asset_version']=ASSET;sc['dtc.parent_asset']='DTC_SPRINT_A_v09_EDITABLE_HOOD_SPLIT';sc['dtc.parent_sha256']=V09_SHA;sc['dtc.v10_scope']='rear fuel tank/rear bumper semantic correction only';sc['dtc.production_hood_cut']=True;sc['dtc.fuel_tank_rear_bound']=True;sc['dtc.physics_authority']='NONE_G2_003_OWNS_SIMULATION'
 ns.out_blend.parent.mkdir(parents=True,exist_ok=True);bpy.ops.wm.save_as_mainfile(filepath=str(ns.out_blend));outsha=sha(ns.out_blend)
 r={'schema':'dtc_sprint_a_v10_fuel_tank_rear_binding_v1','status':'V10_NATIVE_BUILD_PASS','asset_version':ASSET,'parent_sha256':V09_SHA,'work_meshes':len(meshes(work)),'rollback_v09_meshes':len(meshes(rb)),'geometry_changed':False,'tank':{'object':TANK,'faces':len(tank.data.polygons),'vertices':len(tank.data.vertices),'bounds_min':list(tlo),'bounds_max':list(thi),'locator':LOC,'locator_world':list(centre),'detach_gameplay':False},'rear_bumper':{'object':BUMPER,'faces':len(bumper.data.polygons),'vertices':len(bumper.data.vertices)},'hood':{'object':'DTC_Hood','faces':len(bpy.data.objects['DTC_Hood'].data.polygons)},'wheel_pivots_preserved':True,'output_sha256':outsha,'next_gate':'body/panel and chassis visual refinement; no cockpit/wing relocation justified by current reference comparison'}
 ns.report.write_text(json.dumps(r,indent=2)+'\n');print('DTC_SPRINT_A_V10_NATIVE_BUILD_PASS',json.dumps(r,sort_keys=True))
if __name__=='__main__':main()
