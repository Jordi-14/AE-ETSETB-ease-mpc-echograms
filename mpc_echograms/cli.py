"""Command-line export, with a manifest of generated files for safe reruns."""
import argparse
from collections import Counter
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

from . import __version__
from .haas import boundary, classify, TIMES, LEVELS
from .reader import MPCError, read_mpc

GENERATOR = 'mpc-echograms'


def arrival_rows(dataset, frequencies):
    direct = {}
    for ray in dataset.rays:
        key = (ray.source_id, ray.seat_id)
        if ray.order == 0 and (key not in direct or ray.arrival_ms < direct[key].arrival_ms):
            direct[key] = ray
    for ray in dataset.rays:
        ref = direct.get((ray.source_id, ray.seat_id))
        for frequency in frequencies:
            i = dataset.frequencies.index(frequency)
            delay = ray.arrival_ms - ref.arrival_ms if ref else None
            level = ray.levels_db[i] - ref.levels_db[i] if ref else None
            limit = boundary(delay) if delay is not None else None
            yield {
                'source_id': ray.source_id, 'seat_id': ray.seat_id, 'ray_id': ray.id,
                'frequency_Hz': frequency, 'order': ray.order, 'arrival_ms': ray.arrival_ms,
                'level_dB': ray.levels_db[i], 'delay_after_direct_ms': delay,
                'level_relative_to_direct_dB': level, 'haas_boundary_dB': limit,
                'margin_above_boundary_dB': level - limit if limit is not None else None,
                'zone': classify(delay, level, direct=ray.order == 0) if ref else 'no-direct-reference',
            }


