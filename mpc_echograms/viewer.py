"""Offline, project-aware room and recorded-path viewer."""
import html
import json
import math
from pathlib import Path
from .haas import boundary, classify
from .project import polygon_geometry, triangulate, project_summary
from .project_config import ray_categories
from .reader import MPCError


def export_viewer(dataset,output,frequencies,context_edges=(),project=None,config=None,audit=None):
    try:from plotly.offline import get_plotlyjs
    except ImportError as e:raise MPCError('Interactive export needs Plotly; install requirements-interactive.txt.') from e
    config=config or {'categories':{},'materials':{},'provenance':None}
    direct={}
    for r in dataset.rays:
        k=(r.source_id,r.seat_id)
        if r.order==0 and (k not in direct or r.arrival_ms<direct[k].arrival_ms):direct[k]=r
    pairs=[];records=[]
    for source in dataset.sources:
        for seat in dataset.seats:
            pairs.append({'id':f'{source.id}:{seat.id}','label':f'Source {source.label} / Seat {seat.label}',
                          'description':'','position':seat.position,'source':{'label':source.label,'position':source.position}})
    for r in dataset.rays:
        source=next(s for s in dataset.sources if s.id==r.source_id);seat=next(s for s in dataset.seats if s.id==r.seat_id)
        if len(r.reflection_points)!=r.order:raise MPCError('The viewer requires decoded reflection geometry.')
        ref=direct.get((r.source_id,r.seat_id));delay=r.arrival_ms-ref.arrival_ms if ref else None
        metrics={}
        for hz in frequencies:
            i=dataset.frequencies.index(hz);level=r.levels_db[i]-ref.levels_db[i] if ref else None;lim=boundary(delay) if delay is not None else None
            metrics[str(hz)]={'level':level,'absolute':r.levels_db[i],'excess':level-lim if lim is not None else None,
                              'zone':classify(delay,level,direct=r.order==0) if ref else 'no-direct-reference'}
        categories=ray_categories(r,project,config)
        records.append({'id':r.id,'seat':f'{r.source_id}:{r.seat_id}','order':r.order,'arrival':r.arrival_ms,'delay':delay,
                        'faces':r.face_labels,'points':[source.position,*r.reflection_points,seat.position],
                        'openings':categories.get('openings',[]),'audience':categories.get('audience',[]),'metrics':metrics})
    faces={}
    if project:
        referenced={s for r in dataset.rays for s in r.face_labels}
        for f in project.faces:
            obj=dict(f);obj['points']=[project.vertices[i] for i in f['vertex_ids']];faces[f['label']]=obj
            if f['label']+'*' in referenced:
                mirrored=dict(obj);mirrored['label']+='*';mirrored['points']=[(-p[0],p[1],p[2]) for p in reversed(obj['points'])]
                _,mirrored['normal'],_=polygon_geometry(mirrored['points']);mirrored['triangles']=triangulate(mirrored['points']);faces[mirrored['label']]=mirrored
    edges=project.edges() if project else list(context_edges)
    for f in faces.values():
        if f['label'].endswith('*'):edges.extend(zip(f['points'],f['points'][1:]+f['points'][:1]))
    points=[p for r in records for p in r['points']]+[p for e in edges for p in e]
    points+=[p['position'] for p in pairs]+[s.position for s in dataset.sources]
    limits=[]
    for axis in range(3):
        lo=min((p[axis] for p in points),default=0);hi=max((p[axis] for p in points),default=1);pad=max(.5,(hi-lo)*.035);limits.append([lo-pad,hi+pad])
    payload={'bands':frequencies,'seats':pairs,'rays':records,'edges':edges,'limits':limits,'faces':faces,
             'project':project_summary(project,audit) if project else None,'config':config,'sha256':dataset.sha256}
    css=Path(__file__).with_name('viewer.css').read_text(encoding='utf-8');js=Path(__file__).with_name('viewer.js').read_text(encoding='utf-8')
    title=html.escape(dataset.path.stem)
    template='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPC room and reflection viewer</title><style>CSS</style></head><body><main>
