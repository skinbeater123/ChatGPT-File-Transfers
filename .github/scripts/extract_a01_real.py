#!/usr/bin/env python3
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import argparse, hashlib, json, struct
import numpy as np
import trimesh

REGISTERED_PSSG_SHA = '6621074f3048a4ee41606c6fd15b501bc3fd8723a423ee9a0b7368fb4f428bd6'
PHYSICAL_METRES_PER_INTERNAL = 0.217391
FORCE_DATA = {'DATABLOCKBUFFERED','NeAnimPacketData_B1','NeAnimPacketData_B4','RENDERINTERFACEBOUNDBUFFERED'}
SOURCE_TO_DTC = np.array([[0.,1.,0.,0.],[-1.,0.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]],dtype=np.float64)

@dataclass
class Elem:
    id:int; name:str; start:int; end:int
    attrs:list=field(default_factory=list); children:list=field(default_factory=list); value:bytes=b''

class PSSG:
    def __init__(self,path:Path):
        self.path=path; self.data=path.read_bytes(); self.sha256=hashlib.sha256(self.data).hexdigest()
        if self.sha256!=REGISTERED_PSSG_SHA: raise ValueError(f'unregistered A01 PSSG sha256 {self.sha256}')
        if self.data[:4]!=b'PSSG': raise ValueError('bad PSSG magic')
        off=4; self.size=self.i32(off);off+=4;self.attr_count=self.i32(off);off+=4;self.elem_count=self.i32(off);off+=4
        self.elem_by_id={};self.attr_by_id={}
        for _ in range(self.elem_count):
            eid=self.i32(off);off+=4;name,off=self.pstr(off);self.elem_by_id[eid]=name;sub=self.i32(off);off+=4
            for _ in range(sub):
                aid=self.i32(off);off+=4;aname,off=self.pstr(off);self.attr_by_id[aid]=aname
        self.root,end=self.parse_elem(off,len(self.data))
        if end!=len(self.data): raise ValueError('root does not consume PSSG')
        self.all=list(self.walk(self.root));self.idmap={}
        for e in self.all:
            v=self.attr(e,'id')
            if isinstance(v,str) and v:self.idmap[v]=e
    def i32(self,off):return struct.unpack_from('>i',self.data,off)[0]
    def pstr(self,off):
        n=self.i32(off);off+=4;return self.data[off:off+n].decode('utf-8','replace'),off+n
    def parse_elem(self,pos,limit):
        start=pos;eid=self.i32(pos);pos+=4
        if eid not in self.elem_by_id:raise ValueError(f'bad element id at 0x{start:x}')
        size=self.i32(pos);pos+=4;end=pos+size
        if size<4 or end>limit:raise ValueError(f'bad element size at 0x{start:x}')
        attr_size=self.i32(pos);pos+=4;attr_end=pos+attr_size;attrs=[]
        while pos<attr_end:
            aid=self.i32(pos);asize=self.i32(pos+4);pos+=8
            if aid not in self.attr_by_id or asize<0 or pos+asize>attr_end:raise ValueError(f'bad attribute at 0x{pos-8:x}')
            attrs.append((aid,self.attr_by_id[aid],self.data[pos:pos+asize]));pos+=asize
        e=Elem(eid,self.elem_by_id[eid],start,end,attrs)
        if pos==end:return e,end
        if e.name in FORCE_DATA:e.value=self.data[pos:end];return e,end
        children=[];q=pos;ok=True
        try:
            while q<end:
                if q+8>end:ok=False;break
                ceid,csize=self.i32(q),self.i32(q+4)
                if ceid not in self.elem_by_id or csize<4 or q+8+csize>end:ok=False;break
                child,q2=self.parse_elem(q,end);children.append(child);q=q2
            if q!=end:ok=False
        except Exception:ok=False
        if ok and children:e.children=children
        else:e.value=self.data[pos:end]
        return e,end
    def walk(self,e):
        yield e
        for c in e.children:yield from self.walk(c)
    def raw_attr(self,e,name):
        for _,n,raw in e.attrs:
            if n==name:return raw
        return None
    def attr(self,e,name):
        raw=self.raw_attr(e,name)
        if raw is None:return None
        if len(raw)>=4:
            n=struct.unpack('>i',raw[:4])[0]
            if 0<=n==len(raw)-4:
                try:return raw[4:].decode('utf-8')
                except UnicodeDecodeError:pass
        if len(raw)==4:return struct.unpack('>i',raw)[0]
        return raw
    def child(self,e,name):return next((c for c in e.children if c.name==name),None)
    def transform(self,e):
        t=self.child(e,'TRANSFORM')
        if t is None or len(t.value)!=64:return np.eye(4)
        return np.asarray(struct.unpack('>16f',t.value),dtype=np.float64).reshape(4,4).T

