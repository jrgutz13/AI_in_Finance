"""Flight planning for fractal landscapes: a smooth, endless, collision-free
camera path, plus slowly changing light and color.

The horizontal route is an epicycle — a large circle with a smaller circle
riding on it, turning at an irrational rate (the golden ratio). It stays
inside a fixed region of the landscape forever, never retraces itself, and
has no sharp turns.

Altitude comes from measurement: the ground height is probed (see
mb.depth_probe) at points every half rock-width along the route, the
required height is ground + clearance, and the flight altitude is that
requirement "dilated" (max over +-R) and then blurred with a kernel no wider
than R. That combination is provably never below the requirement, while
rising smoothly well before each spire.

Every pose is a pure function of distance flown, so chunks rendered in any
order (or after a crash) join seamlessly.
"""

import math

import numpy as np

GOLDEN = (1.0 + 5.0 ** 0.5) / 2.0


class Route:
    """Arc-length-parametrised epicycle around `center` (2D), in units of L."""

    def __init__(self, center, L, seed, r1=14.0, r2=6.0):
        rng = np.random.default_rng([seed, 4242])
        self.center = np.asarray(center, np.float64)
        self.L = L
        self.r1, self.r2 = r1 * L, r2 * L
        self.k = -GOLDEN * rng.uniform(0.9, 1.1)       # irrational rate: no repeats
        self.phi = rng.uniform(0.0, 2 * math.pi)
        self.u0 = rng.uniform(0.0, 2 * math.pi)
        self.dir = rng.choice([-1.0, 1.0])
        # arc-length table: s(u) sampled finely, inverted by interpolation
        self._u = None

    def _build(self, s_max):
        du = 0.002
        n = int(s_max / (min(self.r1, self.r2) * du) * 1.2) + 1000
        while True:
            u = self.u0 + self.dir * np.arange(n) * du
            dp = self.xy_u(u)
            seg = np.linalg.norm(np.diff(dp, axis=0), axis=1)
            s = np.concatenate([[0.0], np.cumsum(seg)])
            if s[-1] >= s_max:
                break
            n *= 2
        self._u, self._s = u, s

    def xy_u(self, u):
        u = np.asarray(u, np.float64)
        v = (self.r1 * np.stack([np.cos(u), np.sin(u)], -1)
             + self.r2 * np.stack([np.cos(self.k * u + self.phi),
                                   np.sin(self.k * u + self.phi)], -1))
        return self.center + v

    def xy(self, s):
        """Position(s) at arc length s (same units as L)."""
        if self._u is None or np.max(s) > self._s[-1]:
            self._build(max(float(np.max(s)) * 1.5, 100 * self.L))
        return self.xy_u(np.interp(s, self._s, self._u))


def dilate_blur(req, radius):
    """Smooth curve that is never below `req`: max-filter then a Hann blur
    whose support is no wider than the max-filter."""
    n = len(req)
    pad = np.concatenate([np.full(radius, req[0]), req, np.full(radius, req[-1])])
    win = np.lib.stride_tricks.sliding_window_view(pad, 2 * radius + 1)
    dil = win.max(axis=1)
    w = np.hanning(2 * radius + 3)[1:-1]
    w /= w.sum()
    pad2 = np.concatenate([np.full(radius, dil[0]), dil, np.full(radius, dil[-1])])
    out = np.convolve(pad2, w, mode="valid")
    return out[:n]


def catmull(values, x):
    """Catmull-Rom interpolation of uniformly spaced `values` at float index x
    — smooth (continuous slope), so the camera never jerks between samples."""
    x = np.asarray(x, np.float64)
    i = np.clip(np.floor(x).astype(int), 0, len(values) - 2)
    t = x - i
    p0 = values[np.clip(i - 1, 0, len(values) - 1)]
    p1 = values[i]
    p2 = values[np.clip(i + 1, 0, len(values) - 1)]
    p3 = values[np.clip(i + 2, 0, len(values) - 1)]
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                  + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)


