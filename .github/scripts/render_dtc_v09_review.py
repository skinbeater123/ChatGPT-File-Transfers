#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import bpy
from mathutils import Vector

def cli():
    p=argparse.ArgumentParser(); p.add_argument('--blend',type=Path,required=True); p.add_argument('--out',type=Path,required=True)
    return p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])

def look_at(obj,target): obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
def bounds(objs):
    pts=[o.matrix_world@Vector(c) for o in objs if o.type=='MESH' and not o.hide_render for c in o.bound_box]
    return Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts))),Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)))

def main():
    ns=cli(); ns.out.mkdir(parents=True,exist_ok=True); bpy.ops.wm.open_mainfile(filepath=str(ns.blend)); sc=bpy.context.scene
    for c in bpy.data.collections:
        if c.name.startswith('SOURCE_') or c.name.startswith('DTC_SPRINT_A_BASELINE') or c.name=='DTC_COMPONENT_STAGING_V08': c.hide_render=True
    work=bpy.data.collections['DTC_SPRINT_A_WORK']; objs=[o for o in work.all_objects if o.type=='MESH' and not o.hide_render]
    lo,hi=bounds(objs); ctr=(lo+hi)*.5; span=hi-lo
    camd=bpy.data.cameras.new('ReviewCamera'); cam=bpy.data.objects.new('ReviewCamera',camd); sc.collection.objects.link(cam); sc.camera=cam; camd.lens=52
    sc.render.engine='BLENDER_WORKBENCH'; sc.render.resolution_x=900; sc.render.resolution_y=630; sc.render.resolution_percentage=100; sc.render.image_settings.file_format='PNG'
    sh=sc.display.shading; sh.light='STUDIO'; sh.color_type='MATERIAL'; sh.show_shadows=True; sh.show_cavity=True; sh.cavity_type='WORLD'; sh.show_specular_highlight=True
    sh.background_type='WORLD'; sh.background_color=(0.045,0.045,0.045)
    r=max(span.x,span.y,span.z)*1.55
    views={'front_3q':(ctr.x+r,ctr.y-r*.72,ctr.z+r*.46),'left_side':(ctr.x,ctr.y+r*1.4,ctr.z+r*.26),'right_side':(ctr.x,ctr.y-r*1.4,ctr.z+r*.26),'rear_3q':(ctr.x-r,ctr.y+r*.72,ctr.z+r*.46),'top_3q':(ctr.x+r*.35,ctr.y-r*.25,ctr.z+r*1.55)}
    for name,loc in views.items():
        cam.location=loc; look_at(cam,ctr); sc.render.filepath=str(ns.out/f'{name}.png'); bpy.ops.render.render(write_still=True)
    info={'asset_version':sc.get('dtc.asset_version'),'bounds_min':list(lo),'bounds_max':list(hi),'objects':[{'name':o.name,'location':list(o.matrix_world.translation),'dimensions':list(o.dimensions)} for o in objs]}
    (ns.out/'review_info.json').write_text(json.dumps(info,indent=2)); print('DTC_V09_WORKBENCH_REVIEW_PASS')
if __name__=='__main__': main()
