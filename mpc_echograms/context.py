"""Optional wireframe from plain ASCII DXF model-space faces (no CAD dependency)."""
from pathlib import Path
import math
from .reader import MPCError


def read_context_edges(path: Path, z_offset: float = 0.):
    """Read 3DFACE and closed 3D POLYLINE; ignore blocks, inserts and 2D entities."""
    data = Path(path).read_bytes()
    if data.startswith(b'AutoCAD Binary DXF'):
        raise MPCError('Context must be an ASCII DXF, not a binary DXF.')
    lines = data.decode('utf-8-sig', errors='replace').splitlines()
    if len(lines) % 2:
        raise MPCError('Invalid ASCII DXF: incomplete group-code pair.')
    try:
        pairs = [(int(lines[i].strip()), lines[i + 1].strip()) for i in range(0, len(lines), 2)]
    except ValueError as exc:
        raise MPCError('Invalid ASCII DXF group code.') from exc
    records, current, section, pending_section = [], [], '', False
    for code, value in pairs:
        if code == 0:
            if current and section == 'ENTITIES':
                records.append(dict(current))
            current = []
            if value == 'SECTION':
                pending_section = True
            elif value == 'ENDSEC':
                section = ''
            current.append((code, value))
        else:
            if pending_section and code == 2:
                section, pending_section = value, False
            current.append((code, value))
    polygons, vertices, polyline = [], [], None
    try:
        for rec in records:
            kind = rec.get(0)
            if kind == '3DFACE':
                polygons.append([tuple(float(rec.get(base + j, 0)) + (z_offset if base == 30 else 0)
                                       for base in (10, 20, 30)) for j in range(4)])
            elif kind == 'POLYLINE':
                flags = int(rec.get(70, '0'))
                polyline = bool(flags & 8 and flags & 1 and not flags & (16 | 64))
                vertices = []
            elif kind == 'VERTEX' and polyline:
                vertices.append(tuple(float(rec.get(base, 0)) + (z_offset if base == 30 else 0)
                                      for base in (10, 20, 30)))
            elif kind == 'SEQEND':
                if polyline and len(vertices) >= 3:
                    polygons.append(vertices)
                vertices, polyline = [], None
    except ValueError as exc:
        raise MPCError('Invalid numeric face coordinate in context DXF.') from exc
    edges = {}
    for polygon in polygons:
        if not all(math.isfinite(v) for p in polygon for v in p):
            raise MPCError('Non-finite coordinate in context DXF.')
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            if math.dist(a, b) > 1e-8:
                key = tuple(sorted((tuple(round(x, 6) for x in a), tuple(round(x, 6) for x in b))))
                edges[key] = (a, b)
    if not edges:
        raise MPCError('Context DXF has no supported model-space 3DFACEs or closed 3D POLYLINEs.')
    return list(edges.values())
