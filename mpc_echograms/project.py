"""Read-only reader for the observed EASE 4.4 native vertex/face tables.

This is an observed binary layout, not a published interchange specification.
Memory-structure sizes in the headers are NOT disk record lengths. Unknown
layouts fail closed. Material names are snapshots from the project, not proof
of the material coefficients used by an independently supplied MPC.
"""
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re
import struct

from .reader import MPCError


def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def norm(a): return math.sqrt(dot(a,a))


def polygon_geometry(points):
    v=[0.,0.,0.]
    for a,b in zip(points,points[1:]+points[:1]):
        c=cross(a,b)
        for i in range(3):v[i]+=c[i]
    length=norm(v)
    if length<1e-10: raise MPCError('Degenerate project face: zero polygon area.')
    normal=tuple(x/length for x in v)
    return length/2,normal,max(abs(dot(sub(p,points[0]),normal)) for p in points)


def triangulate(points):
    """Ear clipping in the dominant plane; preserves concave room boundaries."""
    _,normal,_=polygon_geometry(points)
    axis=max(range(3),key=lambda i:abs(normal[i]))
    xy=[tuple(p[i] for i in range(3) if i!=axis) for p in points]
    def turn(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    sign=1 if sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(xy,xy[1:]+xy[:1]))>0 else -1
    ids=list(range(len(points)));result=[]
    # EASE boundaries often retain collinear seam vertices.
    changed=True
    while changed and len(ids)>3:
        changed=False
        for k,i in enumerate(ids):
            a,b,c=xy[ids[k-1]],xy[i],xy[ids[(k+1)%len(ids)]]
            if abs(turn(a,b,c))<1e-9:
                ids.pop(k);changed=True;break
    while len(ids)>3:
        for k,i in enumerate(ids):
            ia,ic=ids[k-1],ids[(k+1)%len(ids)];a,b,c=xy[ia],xy[i],xy[ic]
            if sign*turn(a,b,c)<=1e-10:continue
            if any(all(sign*t>=-1e-10 for t in [turn(a,b,xy[j]),turn(b,c,xy[j]),turn(c,a,xy[j])]) for j in ids if j not in [ia,i,ic]):continue
            result.append((ia,i,ic));ids.pop(k);break
        else:raise MPCError('Cannot triangulate project face: non-simple or unsupported polygon.')
    if len(ids)==3:result.append(tuple(ids))
    return result


def point_on_face(point,points,tolerance):
    _,n,_=polygon_geometry(points)
    distance=abs(dot(sub(point,points[0]),n))
    if distance>tolerance:return False,distance
    axis=max(range(3),key=lambda i:abs(n[i]));axes=[i for i in range(3) if i!=axis]
    p=tuple(point[i] for i in axes);xy=[tuple(q[i] for i in axes) for q in points]
    inside=False
    for a,b in zip(xy,xy[1:]+xy[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1];ll=dx*dx+dy*dy
        t=max(0.,min(1.,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/ll)) if ll else 0
        if math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)<=tolerance:return True,distance
        if (a[1]>p[1])!=(b[1]>p[1]) and p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:inside=not inside
    return inside,distance


class Binary:
    def __init__(self,data,offset=0):self.data=data;self.pos=offset
    def take(self,n):
        if n<0 or self.pos+n>len(self.data):raise MPCError('Truncated EASE project table.')
        b=self.data[self.pos:self.pos+n];self.pos+=n;return b
    def unpack(self,fmt):return struct.unpack('<'+fmt,self.take(struct.calcsize('<'+fmt)))
    def string(self):
        n,=self.unpack('H')
        if n>4096:raise MPCError('Unsupported project string length.')
        try:return self.take(n).decode('cp1252',errors='strict')
        except UnicodeDecodeError as e:raise MPCError('Unsupported project string encoding.') from e


def table_header(data,tag,record_version,size):
    if len(data)<30 or data[:4]!=b'EASE' or data[10:12]!=tag:raise MPCError('Not a supported EASE project table.')
    if struct.unpack_from('<HHH',data,4)!=(3,1,20) or struct.unpack_from('<H',data,12)[0]!=record_version or struct.unpack_from('<I',data,22)[0]!=size or struct.unpack_from('<I',data,26)[0]!=31:
        raise MPCError(f'Unsupported native {tag.decode()} table version/layout.')
    count=struct.unpack_from('<I',data,18)[0]
    if count>1_000_000:raise MPCError('Unreasonable project table count.')
    return count


