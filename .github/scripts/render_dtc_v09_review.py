#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import bpy
from mathutils import Vector

def cli():
    p=argparse.ArgumentParser(); p.add_argument('--blend',type=Path,required=True); p.add_argument('--out',type=Path,required=True)
    a=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    return p.parse_args(a)

def look_at(cam, target):
    cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()

def bounds(objs):
    pts=[]
    for o in objs:
        if o.type!='MESH' or o.hide_render: continue
        for c in o.bound_box: pts.append(o.matrix_world@Vector(c))
    lo=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)))
    hi=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)))
    return lo,hi

def main():
    ns=cli(); ns.out.mkdir(parents=True,exist_ok=True); bpy.ops.wm.open_mainfile(filepath=str(ns.blend))
    sc=bpy.context.scene
    for c in bpy.data.collections:
        if c.name.startswith('SOURCE_') or c.name.startswith('DTC_SPRINT_A_BASELINE') or c.name=='DTC_COMPONENT_STAGING_V08':
            c.hide_render=True
    work=bpy.data.collections.get('DTC_SPRINT_A_WORK')
    objs=[o for o in work.all_objects if o.type=='MESH' and not o.hide_render]
    lo,hi=bounds(objs); ctr=(lo+hi)*0.5; span=hi-lo
    # ground
    bpy.ops.mesh.primitive_plane_add(size=max(span.x,span.y)*4, location=(ctr.x,ctr.y,lo.z-0.03))
    g=bpy.context.object; g.name='REVIEW_GROUND'
    mat=bpy.data.materials.new('Ground'); mat.diffuse_color=(0.12,0.12,0.12,1); g.data.materials.append(mat)
    # camera
    camd=bpy.data.cameras.new('ReviewCamera'); cam=bpy.data.objects.new('ReviewCamera',camd); sc.collection.objects.link(cam); sc.camera=cam; camd.lens=52
    # lighting
    world=sc.world or bpy.data.worlds.new('World'); sc.world=world; world.color=(0.055,0.055,0.055)
    for name,loc,energy,size in [('Key',(ctr.x+4,ctr.y-5,ctr.z+5),1800,4),('Fill',(ctr.x-2,ctr.y+5,ctr.z+3),1100,5),('Top',(ctr.x,ctr.y,ctr.z+7),1300,3)]:
        ld=bpy.data.lights.new(name,'AREA'); ld.energy=energy; ld.shape='DISK'; ld.size=size; o=bpy.data.objects.new(name,ld); sc.collection.objects.link(o); o.location=loc; look_at(o,ctr)
    sc.render.engine='BLENDER_EEVEE_NEXT'; sc.render.resolution_x=1000; sc.render.resolution_y=700; sc.render.resolution_percentage=100
    sc.render.image_settings.file_format='PNG'; sc.render.film_transparent=False
    r=max(span.x,span.y,span.z)*1.65
    views={
      'front_3q':(ctr.x+r,ctr.y-r*0.75,ctr.z+r*0.52),
      'left_side':(ctr.x,ctr.y+r*1.45,ctr.z+r*0.33),
      'right_side':(ctr.x,ctr.y-r*1.45,ctr.z+r*0.33),
      'rear_3q':(ctr.x-r,ctr.y+r*0.75,ctr.z+r*0.52),
      'top_3q':(ctr.x+r*0.4,ctr.y-r*0.3,ctr.z+r*1.65),
    }
    for name,loc in views.items():
        cam.location=loc; look_at(cam,ctr); sc.render.filepath=str(ns.out/f'{name}.png'); bpy.ops.render.render(write_still=True)
    info={'asset_version':sc.get('dtc.asset_version'),'bounds_min':list(lo),'bounds_max':list(hi),'objects':[{'name':o.name,'loc':list(o.matrix_world.translation),'bbox_min':list(min((o.matrix_world@Vector(c) for c in o.bound_box),key=lambda v:v.z))} for o in objs]}
    (ns.out/'review_info.json').write_text(json.dumps(info,indent=2))
    print('DTC_V09_REVIEW_RENDER_PASS')
if __name__=='__main__': main()
