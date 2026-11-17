"""Optional project-independent reports and recorded-ray models."""
from contextlib import nullcontext
import csv
import json
import math
from pathlib import Path
import struct

import matplotlib
matplotlib.use('Agg')

from .multiview import select_d_paths
from .plotting import _draw_band, _safe_label, _id_slug
from .reader import MPCError

ORDER_COLOURS = ('#30383d', '#1677a8', '#289567', '#df8b21', '#9656ad')


def ray_points(dataset, ray):
    source = next(s for s in dataset.sources if s.id == ray.source_id)
    seat = next(s for s in dataset.seats if s.id == ray.seat_id)
    if len(ray.reflection_points) != ray.order:
        raise MPCError('This export requires validated reflection geometry.')
    return (source.position, *ray.reflection_points, seat.position)


def order_colour(order):
    if order < len(ORDER_COLOURS):
        return ORDER_COLOURS[order]
    from colorsys import hsv_to_rgb
    rgb = hsv_to_rgb((order * .61803398875) % 1, .65, .75)
    return '#' + ''.join(f'{round(v * 255):02x}' for v in rgb)


def scene_limits(dataset, context_edges=()):
    points = [x.position for x in (*dataset.sources, *dataset.seats)]
    points += [p for ray in dataset.rays for p in ray.reflection_points]
    points += [p for edge in context_edges for p in edge]
    limits = []
    for axis in range(3):
        low, high = min(p[axis] for p in points), max(p[axis] for p in points)
        pad = max(.5, (high - low) * .035)
        limits.append((low - pad, high + pad))
    return limits


def export_combined_echograms(dataset, output, frequencies):
    """At most three selected bands per PDF page, for each source/seat pair."""
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    name = Path(output) / 'echograms.pdf'
    with PdfPages(name) as pdf:
        for source in dataset.sources:
            for seat in dataset.seats:
                rays = [r for r in dataset.rays if r.source_id == source.id and r.seat_id == seat.id]
                for start in range(0, len(frequencies), 3):
                    bands = frequencies[start:start + 3]
                    fig, axes = plt.subplots(len(bands), 1, figsize=(8.27, 3.2 * len(bands) + 1.5), squeeze=False)
                    try:
                        fig.subplots_adjust(left=.12, right=.96, top=.86, bottom=.13, hspace=.47)
                        for ax, frequency in zip(axes[:, 0], bands):
                            normalized, count, outside = _draw_band(ax, rays, dataset.frequencies.index(frequency))
                            message = f'{frequency} Hz · {count} D candidates' if normalized else f'{frequency} Hz · no direct reference'
                            if outside:
                                message += f' · {outside} outside diagram'
                            ax.set_title(message, loc='left', fontsize=10)
                        fig.suptitle(f'Seat {seat.label} · Source {source.label}', fontsize=14, fontweight='bold', y=.97)
                        fig.text(.5, .035, 'Approximate assignment Haas curve. Individual paths; no energy summation.\n'
                                 'A missing direct arrival prevents Haas classification.', ha='center', fontsize=8)
                        pdf.savefig(fig)
                    finally:
                        plt.close(fig)
    return [name]