@dataclass
class Project:
    base: Path
    vertices: dict
    faces: list
    listeners: list
    files: list
    warnings: list
    companion_counts: dict

    def edges(self):
        edges={}
        for f in self.faces:
            p=[self.vertices[i] for i in f['vertex_ids']]
            for a,b in zip(p,p[1:]+p[:1]):
                if a!=b:edges[tuple(sorted((a,b)))]=(a,b)
        return list(edges.values())

    def unchanged(self):
        return all(Path(f['path']).exists() and hashlib.sha256(Path(f['path']).read_bytes()).hexdigest()==f['sha256'] for f in self.files)


def locate_project(path):
    path=Path(path).expanduser().resolve()
    if path.is_dir():
        options=sorted(path.rglob('*.frd'))+sorted(path.rglob('*.FRD'))
        # Loudspeaker databases also contain .frd files; require room companions.
        options=[p for p in dict.fromkeys(options) if any(p.with_suffix(s).is_file() for s in ['.fvt','.FVT']) and any(p.with_suffix(s).is_file() for s in ['.ffc','.FFC']) and p.read_bytes()[:14]==b'EASE\x03\x00\x01\x00\x14\x00rd\x01\x00']
        if len(options)!=1:raise MPCError(f'Expected one .frd project in {path}; found {len(options)}. Specify its .frd explicitly.')
        path=options[0]
    if path.suffix.lower() not in ['.frd','.fvt','.ffc']:raise MPCError('--project must be a project folder or .frd/.fvt/.ffc file.')
    return path.with_suffix('')


