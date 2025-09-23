from typing import List, Optional, Tuple
import math

def sanitize_series(values: List[Optional[float]]) -> List[float]:
    out = []
    for v in values:
        if v is None:
            out.append(float('nan'))
        else:
            try:
                fv = float(v)
                if math.isfinite(fv):
                    out.append(fv)
                else:
                    out.append(float('nan'))
            except (ValueError, TypeError):
                out.append(float('nan'))
    return out

def moving_average(vals: List[float], window: int = 7) -> List[float]:
    if window <= 1:
        return vals[:]
    out = []
    q = []
    s = 0.0
    for i, v in enumerate(vals):
        if not math.isnan(v):
            q.append(v)
            s += v
        else:
            q.append(float('nan'))
        if len(q) > window:
            old = q.pop(0)
            if not math.isnan(old):
                s -= old
        # compute mean of valid in q
        valid = [x for x in q if not math.isnan(x)]
        out.append(sum(valid) / len(valid) if valid else float('nan'))
    return out

def line_points(x1, y1, x2, y2) -> List[Tuple[int, int]]:
    """Bresenham to connect points nicely in the grid."""
    points = []
    dx = abs(x2 - x1)
    dy = -abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx + dy
    x, y = x1, y1
    while True:
        points.append((x, y))
        if x == x2 and y == y2:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    return points