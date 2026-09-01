#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, math, struct, sys
from pathlib import Path

SHA='6219282c663faca7bde0ef955d864aee2aa6cde85532f1614da8517ae9f61289'
EXT_META=9_486_209; EXT_GEO=9_595_782; EXT_END=11_026_277; COCK=11_059_027
TARGET=('cockpit_HOOD_LN_Sol__0','cockpit_HOOD_LN_Sol__1','cockpit_HOOD_LN_Sol__2')
EXT_HOOD='HOOD_LN_Sol_01_0'; EXT_PANEL='PANEL_mopcut_01_0'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def finite(v): return all(math.isfinite(x) for x in v)
def bounds(vs): return [tuple(min(v[k] for v in vs) for k in range(3)),tuple(max(v[k] for v in vs) for k in range(3))]
def centroid(vs): return tuple(sum(v[k] for v in vs)/len(vs) for k in range(3))
def d2(a,b): return sum((a[k]-b[k])**2 for k in range(3))
def q(xs,f):
 s=sorted(xs); return s[min(len(s)-1,int(round((len(s)-1)*f)))] if s else None

def names(data,start,end):
 out=[]; p=start
 while True:
  h=data.find(b'MeshFile\0',p,end)
  if h<0: break
  s=h+9; e=data.find(b'\0',s,min(end,s+256))
  if e<0: break
  raw=data[s:e]
  if raw and all(32<=c<127 for c in raw): out.append((h,raw.decode('ascii')))
  p=e+1
 return out

def matrix(data,hit,limit):
 h=data.find(b'\0Matrix\0',hit,min(limit,hit+5000))
 if h<0: return None
 s=h+1+len(b'Matrix\0'); a=struct.unpack_from('<12f',data,s)
 if not finite(a): return None
 return (a[0:4],a[4:8],a[8:12])
def apply(v,m): return tuple(sum(m[r][c]*v[c] for c in range(3))+m[r][3] for r in range(3))

def section(data,p,full=True):
 if p+21>len(data): return None
 vc=struct.unpack_from('<I',data,p+13)[0]
 if not 3<=vc<=100000: return None
 vs=p+17; to=vs+vc*40
 if to+4>len(data): return None
 tc=struct.unpack_from('<I',data,to)[0]
 if not 1<=tc<=200000: return None
 end=to+4+tc*12
 if end>len(data): return None
 verts=[]; gn=0; go=0; sn=min(vc,24)
 for i in range(vc):
  o=vs+i*40; pos=struct.unpack_from('<3f',data,o)
  if not finite(pos) or any(abs(x)>1e6 for x in pos): return None
  verts.append(pos)
  if i<sn:
   n=struct.unpack_from('<3f',data,o+12); nn=math.sqrt(sum(x*x for x in n)) if finite(n) else 0
   if .75<=nn<=1.25: gn+=1
   if struct.unpack_from('<I',data,o+28)[0]==1: go+=1
   uv=struct.unpack_from('<2f',data,o+32)
   if not finite(uv): return None
 if gn<max(2,int(sn*.70)): return None
 tris=[]
 for i in range(tc if full else min(tc,64)):
  t=struct.unpack_from('<3I',data,to+4+i*12)
  if max(t)>=vc: return None
  if full: tris.append(t)
 return {'offset':p,'end':end,'header':data[p:p+13],'vc':vc,'tc':tc,'verts':verts,'tris':tris,'open1':go/sn}

def ext(data):
 ns=names(data,EXT_META,EXT_GEO); p=EXT_GEO; ss=[]
 for hit,n in ns:
  s=section(data,p)
  if not s: raise RuntimeError(('external parse',n,p))
  s['name']=n; s['meta']=hit; ss.append(s); p=s['end']
 if len(ss)!=102 or p!=EXT_END-9: raise RuntimeError(('external reproduction',len(ss),p))
 fixed=[]
 for j in range(13):
  z={s['header'][j] for s in ss}
  if len(z)==1: fixed.append((j,next(iter(z))))
 return ns,ss,fixed

def match(data,p,fixed): return p+13<=len(data) and all(data[p+j]==v for j,v in fixed)

def scan(data,fixed):
 out=[]; p=COCK
 while p<len(data)-21:
  if match(data,p,fixed):
   s=section(data,p)
   if s:
    out.append(s); p=s['end']; continue
  p+=1
 return out

def sign_counts(vs,tris,axis=0):
 o={'neg':0,'central':0,'pos':0}; eps=max(1e-6,(bounds(vs)[1][axis]-bounds(vs)[0][axis])*.01)
 for t in tris:
  c=sum(vs[i][axis] for i in t)/3
  if c<-eps:o['neg']+=1
  elif c>eps:o['pos']+=1
  else:o['central']+=1
 o['eps']=eps; return o