def export_all_reflections(dataset, output, dpi=180, context_edges=(), combined_pdf=False):
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    from mpl_toolkits.mplot3d.art3d import Line3DCollection
    limits = scene_limits(dataset, context_edges)
    output = Path(output)
    directory = output / 'all_reflections'
    directory.mkdir(exist_ok=True)
    files, records = [], []
    combined = output / 'all_reflections.pdf'
    with (PdfPages(combined) if combined_pdf else nullcontext(None)) as pdf:
        for source in dataset.sources:
            for seat in dataset.seats:
                rays = [r for r in dataset.rays if r.source_id == source.id and r.seat_id == seat.id]
                orders = sorted({r.order for r in rays})
                fig = plt.figure(figsize=(10, 8.8))
                try:
                    grid = fig.add_gridspec(2, 2, left=.07, right=.97, bottom=.17, top=.84, wspace=.23, hspace=.32)
                    ax3 = fig.add_subplot(grid[0, 0], projection='3d')
                    axes = [fig.add_subplot(grid[0, 1]), fig.add_subplot(grid[1, 0]), fig.add_subplot(grid[1, 1])]
                    if context_edges:
                        ax3.add_collection3d(Line3DCollection(context_edges, colors='#acbac3', linewidths=.35, alpha=.2))
                    for order in reversed(orders):
                        segments = []
                        for ray in rays:
                            if ray.order == order:
                                points = ray_points(dataset, ray)
                                segments.extend(zip(points, points[1:]))
                        style = dict(colors=order_colour(order), linewidths=1 if order == 0 else .7,
                                     alpha=1 if order == 0 else .55, linestyles='--' if order == 0 else '-')
                        ax3.add_collection3d(Line3DCollection(segments, **style))
                        for ax, (i, j) in zip(axes, [(0, 1), (1, 2), (0, 2)]):
                            if context_edges:
                                ax.add_collection(LineCollection([[(a[i], a[j]), (b[i], b[j])] for a, b in context_edges],
                                                                 colors='#acbac3', linewidths=.35, alpha=.1))
                            ax.add_collection(LineCollection([[(a[i], a[j]), (b[i], b[j])] for a, b in segments], **style))
                    ax3.set(xlim=limits[0], ylim=limits[1], zlim=limits[2], xlabel='X (m)', ylabel='Y (m)', zlabel='Z (m)')
                    ax3.set_box_aspect([b-a for a, b in limits])
                    ax3.view_init(elev=22, azim=-55)
                    ax3.set_title('3D recorded paths')
                    for entity, label in [(source, 'S: ' + source.label), (seat, seat.label)]:
                        p = entity.position
                        ax3.scatter(*p, color='#222', s=22)
                        ax3.text(*p, ' ' + label)
                    for ax, (i, j), title in zip(axes, [(0, 1), (1, 2), (0, 2)], ['Plan XY', 'Side YZ', 'Front XZ']):
                        for entity, label in [(source, 'S'), (seat, seat.label)]:
                            p = entity.position
                            ax.scatter(p[i], p[j], color='#222', s=22)
                            ax.annotate(label, (p[i], p[j]), xytext=(4, 5), textcoords='offset points', fontsize=8)
                        ax.set(xlim=limits[i], ylim=limits[j], xlabel='XYZ'[i]+' (m)', ylabel='XYZ'[j]+' (m)')
                        ax.set_aspect('equal')
                        ax.grid(alpha=.12)
                        ax.set_title(title)
                    reflected = sum(r.order > 0 for r in rays)
                    fig.suptitle(f'Seat {seat.label} · Source {source.label}\n{reflected} saved reflected paths', fontweight='bold', y=.965)
                    if not rays:
                        fig.text(.5, .885, 'No paths saved for this source/receiver pair.', ha='center')
                    handles = [Line2D([0], [0], color=order_colour(o), linestyle='--' if o == 0 else '-',
                                      label=('Direct' if o == 0 else f'Order {o}') + f': {sum(r.order == o for r in rays)}') for o in orders]
                    if handles:
                        fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.5, .08), ncol=min(5, len(handles)), fontsize=8)
                    fig.text(.5, .035, 'All saved paths; coincident projections may overlap. Colour indicates order, not sound level.\n' +
                             ('DXF is visual context only.' if context_edges else 'No room DXF: recorded ray geometry only.'), ha='center', fontsize=8)
                    stem = f'source_{_id_slug(source.id)}_seat_{_id_slug(seat.id)}_{_safe_label(seat.label)}'
                    for ext in ('png', 'pdf'):
                        name = directory / (stem + '.' + ext)
                        fig.savefig(name, dpi=dpi, facecolor='white')
                        files.append(name)
                    if pdf is not None:
                        pdf.savefig(fig)
                finally:
                    plt.close(fig)
                for ray in rays:
                    records.append({'source_id': ray.source_id, 'seat_id': ray.seat_id, 'ray_id': ray.id, 'order': ray.order,
                                    'arrival_ms': ray.arrival_ms, 'faces': json.dumps(ray.face_labels),
                                    'points': json.dumps(ray_points(dataset, ray))})
    csv_path = output / 'all_ray_paths.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['source_id', 'seat_id', 'ray_id', 'order', 'arrival_ms', 'faces', 'points'])
        writer.writeheader()
        writer.writerows(records)
    files.append(csv_path)
    if combined_pdf:
        files.append(combined)
    return files


