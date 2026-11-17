"""Explicit, project-independent face categories and optional material curves."""
import hashlib
import json
import math
from pathlib import Path
import re
from .reader import MPCError


def read_config(path):
    if path is None:return {'categories':{},'materials':{},'provenance':None}
    path=Path(path).expanduser().resolve()
    try:raw=path.read_bytes();value=json.loads(raw)
    except (ValueError,OSError) as e:raise MPCError(f'Cannot read project configuration: {e}') from e
    if not isinstance(value,dict) or set(value)-{'categories','materials'}:raise MPCError('Config supports categories and materials only.')
    categories=value.get('categories',{});materials=value.get('materials',{})
    if not isinstance(categories,dict) or set(categories)-{'openings','audience'}:raise MPCError('Supported categories: openings, audience.')
    for name,rule in categories.items():
        if not isinstance(rule,dict) or set(rule)-{'faces','materials'}:raise MPCError(f'Invalid category rule: {name}')
        for k,v in rule.items():
            if not isinstance(v,list) or not all(isinstance(x,str) for x in v):raise MPCError(f'{name}.{k} must be a list of strings.')
            if k=='faces' and any(not re.fullmatch(r'F[1-9][0-9]*\*?',x) for x in v):raise MPCError('Invalid face ID in config.')
    if not isinstance(materials,dict):raise MPCError('materials must map material names to curves.')
    for name,m in materials.items():
        if not isinstance(m,dict) or set(m)-{'frequencies_Hz','absorption','scattering','source'}:raise MPCError(f'Invalid material curve: {name}')
        f=m.get('frequencies_Hz');source=m.get('source')
        if not isinstance(source,str) or not source.strip():raise MPCError('Each supplied material curve needs a source/provenance string.')
        if not isinstance(f,list) or not f or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x<=0 for x in f) or f!=sorted(set(f)):raise MPCError('Material frequencies must be positive, finite and strictly increasing.')
        if not any(k in m for k in ['absorption','scattering']):raise MPCError('Supply at least one coefficient curve.')
        for key in ['absorption','scattering']:
            if key in m:
                a=m[key]
                if not isinstance(a,list) or len(a)!=len(f) or any(isinstance(x,bool) or not isinstance(x,(float,int)) or not math.isfinite(x) or not 0<=x<=1 for x in a):raise MPCError(f'{key} must contain one finite coefficient in [0,1] per frequency.')
    return {'categories':categories,'materials':materials,'provenance':{'file':str(path),'sha256':hashlib.sha256(raw).hexdigest()}}


def ray_categories(ray,project,config):
    faces={f['label']:f for f in project.faces} if project else {}
    tags={}
    for category,rule in config['categories'].items():
        ids=set(rule.get('faces',[]));names={s.casefold() for s in rule.get('materials',[])};hits=[]
        for label in ray.face_labels:
            f=faces.get(label.rstrip('*'));mats=[f['material_front'],f['material_rear']] if f else []
            if label in ids or label.rstrip('*') in ids or any(m.casefold() in names for m in mats):hits.append(label)
        tags[category]=hits
    return tags
