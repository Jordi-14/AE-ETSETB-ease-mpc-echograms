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
        manifest = json.loads((output / 'summary.json').read_text())
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


def export(dataset, output, frequencies, dpi):
    from .plotting import export_images
    previous = _old_manifest(output)
    if previous and previous.get('input_file') != str(dataset.path):
        raise MPCError('This output folder was generated from a different MPC. Choose another --output.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.mpc-echograms-', dir=output.parent) as temp:
        staging = Path(temp)
        images = export_images(dataset, staging, frequencies=tuple(frequencies), dpi=dpi)
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
            ],
            'generated_files': sorted([str(p.relative_to(staging)) for p in images] +
                                      ['arrivals.csv', 'summary.json']),
        }
        (staging / 'summary.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
        if hashlib.sha256(dataset.path.read_bytes()).hexdigest() != dataset.sha256:
            raise MPCError('Input MPC changed during export; no output was installed. Run again.')
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
    parser.add_argument('--version', action='version', version=__version__)
    args = parser.parse_args(argv)
    if args.dpi < 50 or args.dpi > 1200:
        parser.error('--dpi must be between 50 and 1200')
    try:
        dataset = read_mpc(args.mpc)
        frequencies = list(dict.fromkeys(args.frequencies))
        unsupported = set(frequencies) - set(dataset.frequencies)
        if unsupported:
            raise MPCError(f'Unsupported bands: {sorted(unsupported)}. Available: {dataset.frequencies}')
        output = (args.output.expanduser().resolve() if args.output else
                  dataset.path.with_name(dataset.path.stem + '_echograms'))
        print(f'Detected {len(dataset.seats)} seats, {len(dataset.sources)} source(s), {len(dataset.rays)} saved paths.', flush=True)
        print('Exporting images...', flush=True)
        manifest = export(dataset, output, frequencies, args.dpi)
        print(f'Exported {manifest["image_count"]} PNG images to: {output}')
        print('Also saved arrivals.csv and summary.json (including region-D candidate counts).')
        return 0
    except ImportError as exc:
        print(f'Missing dependency: {exc.name}. Run: python3 -m pip install -r requirements.txt', file=sys.stderr)
    except (MPCError, OSError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
    return 1
