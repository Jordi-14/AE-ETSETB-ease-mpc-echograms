"""Export seat/source band echograms with the assignment's Haas overlay."""
from __future__ import annotations

import math
from pathlib import Path
import re
import unicodedata

from .haas import LEVELS, TIMES, boundary, classify


def _safe_label(label: str) -> str:
    """A short, portable filename component; the numeric ID ensures uniqueness."""
    text = unicodedata.normalize("NFKD", str(label)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_-")[:64] or "unnamed"


def _id_slug(entity_id: int) -> str:
    """Readable filenames for EASE's uint32-encoded negative image IDs."""
    return f'mirror_{2 ** 32 - entity_id:03}' if entity_id >= 2 ** 31 else f'{entity_id:03}'


def _finite(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _shade_haas(ax, lower: float, upper: float) -> None:
    """Draw only the published 0–100 ms diagram; never extrapolate its curve."""
    t = [float(TIMES[0]) + i * (float(TIMES[-1]) - float(TIMES[0])) / 1000 for i in range(1001)]
    levels = [boundary(x) for x in t]
    left = [(x, y) for x, y in zip(t, levels) if x <= 50 and y is not None]
    right = [(x, y) for x, y in zip(t, levels) if x >= 50 and y is not None]
    if left:
        ax.fill_between([x for x, _ in left], [y for _, y in left], upper,
                        color="#ece4ce", alpha=.65, zorder=-5)
    if right:
        ax.fill_between([x for x, _ in right], lower, [y for _, y in right],
                        color="#e7eef5", alpha=.75, zorder=-5)
        ax.fill_between([x for x, _ in right], [y for _, y in right], upper,
                        color="#f4c6c5", alpha=.65, zorder=-5)
    ax.plot(TIMES, LEVELS, color="#62676b", linewidth=1.1)
    ax.axvline(50, color="#777777", linewidth=.8, linestyle="--")
    for zone, x, y in [("A", 23, lower + .24 * (upper - lower)),
                       ("B", 20, upper - .07 * (upper - lower)),
                       ("C", 88, lower + .24 * (upper - lower)),
                       ("D", 87, upper - .12 * (upper - lower))]:
        ax.text(x, y, zone, color="#9b8b8b" if zone == "D" else "#9aa3a9",
                fontsize=22, fontweight="bold", alpha=.55, zorder=-3)


def _draw_band(ax, impacts, band_index: int) -> tuple[bool, int, int]:
    """Draw one band. Missing direct sound uses absolute axes with no Haas claim."""
    valid = [r for r in impacts if _finite(r.arrival_ms) and _finite(r.levels_db[band_index])]
    direct_options = [r for r in valid if r.order == 0]
    direct = min(direct_options, key=lambda r: r.arrival_ms) if direct_options else None
    normalized = direct is not None
    samples = []
    for ray in valid:
        delay = ray.arrival_ms - direct.arrival_ms if normalized else ray.arrival_ms
        level = ray.levels_db[band_index] - direct.levels_db[band_index] if normalized else ray.levels_db[band_index]
        zone = classify(delay, level, direct=ray is direct) if normalized else "unclassified"
        limit = boundary(delay) if normalized else None
        margin = level - limit if limit is not None else None
        samples.append((ray, delay, level, zone, margin))

    if normalized:
        lower = min(-45., min((p[2] for p in samples), default=-45.) - 2)
        # Very small levels are omitted below the display floor; data stay in CSVs.
        lower = max(lower, -100.)
        upper = max(14., max((p[2] for p in samples), default=0.) + 4)
        _shade_haas(ax, lower, upper)
    else:
        level_values = [p[2] for p in samples]
        lower = min(level_values) - 8 if level_values else 0.
        upper = max(level_values) + 8 if level_values else 100.
        if upper - lower < 20:
            upper = lower + 20

    candidates = [p for p in samples if p[3] == "D"]
    unknown = sum(p[3] == "outside-diagram" for p in samples)
    for ray, delay, level, zone, margin in samples:
        if ray is direct:
            continue
        color = "#bd2533" if zone == "D" else "#26728e"
        ax.vlines(delay, lower, max(level, lower), color=color, linewidth=.8, alpha=.8)
        if zone == "D":
            ax.scatter(delay, level, s=19, color=color, zorder=5)
    if direct is not None:
        ax.scatter(0, 0, s=25, color="#202b35", zorder=7)
        ax.annotate("Direct sound: 0 ms, 0 dB", (0, 0), xytext=(8, 6),
                    textcoords="offset points", fontsize=8)

    chosen = []
    for candidate in sorted(candidates, key=lambda p: -p[4]):
        if all(abs(candidate[1] - old[1]) > 2 for old in chosen):
            chosen.append(candidate)
        if len(chosen) == 3:
            break
    for i, (ray, delay, level, zone, margin) in enumerate(sorted(chosen, key=lambda p: p[1])):
        ax.annotate(f"r{ray.id} / +{margin:.1f} dB", (delay, level),
                    xytext=(.59 + .14 * i, .87 - .10 * (i % 2)), textcoords="axes fraction", fontsize=8,
                    ha="center", bbox={"facecolor": "white", "edgecolor": "none", "alpha": .65},
                    color="#a7192a", arrowprops={"arrowstyle": "-", "lw": .5, "color": "#a7192a"})

    latest = max((p[1] for p in samples), default=100.)
    earliest = min((p[1] for p in samples), default=0.)
    ax.set_xlim(min(-1.5, earliest - 1), max(100, latest * 1.025))
    ax.set_ylim(lower, upper)
    ax.set_xlabel("Reflection delay after direct sound (ms)" if normalized else "Absolute arrival time (ms)")
    ax.set_ylabel("Level relative to direct sound (dB)" if normalized else "Saved individual-path level (dB)")
    ax.grid(alpha=.14)
    if not valid:
        ax.text(.5, .52, "No impacts saved for this seat and source", transform=ax.transAxes,
                ha="center", va="center", fontsize=13, color="#5b6970")
    elif not normalized:
        ax.text(.5, .95, "No direct arrival in this band — Haas classification unavailable",
                transform=ax.transAxes, ha="center", va="top", fontsize=9,
                color="#a7192a", bbox={"facecolor": "white", "edgecolor": "none", "alpha": .9})
    return normalized, len(candidates), unknown


def export_images(dataset, output_dir: Path, frequencies: tuple[int, ...] = (500, 1000, 2000),
                  dpi: int = 180) -> list[Path]:
    """Export one PNG for each declared seat, selected band and active source.

    All declared seats are included, even seats without saved impacts. For multiple
    sources, images are separated into source directories. Direct-reference
    normalization is always per source, per seat and per frequency.
    """
    # The CLI can display --help and parse unsupported files without importing MPL.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_dir = Path(output_dir)
    indices = {frequency: tuple(dataset.frequencies).index(frequency) for frequency in frequencies}
    active_ids = {r.source_id for r in dataset.rays}
    sources = [source for source in dataset.sources if not active_ids or source.id in active_ids]
    multi_source = len(sources) > 1
    paths = []
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False}):
        for source in sources:
            directory = output_dir / f"source_{_id_slug(source.id)}_{_safe_label(source.label)}" if multi_source else output_dir
            directory.mkdir(parents=True, exist_ok=True)
            for seat in dataset.seats:
                impacts = [r for r in dataset.rays if r.source_id == source.id and r.seat_id == seat.id]
                for frequency in frequencies:
                    fig, ax = plt.subplots(figsize=(10, 5.8))
                    fig.subplots_adjust(left=.10, right=.97, bottom=.21, top=.78)
                    try:
                        normalized, count, unknown = _draw_band(ax, impacts, indices[frequency])
                        summary = f"{frequency} Hz · {count} individual region-D candidates" if normalized else f"{frequency} Hz · no direct reference"
                        if unknown:
                            summary += f" · {unknown} outside Haas diagram"
                        ax.set_title(summary, loc="left", fontsize=10)
                        fig.suptitle(f"Seat {seat.label} · Source {source.label}", fontsize=14,
                                     fontweight="bold", y=.98)
                        xyz = ", ".join(f"{float(value):.2f}" for value in seat.position)
                        fig.text(.5, .91, f"Seat coordinates: ({xyz}) m", ha="center", fontsize=9)
                        fig.text(.5, .055,
                                 "Red peaks: region-D candidates. Blue: other arrivals. rID identifies a path in the exported tables.",
                                 ha="center", fontsize=8)
                        fig.text(.5, .025,
                                 "Approximate assignment Haas curve (0–100 ms). Individual paths; no time-bin energy summation. Confirm borderline cases in Probe.",
                                 ha="center", fontsize=7.5)
                        path = directory / f"seat_{_id_slug(seat.id)}_{_safe_label(seat.label)}_{frequency}Hz.png"
                        fig.savefig(path, dpi=dpi, facecolor="white")
                        paths.append(path)
                    finally:
                        plt.close(fig)
    return paths