def read_project(path):
    base=locate_project(path);files=[];warnings=[]
    def read(ext,required=False):
        p=Path(str(base)+ext)
        if not p.exists():
            p=Path(str(base)+ext.upper())
            if not p.exists():
                if required:raise MPCError(f'Missing required project companion: {base.name}{ext}')
                warnings.append(f'Missing optional companion {ext}.');return None
        b=p.read_bytes();files.append({'path':str(p),'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)});return b
    vb=read('.fvt',True);count=table_header(vb,b'vt',1,48)
    if len(vb)!=30+(count+1)*40:raise MPCError('Unexpected native vertex-table length.')
    vertices={i:struct.unpack_from('<3f',vb,30+i*40+12) for i in range(1,count+1)}
    if not all(math.isfinite(x) for p in vertices.values() for x in p):raise MPCError('Nonfinite project vertex.')
    fb=read('.ffc',True);n=table_header(fb,b'fc',2,220);reader=Binary(fb,130);faces=[]
    for i in range(1,n+1):
        prefix=reader.take(150);front=reader.string();front_id,front_flags=reader.unpack('IH');rear=reader.string();rear_id,rear_flags=reader.unpack('IH')
        reader.string();reader.take(4);reader.string();reader.take(4)
        stored_area,colour=reader.unpack('fI');reader.take(8);nv,=reader.unpack('I')
        marker,capacity,reserved=reader.unpack('HII')
        if marker!=1 or capacity!=nv+1 or reserved or not 3<=nv<=count:raise MPCError(f'Unsupported polygon layout at face F{i}.')
        ids=list(reader.unpack('I'*(nv+1)))
        if ids[0]!=ids[-1] or min(ids)<1 or max(ids)>count:raise MPCError(f'Invalid vertex references at F{i}.')
        ids=ids[:-1]
        if len(set(ids))!=len(ids):raise MPCError(f'Unsupported repeated boundary vertices at F{i}.')
        pts=[vertices[j] for j in ids];area,normal,deviation=polygon_geometry(pts)
        if not math.isfinite(stored_area) or stored_area<0:raise MPCError(f'Invalid stored area at F{i}.')
        try:triangles=triangulate(pts);tri_error=None
        except MPCError as e:triangles=[];tri_error=str(e);warnings.append(f'F{i}: {tri_error} Wireframe remains available.')
        faces.append({'id':i,'label':f'F{i}','vertex_ids':ids,'material_front':front,'material_rear':rear,
                      'material_front_index':front_id,'material_rear_index':rear_id,'material_reference_flags':[front_flags,rear_flags],
                      'raw_flags':struct.unpack_from('<I',prefix,136)[0],'colour_rgb':[colour&255,(colour>>8)&255,(colour>>16)&255],
                      'area_m2':area,'stored_area_m2':stored_area,'normal':normal,'planarity_error_m':deviation,
                      'triangles':triangles,'triangulation_error':tri_error})
    if reader.take(len(fb)-reader.pos)!=bytes(128):raise MPCError('Unsupported native face-table trailer.')
    listeners=[];sb=read('.fst')
    if sb is not None:
        try:
            ns=table_header(sb,b'st',1,304);sr=Binary(sb,30)
            for i in range(ns+1):
                label=sr.string();mirror=sr.string();tail=sr.take(292)
                position=struct.unpack_from('<3f',tail,8)
                if not all(math.isfinite(x) for x in position):raise MPCError('Nonfinite listener position.')
                if i:listeners.append({'id':i,'label':label,'mirror_label':mirror,'position':position})
            if sr.pos!=len(sb):raise MPCError('Unexpected listener-table trailer.')
        except MPCError as e:listeners=[];warnings.append(f'Listener table not decoded: {e}')
    companions={}
    for ext in ['.frd','.fld','.far','.fwm']:
        buf=read(ext)
        if buf is not None:
            if len(buf)<26 or buf[:4]!=b'EASE':warnings.append(f'Unrecognised optional {ext} table.');continue
            companions[ext]={'declared_records':struct.unpack_from('<I',buf,18)[0],'decoded':False}
    warnings.append('Material names come from the project face table. Native material curves and source/room settings are not decoded in this layout; external material data may be required. Missing coefficients are never inferred as zero.')
    return Project(base,vertices,faces,listeners,files,warnings,companions)


def audit_project(project,dataset,tolerance=.01):
    """Validate recorded nodes against the actual named polygon, not its plane alone."""
    face_map={f['label']:f for f in project.faces};checks=[];mismatches=[]
    for r in dataset.rays:
        for label,p in zip(r.face_labels,r.reflection_points):
            base=label.rstrip('*');f=face_map.get(base)
            if f is None:row={'ray_id':r.id,'face':label,'status':'missing-face','plane_distance_m':None}
            else:
                pts=[project.vertices[i] for i in f['vertex_ids']]
                if label.endswith('*'):pts=[(-v[0],v[1],v[2]) for v in pts]
                ok,distance=point_on_face(p,pts,tolerance)
                row={'ray_id':r.id,'face':label,'status':'matches' if ok else 'point-outside-face','plane_distance_m':distance}
            checks.append(row)
            if row['status']!='matches':mismatches.append(row)
    positions=[];lookup={s['id']:s for s in project.listeners}
    for s in dataset.seats:
        base_id=2**32-s.id if s.id>=2**31 else s.id;p=lookup.get(base_id)
        if p:
            xyz=p['position'];xyz=(-xyz[0],xyz[1],xyz[2]) if s.id>=2**31 else xyz
            positions.append({'id':s.id,'project_label':p['label'],'mpc_label':s.label,'project_position':xyz,'mpc_position':s.position,'difference_m':math.dist(xyz,s.position)})
    warnings=list(project.warnings)
    if mismatches:warnings.append(f'{len(mismatches)} recorded reflection nodes do not match their project faces at tolerance {tolerance:g} m; geometry versions may differ.')
    if any(p['difference_m']>tolerance for p in positions):warnings.append('Project/MPC listener coordinates differ. Displayed source/receiver positions and rays remain those from the MPC.')
    return {'geometry_status':'mismatch' if mismatches else 'sampled-reflection-nodes-match' if checks else 'not-tested-no-reflection-nodes',
            'tolerance_m':tolerance,'checked_nodes':len(checks),'matched_nodes':len(checks)-len(mismatches),'mismatches':mismatches,
            'listener_comparison':positions,'source_comparison':'not-decoded; MPC sources are authoritative',
            'materials_status':'project snapshot; correspondence to MPC material settings is unverified',
            'unobserved_faces_status':'Geometry not hit by recorded rays cannot be validated against the MPC.', 'warnings':warnings}


def project_summary(project,audit):
    extra=sum(f['area_m2'] for f in project.faces if f['raw_flags']&2)
    edges={};volume=0.
    for f in project.faces:
        if f['raw_flags']&2:continue
        p=[project.vertices[i] for i in f['vertex_ids']]
        for a,b in zip(f['vertex_ids'],f['vertex_ids'][1:]+f['vertex_ids'][:1]):
            k=tuple(sorted((a,b)));edges[k]=edges.get(k,0)+1
        for a,b in zip(p[1:],p[2:]):volume+=dot(p[0],cross(a,b))/6
    return {'project':str(project.base),'files':project.files,'vertex_count':len(project.vertices),'face_count':len(project.faces),
            'surface_area_m2':sum(f['area_m2'] for f in project.faces),'listeners':project.listeners,
            'surface_area_including_two_sided_m2':sum(f['area_m2'] for f in project.faces)+extra,
            'shell_signed_volume_m3':volume,'shell_edges_not_shared_twice':sum(n!=2 for n in edges.values()),
            'volume_note':'Signed boundary integral excluding two-sided faces; not an independent proof of enclosure or an RT calculation.',
            'materials':sorted({f[k] for f in project.faces for k in ['material_front','material_rear'] if f[k]}),
            'companion_tables':project.companion_counts,'compatibility':audit,
            'provenance':'Native project snapshot; saved MPC ray geometry, positions and levels are authoritative.'}
