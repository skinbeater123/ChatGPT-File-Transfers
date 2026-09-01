"""Build DTC_SPRINT_A_v03_HARDPOINT from validated v02 with correct wheel pivots.

This is a render-asset operation only. SOURCE_BIGANT_A01_LOCKED and the v01
rollback remain immutable; a full independent BASELINE_V02 is created first.
The four wheel meshes are resized/repositioned in world space AND their Blender
object origins are relocated to the same WoO axle hard-points, so steering and
wheel rotation use the corrected visual pivots rather than stale A01 origins.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
import bpy
from mathutils import Vector
IN=0.0254; TOL=1e-6
SOURCE='SOURCE_BIGANT_A01_LOCKED'; WORK='DTC_SPRINT_A_WORK'; BASE1='DTC_SPRINT_A_BASELINE_V01'; BASE2='DTC_SPRINT_A_BASELINE_V02'; GUIDES='DTC_WOO_REFERENCE_GUIDES_V03'
WOO=dict(wheelbase_in=85.4193,front_track_in=55.4295,rear_track_in=52.7976,front_tyre_dia_in=26.9768,lr_tyre_dia_in=29.9211,rr_tyre_dia_in=33.4225,nose_overhang_in=19.4255)
BA=dict(front_tyre_dia_in=26.7151,lr_tyre_dia_in=29.0614,rr_tyre_dia_in=33.0042)
def cli():
 p=argparse.ArgumentParser(); p.add_argument('--in',dest='src',required=True,type=Path); p.add_argument('--out',dest='dst',required=True,type=Path); p.add_argument('--report',type=Path); p.add_argument('--export-glb',type=Path); a=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []; return p.parse_args(a)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def coll(n):
 c=bpy.data.collections.get(n)
 if c is None: raise RuntimeError(f'missing collection {n}')
 return c
def objs(c):
 out=[]; seen=set(); stack=[c]
 while stack:
  x=stack.pop()
  for o in x.objects:
   if o.name not in seen: seen.add(o.name); out.append(o)
  stack.extend(x.children)
 return out
def meshes(c): return [o for o in objs(c) if o.type=='MESH']
def one(c,p):
 a=[o for o in meshes(c) if o.name.startswith(p)]
 if len(a)!=1: raise RuntimeError(f'{p}: expected 1, got {[o.name for o in a]}')
 return a[0]
def origin(o): return o.matrix_world.translation.copy()
def smooth(x): x=max(0,min(1,x)); return x*x*(3-2*x)
def backup(work):
 if bpy.data.collections.get(BASE2): raise RuntimeError(f'{BASE2} already exists')
 b=bpy.data.collections.new(BASE2); bpy.context.scene.collection.children.link(b); cp={}
 for o in objs(work):
  q=o.copy(); q.data=o.data.copy() if o.data else None; q.hide_select=True; q['dtc.rollback_role']='V02_PRE_V03_HARDPOINT_BACKUP'; q['dtc.source_object']=o.name; b.objects.link(q); cp[o]=q
 for o,q in cp.items():
  if o.parent in cp: q.parent=cp[o.parent]; q.matrix_parent_inverse=o.matrix_parent_inverse.copy()
 b.hide_viewport=True; b.hide_render=True; b['dtc.locked_backup']=True; b['dtc.rollback_target']='DTC_SPRINT_A_WORK immediately before v03'; return b
def deform(o,fn,label):
 m=o.matrix_world.copy(); inv=m.inverted()
 for v in o.data.vertices: v.co=inv@fn(m@v.co)
 o.data.update(); o['dtc.v03_modified']=True; o['dtc.v03_change']=label
def wheel(o,target,scale,label):
 if o.children: raise RuntimeError(f'{o.name}: wheel must be leaf; children={[x.name for x in o.children]}')
 old=o.matrix_world.copy(); c=old.translation.copy(); world=[]
 for v in o.data.vertices:
  p=old@v.co; world.append(Vector((target.x+(p.x-c.x)*scale,target.y+(p.y-c.y),target.z+(p.z-c.z)*scale)))
 new=old.copy(); new.translation=target; o.matrix_world=new; inv=o.matrix_world.inverted()
 for v,p in zip(o.data.vertices,world): v.co=inv@p
 o.data.update(); err=(origin(o)-target).length
 if err>TOL: raise RuntimeError(f'{o.name}: pivot error {err}')
 o['dtc.v03_modified']=True; o['dtc.v03_change']=label; o['dtc.v03_pivot_relocated']=True; o['dtc.v03_pivot_target_m']=tuple(float(x) for x in target); o['dtc.v03_pivot_error_m']=float(err)
 return dict(object=o.name,before=list(c),after=list(origin(o)),target=list(target),error_m=float(err),radial_scale=scale)
def xmax(o): return max((o.matrix_world@v.co).x for v in o.data.vertices)
def translate_x(o,dx,label): deform(o,lambda p:Vector((p.x+dx,p.y,p.z)),label)
def guide(c,n,p):
 o=bpy.data.objects.new(n,None); o.empty_display_type='PLAIN_AXES'; o.empty_display_size=.06; o.location=p; o['dtc.guide_status']='V03_APPLIED_RENDER_AND_PIVOT_TARGET'; o['dtc.physics_authority']='NONE_G2_003_OWNS_SIMULATION'; c.objects.link(o)
def export(work,p):
 p.parent.mkdir(parents=True,exist_ok=True); bpy.ops.object.select_all(action='DESELECT'); a=objs(work)
 for o in a: o.hide_set(False); o.select_set(True)
 if a: bpy.context.view_layer.objects.active=a[0]
 bpy.ops.export_scene.gltf(filepath=str(p),export_format='GLB',use_selection=True,export_apply=True)
def main():
 ns=cli(); ns.dst.parent.mkdir(parents=True,exist_ok=True); bpy.ops.wm.open_mainfile(filepath=str(ns.src)); source=coll(SOURCE); work=coll(WORK); b1=coll(BASE1)
 if (len(meshes(source)),len(meshes(work)),len(meshes(b1)))!=(92,16,16): raise RuntimeError('v02 census failed')
 if not source.get('dtc.locked_source') or not b1.get('dtc.locked_backup'): raise RuntimeError('source/rollback lock missing')
 if bpy.context.scene.get('dtc.asset_version')!='DTC_SPRINT_A_v02': raise RuntimeError('v03 requires validated v02')
 parent=sha(ns.src); b2=backup(work); w={k:one(work,p) for k,p in [('lf','WheelLF_LOD0'),('rf','WheelRF_LOD0'),('lr','WheelLR_LOD0'),('rr','WheelRR_LOD0')]}; c={k:origin(o) for k,o in w.items()}
 rearx=(c['lr'].x+c['rr'].x)/2; frontx=(c['lf'].x+c['rf'].x)/2; frontz=(c['lf'].z+c['rf'].z)/2; rearz=(c['lr'].z+c['rr'].z)/2; tx=rearx+WOO['wheelbase_in']*IN
 t={'lf':Vector((tx,+WOO['front_track_in']*IN/2,frontz)),'rf':Vector((tx,-WOO['front_track_in']*IN/2,frontz)),'lr':Vector((rearx,+WOO['rear_track_in']*IN/2,rearz)),'rr':Vector((rearx,-WOO['rear_track_in']*IN/2,rearz))}
 s={'lf':WOO['front_tyre_dia_in']/BA['front_tyre_dia_in'],'rf':WOO['front_tyre_dia_in']/BA['front_tyre_dia_in'],'lr':WOO['lr_tyre_dia_in']/BA['lr_tyre_dia_in'],'rr':WOO['rr_tyre_dia_in']/BA['rr_tyre_dia_in']}; piv={k:wheel(w[k],t[k],s[k],f'WoO hard-point + tyre diameter + pivot ({k.upper()})') for k in w}
 fdx=tx-frontx; dyfl=t['lf'].y-c['lf'].y; dyfr=t['rf'].y-c['rf'].y; dyrl=t['lr'].y-c['lr'].y; dyrr=t['rr'].y-c['rr'].y; mech=one(work,'Frame_engine_struts_LOD0')
 def mf(p):
  wf=smooth((p.x-.15)/(frontx-.15)); wr=smooth(((-p.x)-.15)/((-rearx)-.15)); lat=smooth((abs(p.y)-.08)/(.55-.08)); return Vector((p.x+wf*fdx,p.y+lat*(wf*(dyfl if p.y>=0 else dyfr)+wr*(dyrl if p.y>=0 else dyrr)),p.z))
 deform(mech,mf,'axle-zone weighted WoO hard-point deformation'); fw=one(work,'FrontWing_LOD0_DMG0'); translate_x(fw,fdx,'follow v03 front axle'); fb=one(work,'BumperFront_DMG0_LOD0'); targetmax=tx+WOO['nose_overhang_in']*IN; bdx=targetmax-xmax(fb); translate_x(fb,bdx,'WoO nose/body overhang target')
 for o in meshes(work):
  if 'dtc.v03_modified' not in o: o['dtc.v03_modified']=False
 if bpy.data.collections.get(GUIDES): raise RuntimeError(f'{GUIDES} already exists')
 gc=bpy.data.collections.new(GUIDES); bpy.context.scene.collection.children.link(gc)
 for k in w: guide(gc,f'LOC_WOO_{k.upper()}_V03_APPLIED',t[k])
 errors={k:float((origin(w[k])-t[k]).length) for k in w}; wb=(origin(w['lf']).x+origin(w['rf']).x-origin(w['lr']).x-origin(w['rr']).x)/2; ft=origin(w['lf']).y-origin(w['rf']).y; rt=origin(w['lr']).y-origin(w['rr']).y
 if max(errors.values())>TOL or abs(wb-WOO['wheelbase_in']*IN)>TOL or abs(ft-WOO['front_track_in']*IN)>TOL or abs(rt-WOO['rear_track_in']*IN)>TOL: raise RuntimeError(f'v03 pivot invariant failed errors={errors} wb={wb} ft={ft} rt={rt}')
 changed=sorted(o.name for o in meshes(work) if o.get('dtc.v03_modified') is True); exp=('WheelLF_LOD0','WheelRF_LOD0','WheelLR_LOD0','WheelRR_LOD0','Frame_engine_struts_LOD0','FrontWing_LOD0_DMG0','BumperFront_DMG0_LOD0')
 if len(changed)!=7 or not all(any(n.startswith(p) for n in changed) for p in exp): raise RuntimeError(f'bad edit boundary {changed}')
 sc=bpy.context.scene; sc['dtc.asset_version']='DTC_SPRINT_A_v03_HARDPOINT'; sc['dtc.parent_blend_sha256']=parent; sc['dtc.v03_scope']='render hard-points + wheel object pivots; body/cage/cockpit/tank unchanged'; sc['dtc.v03_pivot_invariant']='wheel origins equal WoO hard-points'; sc['dtc.physics_authority']='NONE_G2_003_OWNS_SIMULATION'; b2['dtc.parent_blend_sha256']=parent
 bpy.ops.wm.save_as_mainfile(filepath=str(ns.dst))
 if ns.export_glb: export(work,ns.export_glb)
 report={'schema':'dtc_sprint_a_v03_hardpoint_report_v2','status':'V03_HARDPOINT_AND_PIVOT_BLENDER_PASS','parent_sha256':parent,'rollback':{'v01':BASE1,'v02':BASE2,'v02_meshes':len(meshes(b2))},'targets':WOO,'changes':{'front_axle_dx_m':fdx,'front_bumper_dx_m':bdx,'wheel_pivots':piv,'pivot_errors_m':errors,'pivot_wheelbase_m':wb,'pivot_front_track_m':ft,'pivot_rear_track_m':rt,'changed_meshes':changed},'physics_authority':'NONE — G2-003 owns simulation'}
 if ns.report: ns.report.parent.mkdir(parents=True,exist_ok=True); ns.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
 print('DTC_SPRINT_A_V03_HARDPOINT_AND_PIVOT_PASS',json.dumps(report['changes'],sort_keys=True))
if __name__=='__main__': main()
