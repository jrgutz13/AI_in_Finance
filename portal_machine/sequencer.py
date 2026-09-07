"""Builds the random timeline: a sequence of short clips, each a scene with
random parameters, overlapping by the crossfade duration."""

import random
from dataclasses import dataclass

from .palettes import random_palette
from .scenes import SCENES


@dataclass
class Clip:
    scene: str
    start: float        # absolute seconds in the final video
    end: float
    params: dict        # speed, p1..p4
    palette: tuple      # (A, B, C, D)
    phase: float        # random local-time offset so clips never start identically


def build_timeline(duration, seed, clip_min=7.0, clip_max=10.0,
                   crossfade=1.0, scene_names=None):
    rng = random.Random(seed)
    names = list(scene_names or SCENES.keys())
    for n in names:
        if n not in SCENES:
            raise ValueError(f"unknown scene '{n}' (available: {', '.join(SCENES)})")

    clips = []
    t = 0.0
    prev = None
    while t < duration:
        # never repeat the previous scene back-to-back (unless only one allowed)
        pool = [n for n in names if n != prev] or names
        name = rng.choice(pool)
        length = rng.uniform(clip_min, clip_max)
        end = min(t + length, duration)
        clips.append(Clip(
            scene=name,
            start=t,
            end=end,
            params=SCENES[name].random_params(rng),
            palette=random_palette(rng),
            phase=rng.uniform(0.0, SCENES[name].phase_max),
        ))
        prev = name
        # next clip starts before this one ends, by the crossfade amount
        t = end - min(crossfade, length * 0.4)
        if end >= duration:
            break
    return clips


def active_clips(clips, t):
    """Returns (clipA, clipB, fade) for time t. fade in [0,1] blends A->B."""
    current = [c for c in clips if c.start <= t < c.end]
    if not current:
        c = clips[-1]
        return c, None, 0.0
    if len(current) == 1:
        return current[0], None, 0.0
    a, b = current[0], current[1]
    overlap = a.end - b.start
    fade = (t - b.start) / overlap if overlap > 0 else 1.0
    # smoothstep for a gentler blend
    fade = fade * fade * (3.0 - 2.0 * fade)
    return a, b, fade
