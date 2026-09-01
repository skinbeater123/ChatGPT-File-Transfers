#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import bpy
from mathutils import Vector

REAR_AXLE_X=-0.9337295293807983
CANDS={
 'tight': {'xmax':REAR_AXLE_X+0.10,'zmax':0.55,'ymax':0.62},
 'balanced': {'xmax':REAR_AXLE_X+0.18,'zmax':0.62,'ymax':0.66},
 'broad': {'xmax':REAR_AXLE_X+0.26,'zmax':0.70,'ymax':0.70},
}

def cli():
 p=argparse.ArgumentParser();p.add_argument('--blend',type=Path,required=True);p.add_argument('--out',type=Path,required=True);return p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
def look(o,t):o.rotation_euler=(Vector(t)-o.location).to_track_quat('-Z','Y').to_euler()
def world_centroid(o,p):return o.matrix_world@(sum((o.data.vertices[i].co for i in p.vertices),Vector())/len(p.vertices))
def world_bounds(o,ids):
 pts=[]
 for i in ids:
  p=o.data.polygons[i]
  pts.extend(o.matrix_world@o.data.vertices[j].co for j in p.vertices)
 if not pts:return None
 return {'min':[min(v[k] for v in pts) for k in range(3)],'max':[max(v[k] for v in pts) for k in range(3)]}
def all_bounds(objs):
 pts=[o.matrix_world@Vector(c) for o in objs if o.type=='MESH' and not o.hide_render for c in o.bound_box]
 return Vector((min(v.x for v in pts),min(v.y for v in pts),min(v.z for v in pts))),Vector((max(v.x for v in pts),max(v.y for v in pts),max(v.z for v in pts)))

def main():
 ns=cli();ns.out.mkdir(parents=True,exist_ok=True);bpy.ops.wm.open_mainfile(filepath=str(ns.blend));sc=bpy.context.scene
 work=bpy.data.collections['DTC_SPRINT_A_WORK'];body=bpy.data.objects['DTC_Body_LOD0']
 for c in bpy.data.collections:
  if c.name.startswith('SOURCE_') or c.name.startswith('DTC_SPRINT_A_BASELINE') or c.name=='DTC_COMPONENT_STAGING_V08':c.hide_render=True
 objs=[o for o in work.all_objects if o.type=='MESH' and not o.hide_render];lo,hi=all_bounds(objs);ctr=(lo+hi)*.5;r=max(hi-lo)*1.55
 camd=bpy.data.cameras.new('PreviewCam');cam=bpy.data.objects.new('PreviewCam',camd);sc.collection.objects.link(cam);sc.camera=cam;camd.lens=52
 sc.render.engine='BLENDER_WORKBENCH';sc.render.resolution_x=900;sc.render.resolution_y=630;sc.render.resolution_percentage=100;sc.render.image_settings.file_format='PNG'
 sh=sc.display.shading;sh.light='STUDIO';sh.color_type='MATERIAL';sh.show_shadows=True;sh.show_cavity=True;sh.cavity_type='WORLD';sh.background_type='WORLD';sh.background_color=(.04,.04,.04)
 red=bpy.data.materials.new('TANK_CANDIDATE');red.diffuse_color=(0.8,0.05,0.04,1);body.data.materials.append(red);redidx=len(body.data.materials)-1
 report={'schema':'dtc_v10_tank_candidate_preview_v1','rear_axle_x':REAR_AXLE_X,'candidates':{}}
 original=[p.material_index for p in body.data.polygons]
 for name,cfg in CANDS.items():
  ids=[]
  for p in body.data.polygons:
   q=world_centroid(body,p)
   if q.x<=cfg['xmax'] and q.z<=cfg['zmax'] and abs(q.y)<=cfg['ymax']:ids.append(p.index)
  for p,mi in zip(body.data.polygons,original):p.material_index=mi
  for i in ids:body.data.polygons[i].material_index=redidx
  report['candidates'][name]={'rule':cfg,'faces':len(ids),'bounds':world_bounds(body,ids),'indices':ids}
  views={'side':(ctr.x,ctr.y+r*1.4,ctr.z+r*.25),'rear3q':(ctr.x-r,ctr.y+r*.72,ctr.z+r*.44)}
  for vn,loc in views.items():
   cam.location=loc;look(cam,ctr);sc.render.filepath=str(ns.out/f'{name}_{vn}.png');bpy.ops.render.render(write_still=True)
 for p,mi in zip(body.data.polygons,original):p.material_index=mi
 (ns.out/'tank_candidates.json').write_text(json.dumps(report,indent=2));print('DTC_V10_TANK_PREVIEW_PASS',json.dumps({k:v['faces'] for k,v in report['candidates'].items()}))
if __name__=='__main__':main()
