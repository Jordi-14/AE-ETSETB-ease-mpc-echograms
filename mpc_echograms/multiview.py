"""Draw each seat's remaining region-D paths in four views, with one shared scale."""
import csv
import json
import math
from pathlib import Path

from .haas import boundary, classify
from .reader import MPCError
from .plotting import _safe_label, _id_slug


def select_d_paths(dataset, frequencies):
    """One record per physical path; score by worst D excess in the selected bands."""
    direct = {}
    for ray in dataset.rays:
        key = (ray.source_id, ray.seat_id)
        if ray.order == 0 and (key not in direct or ray.arrival_ms < direct[key].arrival_ms):
            direct[key] = ray
    selected = []
    for ray in dataset.rays:
        ref = direct.get((ray.source_id, ray.seat_id))
        if ref is None or ray.order == 0:
            continue
        delay = ray.arrival_ms - ref.arrival_ms
        bands = []
        for frequency in frequencies:
            index = dataset.frequencies.index(frequency)
            relative = ray.levels_db[index] - ref.levels_db[index]
            if classify(delay, relative) == 'D':
                bands.append({'frequency_Hz': frequency, 'excess_dB': relative - boundary(delay)})
        if not bands:
            continue
        if len(ray.reflection_points) != ray.order or len(ray.face_labels) != ray.order:
            raise MPCError('Multiview requires decoded reflection geometry. Read with include_geometry=True.')
        source = next(s for s in dataset.sources if s.id == ray.source_id)
        seat = next(s for s in dataset.seats if s.id == ray.seat_id)
        worst = max(bands, key=lambda band: band['excess_dB'])
        selected.append({'source_id': ray.source_id, 'seat_id': ray.seat_id, 'ray_id': ray.id,
                         'arrival_ms': ray.arrival_ms, 'delay_after_direct_ms': delay,
                         'max_excess_dB': worst['excess_dB'],
                         'worst_frequency_Hz': worst['frequency_Hz'], 'D_bands': bands,
                         'faces': list(ray.face_labels),
                         'points': [source.position, *ray.reflection_points, seat.position]})
    return selected