class Flight:
    """Poses for every frame, from a route plus measured ground heights."""

    def __init__(self, route, ground, ds, clearance, lookahead=1.3, pitch_deg=8.0,
                 bank=0.9, radius=8):
        self.route, self.ds = route, ds
        L = route.L
        self.alt = dilate_blur(np.asarray(ground) + clearance * L, radius)
        self.lookahead = lookahead * L
        # gimbal-steady view: a constant gentle downward tilt, NOT the slope of
        # the path — otherwise every climb stares at the sky and every descent
        # at the ground
        self.drop = self.lookahead * math.tan(math.radians(pitch_deg))
        self.bank = bank

    def pose(self, s):
        L = self.route.L
        p = self.route.xy(s)
        z = float(catmull(self.alt, s / self.ds))
        s2 = s + self.lookahead
        q = self.route.xy(s2)
        cam = np.array([p[0], p[1], z])
        tgt = np.array([q[0], q[1], z - self.drop])
        # bank gently into turns, like a glider: roll ~ heading change ahead
        a, b = self.route.xy(s + 0.5 * L) - p, self.route.xy(s + 1.5 * L) - self.route.xy(s + 0.5 * L)
        turn = math.atan2(a[0] * b[1] - a[1] * b[0], a[0] * b[0] + a[1] * b[1])
        roll = float(np.clip(-self.bank * turn, -0.35, 0.35))
        fwd = tgt - cam
        fwd /= np.linalg.norm(fwd)
        right = np.cross(fwd, [0.0, 0.0, 1.0])
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)
        top = up * math.cos(roll) + right * math.sin(roll)
        return cam, tgt, top


# ---------------------------------------------------------------------------
# light and color moods: waypoints every minute or two, blended smoothly
# ---------------------------------------------------------------------------

MOODS = [
    # name, sky gradient (horizon, mid, zenith), fog, sun color, sun elevation (deg)
    ("golden hour", ((1.00, 0.72, 0.30), (0.93, 0.55, 0.12), (0.45, 0.10, 0.40)),
     (1.00, 0.85, 0.60), (1.00, 0.88, 0.62), 14.0),
    ("magenta dusk", ((1.00, 0.45, 0.55), (0.62, 0.16, 0.52), (0.14, 0.05, 0.32)),
     (0.95, 0.55, 0.75), (1.00, 0.60, 0.70), 6.0),
    ("teal dawn", ((0.70, 0.95, 0.90), (0.25, 0.62, 0.70), (0.08, 0.18, 0.38)),
     (0.72, 0.92, 0.95), (0.85, 1.00, 0.92), 10.0),
    ("violet noon", ((0.85, 0.80, 1.00), (0.50, 0.40, 0.95), (0.18, 0.12, 0.55)),
     (0.85, 0.80, 1.00), (1.00, 0.95, 1.00), 32.0),
    ("ember", ((1.00, 0.40, 0.12), (0.60, 0.12, 0.05), (0.12, 0.02, 0.06)),
     (0.95, 0.45, 0.22), (1.00, 0.55, 0.25), 4.0),
]


def smootherstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)


class MoodTrack:
    def __init__(self, seed, duration, first=None):
        rng = np.random.default_rng([seed, 99])
        self.ts, self.ids = [0.0], [first if first is not None else int(rng.integers(len(MOODS)))]
        t = 0.0
        while t < duration + 600:
            t += float(rng.uniform(70.0, 130.0))
            nxt = int(rng.integers(len(MOODS) - 1))
            if nxt >= self.ids[-1]:
                nxt += 1
            self.ts.append(t)
            self.ids.append(nxt)
        self.sun_az0 = float(rng.uniform(0, 360))

    def at(self, t):
        i = int(np.clip(np.searchsorted(self.ts, t) - 1, 0, len(self.ts) - 2))
        f = smootherstep((t - self.ts[i]) / (self.ts[i + 1] - self.ts[i]))
        a, b = MOODS[self.ids[i]], MOODS[self.ids[i + 1]]
        lerp = lambda x, y: tuple(xa + (ya - xa) * f for xa, ya in zip(x, y))
        sky = tuple(lerp(a[1][k], b[1][k]) for k in range(3))
        return {"sky": sky, "fog": lerp(a[2], b[2]), "sun": lerp(a[3], b[3]),
                "sun_beta": a[4] + (b[4] - a[4]) * f,
                # the sun drifts slowly around the sky: shadows swing over time
                "sun_alpha": self.sun_az0 + t * (360.0 / 5400.0)}


def mood_columns(m):
    cols = {}
    for name, c in (("main_background_color_1", m["sky"][0]),
                    ("main_background_color_2", m["sky"][1]),
                    ("main_background_color_3", m["sky"][2]),
                    ("main_basic_fog_color", m["fog"]),
                    ("main_main_light_colour", m["sun"])):
        for ch, v in zip("RGB", c):
            cols[f"{name}_{ch}"] = max(0, min(65535, int(round(v * 65535))))
    # unwrapped on purpose: wrapping 180 -> -180 would be harmless here (one
    # keyframe per frame, nothing interpolated), but there is no reason to risk it
    cols["main_main_light_alpha"] = m["sun_alpha"]
    cols["main_main_light_beta"] = m["sun_beta"]
    return cols