def descendants(e):
    yield e
    for c in e.children:yield from descendants(c)
def parent_map(root):return {id(c):p for p in descendants(root) for c in p.children}
def ancestor_has(e,p,pm,needle):
    q=e
    while q is not None:
        for key in ('id','nickname'):
            v=p.attr(q,key)
            if isinstance(v,str) and needle.upper() in v.upper():return True
        q=pm.get(id(q))
    return False
def under_id(e,p,pm,target):
    q=e
    while q is not None:
        if p.attr(q,'id')==target:return True
        q=pm.get(id(q))
    return False
def world_matrix(e,p,pm):
    mats=[];q=e
    while q is not None:
        if q.name in {'ROOTNODE','NODE','RENDERNODE'}:mats.append(p.transform(q))
        q=pm.get(id(q))
    w=np.eye(4)
    for m in reversed(mats):w=w@m
    return w
def decode_block(p,db):
    s=next(c for c in db.children if c.name=='DATABLOCKSTREAM');raw=next(c.value for c in db.children if c.name=='DATABLOCKDATA')
    rt=p.attr(s,'renderType');dt=p.attr(s,'dataType');stride=int(p.attr(s,'stride'));off=p.attr(s,'offset');off=off if isinstance(off,int) else 0
    return rt,dt,stride,int(off),int(p.attr(db,'elementCount')),raw
def decode_rds(p,rds):
    streams={}
    for rs in (c for c in rds.children if c.name=='RENDERSTREAM'):
        db=p.idmap[p.attr(rs,'dataBlock')[1:]];item=decode_block(p,db);streams.setdefault(item[0],[]).append(item[1:])
    dtype,stride,off,count,raw=streams['Vertex'][0]
    if dtype!='float3':raise NotImplementedError(dtype)
    v=np.empty((count,3),dtype=np.float64)
    for i in range(count):v[i]=struct.unpack_from('>3f',raw,off+i*stride)
    normals=None
    if 'Normal' in streams:
        dtype,stride,off,ncount,raw=streams['Normal'][0];normals=np.empty((ncount,3),dtype=np.float64)
        for i in range(ncount):normals[i]=struct.unpack_from('>3f',raw,off+i*stride)
    uv=None
    if 'ST' in streams:
        dtype,stride,off,ucount,raw=streams['ST'][0];uv=np.empty((ucount,2),dtype=np.float64)
        for i in range(ucount):uv[i]=struct.unpack_from('>2f',raw,off+i*stride)
    idx=next(c for c in rds.children if c.name=='RENDERINDEXSOURCE');prim=p.attr(idx,'primitive');fmt=p.attr(idx,'format');icount=int(p.attr(idx,'count'))
    if prim!='triangles':raise NotImplementedError(prim)
    iraw=next(c.value for c in idx.children if c.name=='INDEXSOURCEDATA')
    if fmt=='ushort':indices=np.frombuffer(iraw,dtype='>u2',count=icount).astype(np.int64)
    elif fmt=='uint':indices=np.frombuffer(iraw,dtype='>u4',count=icount).astype(np.int64)
    else:raise NotImplementedError(fmt)
    return v,indices.reshape((-1,3)),normals,uv
