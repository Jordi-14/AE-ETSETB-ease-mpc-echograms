"""Approximate tracing of theatre design.pdf, p. 4; not a universal echo standard."""
from bisect import bisect_right
TIMES = (0., 10., 20., 30., 40., 50., 60., 70., 80., 90., 100.)
LEVELS = (12.5, 9.5, 5., 0., -4., -8., -11., -13.5, -15.5, -17., -18.)

def boundary(delay: float) -> float | None:
    if not TIMES[0] <= delay <= TIMES[-1]:
        return None
    i = min(bisect_right(TIMES, delay) - 1, len(TIMES) - 2)
    fraction = (delay - TIMES[i]) / (TIMES[i + 1] - TIMES[i])
    return LEVELS[i] + fraction * (LEVELS[i + 1] - LEVELS[i])

def classify(delay: float, relative: float, direct: bool = False) -> str:
    if direct:
        return 'Direct'
    limit = boundary(delay)
    if limit is None:
        return 'outside-diagram'
    return ('D' if relative >= limit else 'C') if delay >= 50 else ('B' if relative >= limit else 'A')
