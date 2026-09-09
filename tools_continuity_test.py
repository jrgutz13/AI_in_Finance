#!/usr/bin/env python3
"""Detects motion discontinuities in scenes.

Renders frames directly (no video encoding, so no compression noise) and
measures how much the picture changes between consecutive frames. Smooth
motion gives a steady change. A wrap/reset shows up as one frame where the
change spikes far above the typical level.

Reports  spike = (largest frame-to-frame change) / (median change).
Seamless scenes sit near 1-3. A visible jump reads as 5, 10, 50+.
"""
import random
import sys

import numpy as np

sys.path.insert(0, "/home/user/AI_in_Finance")
from portal_machine.continuous import ContinuousTrack
from portal_machine.renderer import Renderer
from portal_machine.scenes import SCENES

W, H = 256, 144
FPS = 15
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 40.0
SEED = 1234


def test(name):
    rng = random.Random(SEED)
    track = ContinuousTrack(name, SECONDS + 60, rng)
    r = Renderer(W, H, scene_names=[name])
    n = int(SECONDS * FPS)
    prev = None
    deltas = []
    for i in range(n):
        t = i / FPS
        buf = r.render_continuous(track, t)
        f = np.frombuffer(buf, dtype=np.uint8).reshape(H, W, 3).astype(np.int16)
        if prev is not None:
            deltas.append(np.abs(f - prev).mean())
        prev = f
    d = np.array(deltas)
    med = np.median(d)
    spike = d.max() / max(med, 1e-6)
    where = (d.argmax() + 1) / FPS
    return spike, med, d.max(), where


if __name__ == "__main__":
    names = sys.argv[1].split(",") if sys.argv[1] != "all" else list(SCENES)
    print(f"{'scene':18s} {'spike':>7s} {'median':>7s} {'max':>7s}  worst@   verdict")
    bad = []
    for nm in names:
        spike, med, mx, where = test(nm)
        verdict = "OK" if spike < 4.0 else "JUMPS"
        if spike >= 4.0:
            bad.append(nm)
        print(f"{nm:18s} {spike:7.1f} {med:7.2f} {mx:7.2f}  {where:5.1f}s   {verdict}")
    print()
    print("scenes with jumps:", ",".join(bad) if bad else "none")
