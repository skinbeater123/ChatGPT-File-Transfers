#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import bpy
from mathutils import Vector

def cli():
 p=argparse.ArgumentParser();p.add_argument('--blend',type=Path,required=True);p.add_argument('--out',type=Path,required=True);return p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
def look(o,t):o.rotation_euler=(Vector(t)-o.location).to_track_quat('-Z','Y').to_euler()
def centroid(o,p):return o.matrix_world@(sum((o.data.vertices[i].co for i in p.vertices),Vector())/len(p.vertices))
def normal(o,p):return (o.matrix_world.to_3x3()@p.normal).normalized()
def area_world(o,p):
 vs=[o.matrix_world@o.data.vertices[i].co for i in p.vertices]
 if len(vs)<3:return 0.0
 a=0.0
 for i in range(1,len(vs)-1):a+=((vs[i]-vs[0]).cross(vs[i+1]-vs[0])).length*.5
 return a
def allb(objs):
 pts=[o.matrix_world@Vector(c) for o in objs if o.type=='MESH' and not o.hide_render for c in o.bound_box]
 return Vector((min(v.x for v in pts),min(v.y for v in pts),min(v.z for v in pts))),Vector((max(v.x for v in pts),max(v.y for v in pts),max(v.z for v in pts)))

def select(body,variant):
 out=[]
 for p in body.data.polygons:
  c=centroid(body,p);n=normal(body,p);a=area_world(body,p)
  if not (-1.05<=c.x<=-0.28 and 0.16<=c.z<=0.86 and abs(c.y)>=0.24):continue
  if abs(n.y)<variant['ny']:continue
  if a<variant['area']:continue
  out.append(p.index)
 return out

def main():
 ns=cli();ns.out.mkdir(parents=True,exist_ok=True);bpy.ops.wm.open_mainfile(filepath=str(ns.blend));sc=bpy.context.scene;work=bpy.data.collections['DTC_SPRINT_A_WORK'];body=bpy.data.objects['DTC_Body_LOD0']
 for c in bpy.data.collections:
  if c.name.startswith('SOURCE_') or c.name.startswith('DTC_SPRINT_A_BASELINE') or c.name=='DTC_COMPONENT_STAGING_V08':c.hide_render=True
 objs=[o for o in work.all_objects if o.type=='MESH' and not o.hide_render];lo,hi=allb(objs);ctr=(lo+hi)*.5;r=max(hi-lo)*1.55
 camd=bpy.data.cameras.new('PanelPreviewCam');cam=bpy.data.objects.new('PanelPreviewCam',camd);sc.collection.objects.link(cam);sc.camera=cam;camd.lens=52
 sc.render.engine='BLENDER_WORKBENCH';sc.render.resolution_x=900;sc.render.resolution_y=630;sc.render.resolution_percentage=100;sc.render.image_settings.file_format='PNG'
 sh=sc.display.shading;sh.light='STUDIO';sh.color_type='MATERIAL';sh.show_shadows=True;sh.show_cavity=True;sh.cavity_type='WORLD';sh.background_type='WORLD';sh.background_color=(.04,.04,.04)
 red=bpy.data.materials.new('PANEL_SELECTION');red.diffuse_color=(.9,.03,.02,1);body.data.materials.append(red);ri=len(body.data.materials)-1;orig=[p.material_index for p in body.data.polygons]
 variants={'strict':{'ny':.78,'area':.0040},'medium':{'ny':.65,'area':.0022},'broad':{'ny':.52,'area':.0012}}
 rep={'schema':'dtc_v11_rear_panel_selection_preview_v1','variants':{}}
 for name,v in variants.items():
  ids=select(body,v)
  for p,mi in zip(body.data.polygons,orig):p.material_index=mi
  for i in ids:body.data.polygons[i].material_index=ri
  verts=sorted({vi for i in ids for vi in body.data.polygons[i].vertices})
  rep['variants'][name]={'face_count':len(ids),'vertex_count':len(verts),'face_indices':ids,'vertex_indices':verts,'criteria':v}
  for vn,loc in {'side':(ctr.x,ctr.y+r*1.4,ctr.z+r*.25),'rear3q':(ctr.x-r,ctr.y+r*.72,ctr.z+r*.44)}.items():cam.location=loc;look(cam,ctr);sc.render.filepath=str(ns.out/f'{name}_{vn}.png');bpy.ops.render.render(write_still=True)
 for p,mi in zip(body.data.polygons,orig):p.material_index=mi
 (ns.out/'rear_panel_selection.json').write_text(json.dumps(rep,indent=2));print('DTC_V11_PANEL_SELECTION_PREVIEW_PASS',json.dumps({k:v['face_count'] for k,v in rep['variants'].items()}))
if __name__=='__main__':main()