def selection(p,scope=None,intact=False):
    pm=parent_map(p.root);items=[e for e in p.all if e.name=='RENDERSTREAMINSTANCE']
    if scope:items=[e for e in items if under_id(e,p,pm,scope)]
    if intact:items=[e for e in items if not ancestor_has(e,p,pm,'DMG1')]
    return items,pm
def make_scene(p,scope=None,intact=False,dtc=False):
    items,pm=selection(p,scope,intact);scene=trimesh.Scene();records=[];metric=np.diag([PHYSICAL_METRES_PER_INTERNAL]*3+[1.]);basis=SOURCE_TO_DTC if dtc else np.eye(4)
    for j,rsi in enumerate(items):
        rid=p.attr(rsi,'indices')[1:];rds=p.idmap[rid];v,f,n,uv=decode_rds(p,rds);rn=pm[id(rsi)];rname=p.attr(rn,'id') or f'rendernode_{j}';name=f'{rname}__{j:02d}'
        mesh=trimesh.Trimesh(vertices=v,faces=f,vertex_normals=n,process=False)
        if uv is not None:mesh.visual=trimesh.visual.texture.TextureVisuals(uv=uv)
        scene.add_geometry(mesh,node_name=name,geom_name=name,transform=basis@metric@world_matrix(rn,p,pm))
        records.append({'node':name,'rendernode':rname,'rds':rid,'vertices':len(v),'triangles':len(f),'dmg1':ancestor_has(rsi,p,pm,'DMG1')})
    return scene,records,pm
def top_level_locators(p,pm):
    root=p.idmap['VisualSceneNode'];metric=np.diag([PHYSICAL_METRES_PER_INTERNAL]*3+[1.]);out=[]
    for node in root.children:
        if node.name not in {'NODE','RENDERNODE'}:continue
        name=p.attr(node,'id')
        if not name:continue
        w=world_matrix(node,p,pm);src=(metric@w)[:3,3];dtc=(SOURCE_TO_DTC@metric@w)[:3,3]
        out.append({'name':name,'has_render_geometry':any(e.name=='RENDERSTREAMINSTANCE' for e in descendants(node)),'source_xyz_m':src.tolist(),'dtc_xyz_m':dtc.tolist()})
    return out

def main():
    ap=argparse.ArgumentParser();ap.add_argument('pssg',type=Path);ap.add_argument('--out-dir',type=Path,required=True);ns=ap.parse_args();ns.out_dir.mkdir(parents=True,exist_ok=True)
    p=PSSG(ns.pssg);outputs={};jobs=[('source_all_render_geometry_dtc',None,False,True),('donor_lod0_intact_dtc','SprintCar_LOD0',True,True)]
    pm=None
    for label,scope,intact,dtc in jobs:
        scene,recs,pm=make_scene(p,scope,intact,dtc);glb=ns.out_dir/f'A01_{label}.glb';glb.write_bytes(scene.export(file_type='glb'))
        outputs[label]={'glb':str(glb),'render_instances':len(recs),'streamed_vertices':sum(x['vertices'] for x in recs),'triangles':sum(x['triangles'] for x in recs),'bounds_m':scene.bounds.tolist(),'records':recs}
    outputs['source']={'pssg_sha256':p.sha256,'parsed_nodes':len(p.all),'rendernodes':sum(e.name=='RENDERNODE' for e in p.all),'physical_metres_per_internal':PHYSICAL_METRES_PER_INTERNAL}
    outputs['locators']=top_level_locators(p,pm)
    (ns.out_dir/'A01_top_level_locators.json').write_text(json.dumps(outputs['locators'],indent=2));(ns.out_dir/'A01_real_donor_extraction_report.json').write_text(json.dumps(outputs,indent=2))
    c=outputs['donor_lod0_intact_dtc'];assert len(p.all)==5628;assert outputs['source']['rendernodes']==80;assert c['render_instances']==16;assert c['streamed_vertices']==30660;assert c['triangles']==14892
    print('A01_REAL_DONOR_CENSUS_PASS')
if __name__=='__main__':main()