def export_interactive(dataset, output, frequencies, context_edges=(), project=None, config=None, audit=None):
    from .viewer import export_viewer
    return export_viewer(dataset, output, frequencies, context_edges, project, config, audit)




def _write_glb(dataset, rays, filename, scores=None):
    """glTF line primitives: convert MPC Z-up to glTF Y-up, in metres."""
    import matplotlib.colors as colours
    import matplotlib.pyplot as plt
    binary, views, accessors, meshes, nodes = bytearray(), [], [], [], []
    upper = max(1., math.ceil(max(scores.values(), default=0))) if scores else 1.
    for source in dataset.sources:
        for seat in dataset.seats:
            points, rgb, ids = [], [], []
            for ray in rays:
                if ray.source_id != source.id or ray.seat_id != seat.id:
                    continue
                path = ray_points(dataset, ray)
                color = plt.get_cmap('plasma_r')(scores[ray.id]/upper)[:3] if scores else colours.to_rgb(order_colour(ray.order))
                ids.append(ray.id)
                for a, b in zip(path, path[1:]):
                    for p in (a, b):
                        points.append(struct.unpack('<fff', struct.pack('<fff', p[0], p[2], -p[1])))
                        rgb.extend(color)
            if not points:
                continue
            attrs = {}
            for key, values in [('POSITION', [v for p in points for v in p]), ('COLOR_0', rgb)]:
                offset = len(binary)
                buf = struct.pack('<' + str(len(values)) + 'f', *values)
                binary.extend(buf)
                views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(buf), 'target': 34962})
                acc = {'bufferView': len(views)-1, 'componentType': 5126, 'count': len(points), 'type': 'VEC3'}
                if key == 'POSITION':
                    acc.update(min=[min(p[i] for p in points) for i in range(3)], max=[max(p[i] for p in points) for i in range(3)])
                accessors.append(acc)
                attrs[key] = len(accessors)-1
            label = f'Source {source.label} / Seat {seat.label}'
            meshes.append({'name': label, 'primitives': [{'attributes': attrs, 'mode': 1, 'material': 0}], 'extras': {'ray_ids': ids}})
            nodes.append({'mesh': len(meshes)-1, 'name': label})
    doc = {'asset': {'version': '2.0', 'generator': 'mpc-echograms'}, 'extensionsUsed': ['KHR_materials_unlit'],
           'materials': [{'extensions': {'KHR_materials_unlit': {}}, 'pbrMetallicRoughness': {'baseColorFactor': [1, 1, 1, 1], 'metallicFactor': 0, 'roughnessFactor': 1}, 'doubleSided': True}],
           'buffers': [{'byteLength': len(binary)}], 'bufferViews': views, 'accessors': accessors, 'meshes': meshes, 'nodes': nodes,
           'scenes': [{'nodes': list(range(len(nodes)))}], 'scene': 0,
           'extras': {'input_sha256': dataset.sha256, 'geometry': 'Recorded ray lines only; no room mesh', 'transform': 'glTF XYZ = MPC (X,Z,-Y); metres'}}
    text = json.dumps(doc, separators=(',', ':')).encode('utf-8')
    text += b' ' * (-len(text) % 4)
    binary.extend(b'\0' * (-len(binary) % 4))
    length = 12 + 8 + len(text) + 8 + len(binary)
    Path(filename).write_bytes(struct.pack('<4sII', b'glTF', 2, length) + struct.pack('<I4s', len(text), b'JSON') + text + struct.pack('<I4s', len(binary), b'BIN\0') + binary)


def export_models(dataset, output, frequencies):
    if not dataset.rays:
        return []
    selected = select_d_paths(dataset, frequencies)
    output = Path(output)
    files = [output / 'all_ray_paths.glb']
    _write_glb(dataset, dataset.rays, files[0])
    if selected:
        scores = {p['ray_id']: p['max_excess_dB'] for p in selected}
        name = output / 'D_ray_paths.glb'
        _write_glb(dataset, [r for r in dataset.rays if r.id in scores], name, scores)
        files.append(name)
    return files