def export_multiviews(dataset, output: Path, frequencies, dpi=180, context_edges=(), combined_pdf=False):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from contextlib import nullcontext
    from matplotlib.colors import Normalize
    from matplotlib.cm import ScalarMappable
    from matplotlib.collections import LineCollection
    from mpl_toolkits.mplot3d.art3d import Line3DCollection

    output = Path(output)
    selected = select_d_paths(dataset, frequencies)
    upper = max(1., float(math.ceil(max((p['max_excess_dB'] for p in selected), default=0))))
    norm, cmap = Normalize(0, upper), plt.get_cmap('plasma_r')
    all_points = [s.position for s in (*dataset.sources, *dataset.seats)]
    all_points += [p for ray in dataset.rays for p in ray.reflection_points]
    all_points += [p for edge in context_edges for p in edge]
    limits = []
    for axis in range(3):
        low, high = min(p[axis] for p in all_points), max(p[axis] for p in all_points)
        padding = max(.5, (high - low) * .035)
        limits.append((low - padding, high + padding))
    skipped, generated = [], []
    combined_path = output / 'D_ray_multiviews.pdf'
    with (PdfPages(combined_path) if combined_pdf and selected else nullcontext(None)) as combined:
        for source in dataset.sources:
            for seat in dataset.seats:
                paths = sorted([p for p in selected if p['source_id'] == source.id and p['seat_id'] == seat.id],
                               key=lambda p: p['max_excess_dB'])
                if not paths:
                    has_direct = any(r.order == 0 and r.source_id == source.id and r.seat_id == seat.id
                                     for r in dataset.rays)
                    skipped.append({'source_id': source.id, 'seat_id': seat.id,
                                    'reason': 'no-region-D-candidates' if has_direct else 'no-direct-reference'})
                    continue
                with plt.rc_context({'font.family': 'DejaVu Sans', 'font.size': 9,
                                     'axes.spines.top': False, 'axes.spines.right': False}):
                    fig = plt.figure(figsize=(10, 8.8))
                    try:
                        grid = fig.add_gridspec(2, 2, left=.07, right=.92, bottom=.17, top=.84,
                                               wspace=.23, hspace=.32)
                        ax3 = fig.add_subplot(grid[0, 0], projection='3d')
                        plan, side, front = (fig.add_subplot(grid[0, 1]), fig.add_subplot(grid[1, 0]),
                                             fig.add_subplot(grid[1, 1]))
                        if context_edges:
                            ax3.add_collection3d(Line3DCollection(context_edges, colors='#b0bdc4',
                                                                  linewidths=.35, alpha=.22))
                        direct = (source.position, seat.position)
                        ax3.plot(*zip(*direct), color='#707a81', linewidth=1, linestyle='--')
                        for p in paths:
                            color = cmap(norm(p['max_excess_dB']))
                            ax3.plot(*zip(*p['points']), color=color, linewidth=1.2, alpha=.85)
                            ax3.scatter(*zip(*p['points'][1:-1]), s=6, color=color)
                        for point, label, color in [(source.position, 'S', '#222222'),
                                                     (seat.position, seat.label, '#159c91')]:
                            ax3.scatter(*point, color=color, s=25)
                            ax3.text(*point, ' ' + label)
                        ax3.set(xlim=limits[0], ylim=limits[1], zlim=limits[2],
                                xlabel='X (m)', ylabel='Y (m)', zlabel='Z (m)')
                        ax3.set_box_aspect([high - low for low, high in limits])
                        ax3.view_init(elev=22, azim=-55)
                        ax3.set_title('3D — saved reflection paths', fontsize=9)
                        for ax, axes, title in [(plan, (0, 1), 'Plan XY'), (side, (1, 2), 'Side elevation YZ'),
                                                 (front, (0, 2), 'Front elevation XZ')]:
                            i, j = axes
                            if context_edges:
                                segments = [[(a[i], a[j]), (b[i], b[j])] for a, b in context_edges]
                                ax.add_collection(LineCollection(segments, colors='#b0bdc4',
                                                                 linewidths=.35, alpha=.23))
                            ax.plot([p[i] for p in direct], [p[j] for p in direct], color='#707a81',
                                    linewidth=.8, linestyle='--')
                            for p in paths:
                                color = cmap(norm(p['max_excess_dB']))
                                ax.plot([v[i] for v in p['points']], [v[j] for v in p['points']],
                                        color=color, linewidth=1.1, alpha=.85)
                                ax.scatter([v[i] for v in p['points'][1:-1]], [v[j] for v in p['points'][1:-1]],
                                           s=6, color=color)
                            for point, label, color in [(source.position, 'S', '#222222'),
                                                         (seat.position, seat.label, '#159c91')]:
                                ax.scatter(point[i], point[j], color=color, s=24, zorder=5)
                                ax.annotate(label, (point[i], point[j]), xytext=(5, 4),
                                            textcoords='offset points', fontsize=8)
                            ax.set(xlim=limits[i], ylim=limits[j], xlabel='XYZ'[i] + ' (m)', ylabel='XYZ'[j] + ' (m)')
                            ax.set_aspect('equal')
                            ax.grid(alpha=.1)
                            ax.set_title(title, fontsize=10)
                        worst = max(paths, key=lambda p: p['max_excess_dB'])
                        fig.suptitle(f'Seat {seat.label} · Source {source.label}\n{len(paths)} region-D candidate paths',
                                     fontweight='bold', fontsize=13, y=.965)
                        fig.text(.5, .885, f"Largest excess: r{worst['ray_id']} · +{worst['max_excess_dB']:.2f} dB "
                                 f"at {worst['worst_frequency_Hz']} Hz · delay +{worst['delay_after_direct_ms']:.2f} ms",
                                 ha='center', fontsize=10)
                        color_ax = fig.add_axes([.945, .28, .018, .40])
                        bar = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), cax=color_ax)
                        bar.set_label('Maximum excess above D boundary (dB)', fontsize=8)
                        bar.ax.tick_params(labelsize=8)
                        fig.text(.5, .09, 'Each path appears once, coloured by its largest D excess in the selected bands.\n'
                                 'One common colour scale across all seats and sources; coincident segments may overlap.',
                                 ha='center', fontsize=8)
                        fig.text(.5, .035, ('Grey: optional DXF context. ' if context_edges else 'No room DXF supplied. ') +
                                 'Dashed grey: direct path. Coloured vertices: saved reflection points.\n'
                                 'Approximate assignment Haas boundary. These are ray paths, not sound-energy coverage.',
                                 ha='center', fontsize=8)
                        if combined is not None:
                            combined.savefig(fig)
                        name = f'source_{_id_slug(source.id)}_seat_{_id_slug(seat.id)}_{_safe_label(seat.label)}_D_multiview'
                        for extension in ('png', 'pdf'):
                            path = output / (name + '.' + extension)
                            fig.savefig(path, dpi=dpi, facecolor='white')
                            generated.append(path)
                    finally:
                        plt.close(fig)
    if combined_pdf and selected:
        generated.append(combined_path)
    # Save all D paths, not just paths that received a label in a plot.
    path_file = output / 'D_ray_paths.csv'
    with path_file.open('w', newline='', encoding='utf-8') as stream:
        fields = ['source_id', 'seat_id', 'ray_id', 'arrival_ms', 'delay_after_direct_ms',
                  'max_excess_dB', 'worst_frequency_Hz', 'D_bands', 'faces', 'points']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({**p, 'D_bands': json.dumps(p['D_bands']), 'faces': json.dumps(p['faces']),
                          'points': json.dumps(p['points'])} for p in selected)
    generated.append(path_file)
    return generated, {'view_count': sum(p.name.endswith('_D_multiview.png') for p in generated), 'unique_D_paths': len(selected),
                       'colour_range_dB': [0, upper], 'skipped': skipped}
