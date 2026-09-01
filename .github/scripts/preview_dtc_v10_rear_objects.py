#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import bpy
from mathutils import Vector

def cli():
 p=argparse.ArgumentParser();p.add_argument('--blend',type=Path,required=True);p.add_argument('--out',type=Path,required=True);return p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
def look(o,t):o.rotation_euler=(Vector(t)-o.location).to_track_quat('-Z','Y').to_euler()
def wb(o):
 pts=[o.matrix_world@Vector(c) for c in o.bound_box];return {'min':[min(v[k] for v in pts) for k in range(3)],'max':[max(v[k] for v in pts) for k in range(3)]}
def allb(objs):
 pts=[o.matrix_world@Vector(c) for o in objs if o.type=='MESH' and not o.hide_render for c in o.bound_box]
 return Vector((min(v.x for v in pts),min(v.y for v in pts),min(v.z for v in pts))),Vector((max(v.x for v in pts),max(v.y for v in pts),max(v.z for v in pts)))
def main():
 ns=cli();ns.out.mkdir(parents=True,exist_ok=True);bpy.ops.wm.open_mainfile(filepath=str(ns.blend));sc=bpy.context.scene;work=bpy.data.collections['DTC_SPRINT_A_WORK']
 for c in bpy.data.collections:
  if c.name.startswith('SOURCE_') or c.name.startswith('DTC_SPRINT_A_BASELINE') or c.name=='DTC_COMPONENT_STAGING_V08':c.hide_render=True
 objs=[o for o in work.all_objects if o.type=='MESH' and not o.hide_render];rear=sorted([o for o in objs if o.name.startswith('BumperRear_DMG0_LOD0')],key=lambda o:o.name)
 if len(rear)!=2:raise RuntimeError([o.name for o in rear])
 mats=[]
 for name,col in [('REAR_A',(0.85,0.04,0.03,1)),('REAR_B',(0.03,0.20,0.95,1))]:m=bpy.data.materials.new(name);m.diffuse_color=col;mats.append(m)
 originals={o.name:list(o.data.materials) for o in rear}
 for o,m in zip(rear,mats):o.data.materials.clear();o.data.materials.append(m)
 lo,hi=allb(objs);ctr=(lo+hi)*.5;r=max(hi-lo)*1.55
 camd=bpy.data.cameras.new('RearRoleCam');cam=bpy.data.objects.new('RearRoleCam',camd);sc.collection.objects.link(cam);sc.camera=cam;camd.lens=52
 sc.render.engine='BLENDER_WORKBENCH';sc.render.resolution_x=900;sc.render.resolution_y=630;sc.render.resolution_percentage=100;sc.render.image_settings.file_format='PNG'
 sh=sc.display.shading;sh.light='STUDIO';sh.color_type='MATERIAL';sh.show_shadows=True;sh.show_cavity=True;sh.cavity_type='WORLD';sh.background_type='WORLD';sh.background_color=(.04,.04,.04)
 for name,loc in {'side':(ctr.x,ctr.y+r*1.4,ctr.z+r*.25),'rear3q':(ctr.x-r,ctr.y+r*.72,ctr.z+r*.44)}.items():cam.location=loc;look(cam,ctr);sc.render.filepath=str(ns.out/f'rear_roles_{name}.png');bpy.ops.render.render(write_still=True)
 report={'schema':'dtc_v10_rear_object_role_preview_v1','objects':[{'name':o.name,'faces':len(o.data.polygons),'vertices':len(o.data.vertices),'world_bounds':wb(o)} for o in rear]}
 (ns.out/'rear_roles.json').write_text(json.dumps(report,indent=2));print('DTC_V10_REAR_ROLE_PREVIEW_PASS',json.dumps(report))
if __name__=='__main__':main()
