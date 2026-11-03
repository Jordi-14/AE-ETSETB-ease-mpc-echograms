"""Strict reader for the EASE 4.x binary impact layout observed in EASE 4.4.

This layout is not a public AFMG interchange specification. Byte offsets below
are format fields, not coordinates or seat counts. Unexpected layouts are rejected.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import math
import re
import struct

FREQUENCIES = (100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000,
               1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000)
RAY_SIGNATURE = struct.pack('<III', 8, 4608, 0)

class MPCError(ValueError):
    """Invalid or unsupported impact file."""

@dataclass(frozen=True)
class Seat:
    id: int
    label: str
    position: tuple[float, float, float]

@dataclass(frozen=True)
class Source:
    id: int
    label: str
    position: tuple[float, float, float]

@dataclass(frozen=True)
class Ray:
    id: int
    seat_id: int
    source_id: int
    order: int
    arrival_ms: float
    levels_db: tuple[float, ...]
    reflection_points: tuple[tuple[float, float, float], ...] = ()
    face_labels: tuple[str, ...] = ()

@dataclass(frozen=True)
class Dataset:
    path: Path
    seats: tuple[Seat, ...]
    sources: tuple[Source, ...]
    rays: tuple[Ray, ...]
    frequencies: tuple[int, ...]
    sha256: str


def _unpack(fmt: str, data: bytes, offset: int):
    try:
        return struct.unpack_from('<' + fmt, data, offset)
    except struct.error as exc:
        raise MPCError(f'Truncated MPC data at byte {offset}.') from exc


def _chunk(data: bytes, tag: bytes) -> tuple[bytes, int]:
    candidates = []
    for match in re.finditer(re.escape(tag), data):
        p = match.start()
        if p + 20 > len(data):
            continue
        version, _variant, _kind, count, size = _unpack('HHIII', data, p + 4)
        if version == 14 and count <= 10_000_000 and p + 20 + size <= len(data):
            candidates.append((data[p + 20:p + 20 + size], count))
    if len(candidates) != 1:
        raise MPCError(f'Expected one supported {tag.decode()} chunk; found {len(candidates)}. '
                       'Use an EASE 4.x binary Impact (.mpc) export.')
    return candidates[0]


def _metadata(payload: bytes, count: int, source: bool = False):
    result = []
    pos = 0
    seen = set()
    for _ in range(count):
        size, = _unpack('I', payload, pos)
        pos += 4
        if size == 0 or pos + size > len(payload):
            raise MPCError('Invalid length in source/seat metadata.')
        body = payload[pos:pos + size]
        pos += size
        entity_id, = _unpack('I', body, 4)
        length_at = 20 if source else 8
        label_length, = _unpack('H', body, length_at)
        label_start = length_at + 2
        xyz_at = label_start + label_length + 10
        if xyz_at + 12 > len(body):
            raise MPCError('Invalid label or coordinate length in source/seat metadata.')
        label = body[label_start:label_start + label_length].decode('cp1252', errors='replace').rstrip('\0')
        position = _unpack('fff', body, xyz_at)
        if entity_id <= 0 or entity_id in seen or not all(math.isfinite(v) for v in position):
            raise MPCError('Duplicate/invalid source or seat ID, or invalid coordinates.')
        seen.add(entity_id)
        result.append((Source if source else Seat)(entity_id, label or str(entity_id), position))
    if pos != len(payload):
        raise MPCError('Unsupported trailing data in source/seat metadata.')
    return tuple(result)


def _reflection_geometry(payload: bytes, origin: int, end: int, order: int):
    """Read the observed named F-number face nodes; reject ambiguous geometry."""
    points, labels = [], []
    start = origin + 358
    for match in re.finditer(rb'F[0-9]{1,10}', payload[start:end]):
        label_at = start + match.start()
        label = match.group().decode('ascii')
        # Ignore accidental F/digit patterns inside binary floating-point values.
        if label_at < 2 or _unpack('H', payload, label_at - 2)[0] != len(label):
            continue
        point_at = start + match.end() + 4
        if point_at + 12 > end:
            raise MPCError('Truncated reflection-point geometry.')
        point = _unpack('fff', payload, point_at)
        if not all(math.isfinite(value) for value in point):
            raise MPCError('Non-finite reflection-point coordinates.')
        labels.append(label)
        points.append(point)
    if len(points) != order:
        raise MPCError(f'Unsupported reflection geometry: expected {order} F-number face nodes, '
                       f'found {len(points)}. Run without --multiviews for echograms only.')
    return tuple(points), tuple(labels)


def read_mpc(path: str | Path, *, include_geometry: bool = False) -> Dataset:
    path = Path(path).expanduser().resolve()
    data = path.read_bytes()
    if not data.startswith(b'EASE') or len(data) < 32 or data[10:12] != b'MP':
        raise MPCError('This is not a supported EASE binary Impact (.mpc) file.')
    seat_payload, seat_count = _chunk(data, b'SEAT')
    source_payload, source_count = _chunk(data, b'LSPK')
    seats = _metadata(seat_payload, seat_count)
    sources = _metadata(source_payload, source_count, source=True)
    if not seats or not sources:
        raise MPCError('The MPC declares no seats or no sound sources.')
    seat_by_id = {s.id: s for s in seats}
    source_by_id = {s.id: s for s in sources}
    payload, count = _chunk(data, b'RAYS')
    headers = [m.start() for m in re.finditer(re.escape(RAY_SIGNATURE), payload)]
    if len(headers) != count:
        raise MPCError(f'Unsupported or damaged ray layout: found {len(headers)} records, '
                       f'but the file declares {count}.')
    rays = []
    propagation_speeds = []
    for index, h in enumerate(headers):
        origin = h + 26
        end = headers[index + 1] if index + 1 < count else len(payload)
        if origin + 338 > end:
            raise MPCError(f'Truncated primary impact record {index + 1}.')
        source_id, = _unpack('I', payload, h + 16)
        order, = _unpack('H', payload, h + 22)
        seat_id, = _unpack('I', payload, origin + 170)
        endpoint_type, = _unpack('I', payload, origin + 174)
        node_count, = _unpack('H', payload, origin + 336)
        if source_id not in source_by_id or seat_id not in seat_by_id:
            raise MPCError(f'Impact {index + 1} references an undeclared source/seat ID.')
        if endpoint_type != 4 or order > 100 or node_count != order + 2:
            raise MPCError(f'Unsupported impact structure in record {index + 1}.')
        for actual, expected in [(_unpack('fff', payload, origin), source_by_id[source_id].position),
                                 (_unpack('fff', payload, origin + 178), seat_by_id[seat_id].position)]:
            if math.dist(actual, expected) > .002:
                raise MPCError(f'Impact {index + 1} does not match its source/seat coordinates.')
        arrival_ms, = _unpack('f', payload, origin + 190)
        if not math.isfinite(arrival_ms) or arrival_ms < 0:
            raise MPCError(f'Invalid arrival time in record {index + 1}.')
        emitted = _unpack('21h', payload, origin + 22)
        attenuation = _unpack('21h', payload, origin + 200)
        levels = tuple((a - b) / 100 for a, b in zip(emitted, attenuation))
        points, labels = _reflection_geometry(payload, origin, end, order) if include_geometry else ((), ())
        if include_geometry:
            polyline = (source_by_id[source_id].position, *points, seat_by_id[seat_id].position)
            length = sum(math.dist(a, b) for a, b in zip(polyline, polyline[1:]))
            if length > .001 and arrival_ms > 0:
                propagation_speeds.append(length / (arrival_ms / 1000))
        rays.append(Ray(index + 1, seat_id, source_id, order, arrival_ms, levels, points, labels))
    if propagation_speeds:
        # Saved times describe propagation (source delay is separate). Reject malformed
        # node paths instead of plotting plausible-looking but unvalidated coordinates.
        low, high = min(propagation_speeds), max(propagation_speeds)
        if low < 250 or high > 450 or high - low > .001 * high:
            raise MPCError('Reflection geometry is inconsistent with saved propagation times. '
                           'Run without --multiviews for echograms only.')
    return Dataset(path, seats, sources, tuple(rays), FREQUENCIES, hashlib.sha256(data).hexdigest())
