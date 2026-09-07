"""Continuous (single-style) timeline.

Instead of cutting the video into separate clips, this produces ONE endless
instance of a scene. The forward motion runs unbroken (local time only ever
increases), while the scene's shape and colors drift smoothly between random
"waypoints" spaced tens of seconds apart. The result evolves forever without
ever restarting into a different-looking instance.

Parameters that would make the motion lurch if changed mid-flight (anything
that scales time), or that must be whole numbers, are chosen once and held
constant (see SceneDef.locked). Everything else drifts."""

from dataclasses import dataclass

from .palettes import random_palette
from .scenes import SCENES


def _smootherstep(x):
    # Ken Perlin's smootherstep: zero 1st and 2nd derivatives at the ends,
    # so waypoint-to-waypoint transitions have no visible kink.
    x = max(0.0, min(1.0, x))
    return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)


def _lerp(a, b, t):
    return a + (b - a) * t


def _lerp_palette(pa, pb, t):
    return tuple(
        tuple(_lerp(ca, cb, t) for ca, cb in zip(va, vb))
        for va, vb in zip(pa, pb)
    )


@dataclass
class Waypoint:
    time: float
    free: dict        # free param name -> value at this waypoint
    palette: tuple    # (A, B, C, D)


class ContinuousTrack:
    """A single evolving scene spanning the whole video."""

    def __init__(self, scene_name, duration, rng,
                 wp_min=30.0, wp_max=50.0):
        self.scene = scene_name
        scene = SCENES[scene_name]

        # locked params: drawn once, constant for the entire video
        base = scene.random_params(rng)
        self.locked = {k: base[k] for k in scene.locked_params()}
        self._free_keys = scene.free_params()

        # the monotonically increasing local time fed to the shader
        self.phase0 = rng.uniform(0.0, scene.phase_max)

        # build waypoints out past the end so the final segment interpolates
        self.waypoints = [Waypoint(0.0,
                                   {k: base[k] for k in self._free_keys},
                                   random_palette(rng))]
        t = 0.0
        while t < duration:
            t += rng.uniform(wp_min, wp_max)
            draw = scene.random_params(rng)
            self.waypoints.append(Waypoint(
                t, {k: draw[k] for k in self._free_keys}, random_palette(rng)))

    def eval(self, t):
        """Returns (params, palette) at absolute time t."""
        wps = self.waypoints
        # locate the segment containing t (linear scan is fine: a 3h video has
        # only a few hundred waypoints and t advances monotonically)
        i = 0
        while i + 1 < len(wps) and wps[i + 1].time <= t:
            i += 1
        a = wps[i]
        b = wps[min(i + 1, len(wps) - 1)]
        span = b.time - a.time
        f = _smootherstep((t - a.time) / span) if span > 0 else 0.0

        params = dict(self.locked)
        for k in self._free_keys:
            params[k] = _lerp(a.free[k], b.free[k], f)
        palette = _lerp_palette(a.palette, b.palette, f)
        return params, palette