def _old_manifest(output):
    if not output.exists() or not any(output.iterdir()):
        return None
    try:
        manifest = json.loads((output / 'summary.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise MPCError(f'Output folder is not an export managed by this tool: {output}. '
                       'Choose a new folder with --output.') from exc
    if manifest.get('generator') != GENERATOR:
        raise MPCError('The output folder belongs to another tool; choose --output elsewhere.')
    return manifest


def _safe_generated_path(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise MPCError('Invalid generated-file path in previous summary.json.')
    return path


def export(dataset, output, frequencies, dpi, *, multiviews=False, context_dxf=None, context_z_offset=0.,
           all_reflections=False, combined_pdf=False, interactive=False, models=False, project_path=None,
           project_config=None, project_tolerance=.01, project_strict=False):
    from .plotting import export_images
    if interactive:
        try:
            import plotly.graph_objects
        except ImportError as exc:
            raise MPCError('Interactive export needs Plotly. Run: python3 -m pip install -r requirements-interactive.txt') from exc
    previous = _old_manifest(output)
    from .project_config import read_config, ray_categories
    config=read_config(project_config)
    project,project_audit,project_info=None,None,None
    context_edges, context_info = (), None
    if project_path is not None:
        if context_dxf is not None:raise MPCError('Use --project or --context-dxf, not both.')
        if any(len(r.reflection_points)!=r.order for r in dataset.rays):raise MPCError('--project requires decoded MPC reflection geometry.')
        from .project import read_project, audit_project, project_summary
        project=read_project(project_path);project_audit=audit_project(project,dataset,project_tolerance);project_info=project_summary(project,project_audit)
        if project_strict and (project_audit['mismatches'] or any(p['difference_m']>project_tolerance for p in project_audit['listener_comparison'])):
            raise MPCError('Project/MPC geometry or listener positions differ; inspect without --project-strict for a compatibility report.')
        context_edges=project.edges()
    if context_dxf is not None:
        from .context import read_context_edges
        context_dxf = context_dxf.expanduser().resolve()
        context_info = {'file': str(context_dxf), 'sha256': hashlib.sha256(context_dxf.read_bytes()).hexdigest(),
                        'z_offset_m': context_z_offset}
        context_edges = read_context_edges(context_dxf, context_z_offset)
    if previous and previous.get('input_file') != str(dataset.path):
        raise MPCError('This output folder was generated from a different MPC. Choose another --output.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.mpc-echograms-', dir=output.parent) as temp:
        staging = Path(temp)
        images = export_images(dataset, staging, frequencies=tuple(frequencies), dpi=dpi)
        extra_files, multiview_info = [], None
        if project:
            (staging/'project_room.json').write_text(json.dumps({'summary':project_info,'vertices':project.vertices,'faces':project.faces,'supplied_material_curves':config['materials']},indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            (staging/'project_compatibility.json').write_text(json.dumps(project_audit,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
            for name,records in [('project_faces.csv',project.faces),('project_vertices.csv',[{'id':i,'x_m':v[0],'y_m':v[1],'z_m':v[2]} for i,v in project.vertices.items()])]:
                with (staging/name).open('w',newline='',encoding='utf-8') as stream:
                    fields=list(records[0]) if records else ['id'];writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows({k:json.dumps(v) if isinstance(v,(list,tuple,dict)) else v for k,v in r.items()} for r in records)
                extra_files.append(staging/name)
            extra_files += [staging/'project_room.json',staging/'project_compatibility.json']
            lookup={f['label']:f for f in project.faces}
            bounce_rows=[]
            for ray in dataset.rays:
                for ordinal,(label,point) in enumerate(zip(ray.face_labels,ray.reflection_points),1):
                    f=lookup.get(label.rstrip('*'),{})
                    bounce_rows.append({'ray_id':ray.id,'source_id':ray.source_id,'seat_id':ray.seat_id,'bounce':ordinal,'face':label,'x_m':point[0],'y_m':point[1],'z_m':point[2],
                                        'project_material_front':f.get('material_front'),'project_material_rear':f.get('material_rear'),'material_provenance':'project snapshot; not verified against MPC'})
            with (staging/'reflection_faces.csv').open('w',newline='',encoding='utf-8') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(bounce_rows[0]) if bounce_rows else ['ray_id','face']);writer.writeheader();writer.writerows(bounce_rows)
            extra_files.append(staging/'reflection_faces.csv')
        if project or project_config:
            with (staging/'path_categories.csv').open('w',newline='',encoding='utf-8') as stream:
                writer=csv.DictWriter(stream,fieldnames=['ray_id','source_id','seat_id','opening_faces','audience_faces']);writer.writeheader()
                for ray in dataset.rays:
                    tags=ray_categories(ray,project,config);writer.writerow({'ray_id':ray.id,'source_id':ray.source_id,'seat_id':ray.seat_id,'opening_faces':json.dumps(tags.get('openings',[])),'audience_faces':json.dumps(tags.get('audience',[]))})
            extra_files.append(staging/'path_categories.csv')
        if multiviews:
            from .multiview import export_multiviews
            mv_files, multiview_info = export_multiviews(dataset, staging, frequencies, dpi, context_edges, combined_pdf=combined_pdf)
            extra_files += mv_files
        if all_reflections or combined_pdf or interactive or models:
            from . import extras
            if all_reflections:
                extra_files += extras.export_all_reflections(dataset, staging, dpi, context_edges, combined_pdf)
            if combined_pdf:
                extra_files += extras.export_combined_echograms(dataset, staging, frequencies)
            if interactive:
                extra_files += extras.export_interactive(dataset, staging, frequencies, context_edges, project, config, project_audit)
            if models:
                extra_files += extras.export_models(dataset, staging, frequencies)
        rows = list(arrival_rows(dataset, frequencies))
        with (staging / 'arrivals.csv').open('w', newline='', encoding='utf-8') as stream:
            fields = ['source_id', 'seat_id', 'ray_id', 'frequency_Hz', 'order', 'arrival_ms',
                      'level_dB', 'delay_after_direct_ms', 'level_relative_to_direct_dB',
                      'haas_boundary_dB', 'margin_above_boundary_dB', 'zone']
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        source_ids = sorted({r.source_id for r in dataset.rays} or {s.id for s in dataset.sources})
        counts = []
        for source_id in source_ids:
            for seat in dataset.seats:
                counts.append({'source_id': source_id, 'seat_id': seat.id, 'seat_label': seat.label,
                               **{str(f): sum(r['zone'] == 'D' and r['seat_id'] == seat.id and
                                             r['source_id'] == source_id and r['frequency_Hz'] == f
                                             for r in rows) for f in frequencies}})
        manifest = {
            'generator': GENERATOR, 'version': __version__, 'input_file': str(dataset.path),
            'input_sha256': dataset.sha256, 'seat_count': len(dataset.seats),
            'seats': [asdict(s) for s in dataset.seats], 'sources': [asdict(s) for s in dataset.sources],
            'exported_source_ids': source_ids, 'ray_count': len(dataset.rays),
            'reflection_order_counts': dict(Counter(r.order for r in dataset.rays)),
            'frequencies_Hz': frequencies, 'image_count': len(images), 'D_candidate_counts': counts,
            'multiviews': multiview_info, 'context_dxf': context_info,
            'native_project':project_info,'project_config':config['provenance'],
            'optional_exports': {'all_reflections': all_reflections, 'combined_pdf': combined_pdf,
                                 'interactive': interactive, 'models': models},
            'haas_curve': {'time_ms': TIMES, 'relative_level_dB': LEVELS,
                           'reference': 'Approximate tracing of theatre design.pdf, page 4',
                           'range_ms': [0, 100]},
            'limitations': [
                'Reader supports the observed EASE 4.x impact layout, validated on an EASE 4.4 MPC.',
                'Haas line is approximate; confirm borderline cases in EASE Probe.',
                'Individual paths; no time-bin energy summation or late reverberation tail.',
                'No direct arrival: absolute chart, no Haas classification.',
                'Delays outside 0–100 ms are not classified against the supplied Haas diagram.',
                'For multiple sources, normalisation and output are separate for each source.',
                'Multiview geometry supports the observed F-number face-node layout only.',
                'DXF context is visual only; its coordinates must match the MPC datum. No block transforms.',
            ],
            'generated_files': sorted([str(p.relative_to(staging)) for p in images + extra_files] +
                                      ['arrivals.csv', 'summary.json']),
        }
        (staging / 'summary.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        if hashlib.sha256(dataset.path.read_bytes()).hexdigest() != dataset.sha256:
            raise MPCError('Input MPC changed during export; no output was installed. Run again.')
        if context_info and hashlib.sha256(context_dxf.read_bytes()).hexdigest() != context_info['sha256']:
            raise MPCError('Context DXF changed during export; run again.')
        if project and not project.unchanged():raise MPCError('Native project changed during export; no output was installed.')
        if config['provenance'] and hashlib.sha256(Path(config['provenance']['file']).read_bytes()).hexdigest()!=config['provenance']['sha256']:
            raise MPCError('Project configuration changed during export; no output was installed.')
        # Preserve unrelated files. Replace only known generated artifacts on a rerun.
        old_names = set(previous.get('generated_files', [])) if previous else set()
        for name in old_names:
            _safe_generated_path(output, name)
        new_names = set(manifest['generated_files'])
        for name in new_names:
            dst = _safe_generated_path(output, name)
            if dst.exists() and name not in old_names:
                raise MPCError(f'Refusing to overwrite an untracked file: {dst}')
        output.mkdir(parents=True, exist_ok=True)
        for name in manifest['generated_files']:
            dst = _safe_generated_path(output, name)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(staging / name, dst)
        for name in old_names - new_names:
            obsolete = _safe_generated_path(output, name)
            if obsolete.is_file():
                obsolete.unlink()
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Export EASE MPC echograms with Haas regions; seat count is detected from the file.')
    parser.add_argument('mpc', type=Path, help='Path to the EASE .mpc impact file')
    parser.add_argument('-o', '--output', type=Path, help='Output directory (default: <MPC name>_echograms beside input)')
    parser.add_argument('--frequencies', type=int, nargs='+', default=[500, 1000, 2000], metavar='HZ',
                        help='Bands to export; default: 500 1000 2000')
    parser.add_argument('--dpi', type=int, default=180, help='PNG resolution; default: 180')
    parser.add_argument('--multiviews', action='store_true',
                        help='Also export 3D/XY/YZ/XZ D-ray views, skipping seats without D candidates')
    parser.add_argument('--all-reflections', action='store_true', help='Export every saved path in 3D/XY/YZ/XZ views and CSV')
    parser.add_argument('--combined-pdf', action='store_true', help='Also create combined echogram and enabled multiview PDFs')
    parser.add_argument('--interactive', action='store_true', help='Create an offline 3D HTML viewer (requires Plotly)')
    parser.add_argument('--models', action='store_true', help='Create portable GLB line models for all and D-only paths')
    parser.add_argument('--all-outputs', action='store_true', help='Enable all optional exports, including the Plotly viewer')
    parser.add_argument('--context-dxf', type=Path, help='Optional ASCII DXF backdrop for static/interactive ray views')
    parser.add_argument('--project',type=Path,help='Native EASE project folder or .frd file; reads .fvt/.ffc and optional companions')
    parser.add_argument('--project-config',type=Path,help='JSON face/material categories and optional coefficient curves with provenance')
    parser.add_argument('--project-tolerance',type=float,default=.01,metavar='METRES',help='Reflection point and listener compatibility tolerance; default 0.01 m')
    parser.add_argument('--project-strict',action='store_true',help='Reject known geometry/listener mismatches instead of exporting them with warnings')
    parser.add_argument('--context-z-offset', type=float, default=0., metavar='METRES',
                        help='Add to context DXF Z coordinates only; default: 0')
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args(argv)
    if args.dpi < 50 or args.dpi > 1200:
        parser.error('--dpi must be between 50 and 1200')
    if args.all_outputs:
        args.multiviews = args.all_reflections = args.combined_pdf = args.interactive = args.models = True
    if args.context_dxf and not (args.multiviews or args.all_reflections or args.interactive):
        parser.error('--context-dxf requires --multiviews, --all-reflections or --interactive')
    if args.context_z_offset and not args.context_dxf:
        parser.error('--context-z-offset requires --context-dxf')
    if args.project and args.context_dxf:parser.error('Choose --project or --context-dxf, not both')
    if args.project_strict and not args.project:parser.error('--project-strict requires --project')
    import math
    if not math.isfinite(args.context_z_offset):
        parser.error('--context-z-offset must be finite')
    if not math.isfinite(args.project_tolerance) or args.project_tolerance<=0:parser.error('--project-tolerance must be finite and positive')
    try:
        dataset = read_mpc(args.mpc, include_geometry=any([args.multiviews, args.all_reflections, args.interactive, args.models,args.project,args.project_config]))
        frequencies = list(dict.fromkeys(args.frequencies))
        unsupported = set(frequencies) - set(dataset.frequencies)
        if unsupported:
            raise MPCError(f'Unsupported bands: {sorted(unsupported)}. Available: {dataset.frequencies}')
        output = (args.output.expanduser().resolve() if args.output else
                  dataset.path.with_name(dataset.path.stem + '_echograms'))
        print(f'Detected {len(dataset.seats)} seats, {len(dataset.sources)} source(s), {len(dataset.rays)} saved paths.', flush=True)
        print('Exporting images...', flush=True)
        manifest = export(dataset, output, frequencies, args.dpi, multiviews=args.multiviews,
                          context_dxf=args.context_dxf, context_z_offset=args.context_z_offset,
                          all_reflections=args.all_reflections, combined_pdf=args.combined_pdf,
                          interactive=args.interactive, models=args.models,project_path=args.project,project_config=args.project_config,
                          project_tolerance=args.project_tolerance,project_strict=args.project_strict)
        if manifest.get('native_project'):
            p=manifest['native_project'];print(f"Native project: {p['vertex_count']} vertices, {p['face_count']} faces; {p['compatibility']['matched_nodes']}/{p['compatibility']['checked_nodes']} sampled reflection nodes match.")
            for warning in p['compatibility']['warnings']:print('Project note: '+warning)
        print(f'Exported {manifest["image_count"]} PNG images to: {output}')
        if manifest['multiviews'] is not None:
            print(f"Exported {manifest['multiviews']['view_count']} D-ray multiviews (PNG + PDF) and D_ray_paths.csv.")
        print('Also saved arrivals.csv and summary.json (including region-D candidate counts).')
        return 0
    except ImportError as exc:
        print(f'Missing dependency: {exc.name}. Run: python3 -m pip install -r requirements.txt', file=sys.stderr)
    except (MPCError, OSError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
    return 1