def symmetry(vs,axis=0):
 lo,hi=bounds(vs); mid=(lo[axis]+hi[axis])/2; width=hi[axis]-lo[axis]
 step=max(1,len(vs)//600); ds=[]
 for v in vs[::step]:
  r=list(v); r[axis]=2*mid-r[axis]; r=tuple(r)
  ds.append(math.sqrt(min(d2(r,w) for w in vs)))
 return {'mid':mid,'width':width,'median_nn':q(ds,.5),'p90_nn':q(ds,.9),'median_over_width':q(ds,.5)/width if width else 0,'p90_over_width':q(ds,.9)/width if width else 0}

def centered_nn(a,b):
 ca=centroid(a); cb=centroid(b); bb=[tuple(v[k]-cb[k] for k in range(3)) for v in b]; step=max(1,len(a)//600); ds=[]
 for v in a[::step]:
  x=tuple(v[k]-ca[k] for k in range(3)); ds.append(math.sqrt(min(d2(x,w) for w in bb)))
 return {'median':q(ds,.5),'p90':q(ds,.9),'max':max(ds),'centroid_a':ca,'centroid_b':cb}

def main():
 src=Path(sys.argv[1]); out=Path(sys.argv[2]); data=src.read_bytes()
 if len(data)!=12401519 or sha(src)!=SHA: raise RuntimeError('source gate')
 ens,ess,fixed=ext(data); cns=names(data,COCK,len(data)); css=scan(data,fixed)
 report={'schema':'woo_cockpit_hood_witness_probe_v2','source_sha256':SHA,'cockpit_meshfile_count':len(cns),'geometry_candidate_count':len(css),'ordinal_mapping_authority':len(cns)==len(css),'fixed_header_positions':fixed}
 report['hood_meshfiles']=[{'meshfile_index':i,'metadata_offset':h,'name':n} for i,(h,n) in enumerate(cns) if 'hood' in n.lower()]
 report['geometry_candidates_brief']=[{'index':i,'offset':s['offset'],'vc':s['vc'],'tc':s['tc']} for i,s in enumerate(css)]
 if len(cns)==len(css):
  target=[]; combo=[]; combo_tris=[]
  for wanted in TARGET:
   i=next(i for i,(_,n) in enumerate(cns) if n==wanted); s=css[i]; hit=cns[i][0]; lim=cns[i+1][0] if i+1<len(cns) else s['offset']; m=matrix(data,hit,max(lim,hit+5000)); w=[apply(v,m) for v in s['verts']] if m else s['verts']
   base=len(combo); combo.extend(w); combo_tris.extend(tuple(base+x for x in t) for t in s['tris'])
   target.append({'meshfile_index':i,'name':wanted,'metadata_offset':hit,'geometry_offset':s['offset'],'vc':s['vc'],'tc':s['tc'],'raw_bounds':bounds(s['verts']),'matrix':m,'world_bounds':bounds(w),'world_sign_counts_axis0':sign_counts(w,s['tris'],0),'world_symmetry_axis0':symmetry(w,0),'open_u32_one_fraction':s['open1']})
  report['beulah_cockpit_sections']=target
  report['beulah_cockpit_combined']={'vertices':len(combo),'triangles':len(combo_tris),'world_bounds':bounds(combo),'world_sign_counts_axis0':sign_counts(combo,combo_tris,0),'world_symmetry_axis0':symmetry(combo,0)}
  by={s['name']:s for s in ess}; hood=by[EXT_HOOD]; panel=by[EXT_PANEL]; hmin,hmax=bounds(hood['verts']); pmin,pmax=bounds(panel['verts']); norm=(pmax[0]-hmax[0],pmin[1]-hmin[1],pmin[2]-hmin[2]); hn=[tuple(v[k]+norm[k] for k in range(3)) for v in hood['verts']]; hm=matrix(data,hood['meta'],EXT_GEO); hw=[apply(v,hm) for v in hn] if hm else hn
  report['external_beulah_normalized']={'vertices':len(hw),'triangles':hood['tc'],'normalization':norm,'world_bounds':bounds(hw),'world_sign_counts_axis0':sign_counts(hw,hood['tris'],0),'world_symmetry_axis0':symmetry(hw,0)}
  report['cockpit_to_external_shape_only']={'centered_nn':centered_nn(combo,hw),'warning':'shape-only diagnostic; not a mount equation'}
  b=bounds(combo); sc=report['beulah_cockpit_combined']['world_sign_counts_axis0']; report['witness_decision']={'crosses_absolute_axis0':b[0][0]<0<b[1][0],'has_triangles_both_absolute_sides':sc['neg']>0 and sc['pos']>0,'physical_cut_authority':False,'reason':'cockpit witness can strengthen semantic completeness but DTC face-boundary intersection is a separate gate'}
 else:
  report['witness_decision']={'physical_cut_authority':False,'reason':'cockpit MeshFile/geometry candidate ordinal mapping not exact; no geometry promoted'}
 out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'meshfiles':len(cns),'candidates':len(css),'ordinal':len(cns)==len(css),'hoods':report['hood_meshfiles']},indent=2))
if __name__=='__main__': main()