<header><div><p class="eyebrow">EASE MPC · NATIVE PROJECT CONTEXT</p><h1>Room and reflection viewer</h1><p class="intro">TITLE · Saved rays and source/receiver positions come from the MPC.</p></div><button id="reset">Reset view ↗</button></header>
<p id="compatibility" class="notice"></p>
<section class="controls" aria-label="Viewer controls">
<label>Source / receiver<select id="seat"></select></label><label>Reflections<select id="paths"><option value="all">All reflections</option><option value="D">Only D reflections</option></select></label>
<label>Frequency<select id="band"><option value="study">Any selected band</option></select></label><label>Colours<select id="colour"><option value="order">Reflection order</option><option value="level">Level relative to direct (dB)</option><option value="excess">Haas-boundary excess (dB)</option></select></label>
<div class="toggles"><label><input type="checkbox" id="hide-openings">Hide opening-dependent paths</label><label><input type="checkbox" id="hide-audience">Hide audience paths</label><label><input type="checkbox" id="room" checked>Wireframe</label><label><input type="checkbox" id="surfaces">Translucent room surfaces</label></div></section>
<section class="stats"><div><span id="stat-total">—</span><small>visible reflected paths</small></div><div><span id="stat-physical">—</span><small>not tagged as opening paths</small></div><div><span id="stat-opening">—</span><small>opening · visible / selected</small></div><div><span id="stat-audience">—</span><small>audience · visible / selected</small></div><div><span id="stat-D">—</span><small>D candidates excluding tagged openings</small></div></section>
<div class="plot-head"><div><h2 id="view-title">Loading…</h2><p id="colour-note"></p></div><span class="axis-note">Z vertical · metres</span></div>
<div id="plot"></div><p id="empty" hidden>No reflected paths match these filters. Direct sound, when available, remains as a reference.</p><p id="status"></p>
<section class="inspect"><label>Inspect a visible path<select id="ray-pick"><option value="">Choose a path…</option></select></label><label>Inspect a project face<select id="face-pick"><option value="">Choose a face…</option></select></label><button id="clear-pick">Clear selection</button><div id="ray-info"></div><div id="face-info"></div><div id="material-chart" hidden></div></section>
<details><summary>Interpretation and provenance</summary><div class="help"><p>Recorded paths only; no new ray tracing or acoustic simulation is performed. The MPC supplies source/receiver positions, paths and saved levels. Project materials are a separate snapshot, not verified as the materials used to calculate the MPC.</p><p>Relative-level colours use each pair’s direct sound. With several bands selected, each path uses its largest selected value. D means an approximate assignment Haas criterion over 0–100 ms, not a universal echo standard. A pair with no direct arrival has no direct reference; unclassifiable. Its saved paths remain available in order colours, with absolute levels in their details.</p><p>Grey paths are tagged opening-dependent by the optional configuration. Opening and audience filters remove complete paths from the display, preserving all data. Audience filtering does not simulate scattering. No project-specific face IDs or material-name guesses are built into the tool.</p><p>Click a path or use its selector to highlight the whole route and the matching project faces. Enable translucent surfaces to click a face. A face’s normal follows its stored vertex order. Missing material curves are shown as unavailable, never as zero absorption or scattering.</p><p id="project-details"></p></div></details><footer>Offline single-file viewer · INPUTS retained · Project and MPC files are read-only.</footer>
</main><script>PLOTLY</script><script id="reflection-data" type="application/json">DATA</script><script>APP</script></body></html>'''
    template=template.replace('TITLE',title).replace('INPUTS',str(len(records))+' saved paths')
    template=template.replace('<style>CSS</style>','<style>'+css+'</style>').replace('<script>PLOTLY</script>','<script>'+get_plotlyjs()+'</script>').replace('>DATA</script>','>'+json.dumps(payload,ensure_ascii=True,allow_nan=False,separators=(',',':')).replace('<','\\u003c')+'</script>').replace('<script>APP</script>','<script>'+js+'</script>')
    path=Path(output)/'ray_viewer.html';path.write_text(template,encoding='utf-8');return [path]
