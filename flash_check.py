#!/usr/bin/env python3
"""Check a video for photosensitive-seizure risk (rapid flashing).

Follows the general-flash rule used by broadcasters (Ofcom / ITU-R BT.1702)
and WCAG 2.3.1: a "flash" is a pair of opposing changes in brightness of at
least 10% of full white (where the darker state is below 80% white); content
fails when more than 3 flashes happen within any one second over a large part
of the screen (25% or more). Flashing over smaller areas is reported as a
warning.

    python3 flash_check.py "output\\portal_12345.mp4"

Prints PASS/FAIL, the worst moments, and how much of the screen flashed."""

import argparse
import subprocess
import sys

import numpy as np

W, H = 96, 54                   # analysis grid: each cell is ~1/5000 of the screen


def frames(path, fps):
    proc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", path, "-vf",
                             f"fps={fps},scale={W}:{H}:flags=area", "-f", "rawvideo",
                             "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    size = W * H * 3
    while True:
        buf = proc.stdout.read(size)
        if len(buf) < size:
            break
        rgb = np.frombuffer(buf, np.uint8).reshape(H, W, 3).astype(np.float32) / 255.0
        lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
        yield lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)   # relative luminance
    proc.wait()


def analyze(path, fps=24.0, step=0.10, area_fail=0.25, area_warn=0.05):
    """Returns per-frame flashing-area fractions (0..1)."""
    win = int(round(fps))                          # one-second window, in frames
    ext = None                                     # each cell's last extreme value
    direction = None                               # +1 rising, -1 falling, 0 unknown
    history = []                                   # per frame: which cells transitioned
    areas = []
    for y in frames(path, fps):
        if ext is None:
            ext = y.copy()
            direction = np.zeros_like(y)
            history.append(np.zeros(y.shape, bool))
            areas.append(0.0)
            continue
        up = (y - ext >= step) & (np.minimum(y, ext) < 0.8)
        down = (ext - y >= step) & (np.minimum(y, ext) < 0.8)
        # a transition = a 10% swing that reverses the previous direction
        trans = (up & (direction <= 0)) | (down & (direction >= 0))
        direction = np.where(up, 1.0, np.where(down, -1.0, direction))
        # follow the extreme in the current direction
        ext = np.where(trans, y, np.where(direction > 0, np.maximum(ext, y),
                                          np.where(direction < 0, np.minimum(ext, y), ext)))
        history.append(trans)
        if len(history) > win:
            history.pop(0)
        count = np.sum(history, axis=0)
        # more than 3 flashes = 7+ opposing transitions within one second
        areas.append(float((count >= 7).mean()))
    return np.array(areas), fps


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a video for rapid flashing.")
    ap.add_argument("video")
    ap.add_argument("--fps", type=float, default=24.0, help="analysis rate (default 24)")
    args = ap.parse_args(argv)
    areas, fps = analyze(args.video, args.fps)
    if len(areas) == 0:
        print("Could not read the video.")
        return 2
    worst = int(areas.argmax())
    fail = areas >= 0.25
    warn = areas >= 0.05

    def spans(mask):
        out, start = [], None
        for i, m in enumerate(list(mask) + [False]):
            if m and start is None:
                start = i
            elif not m and start is not None:
                out.append((start / fps, i / fps))
                start = None
        return out

    def ts(s):
        return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"

    print(f"video     {args.video}  ({len(areas) / fps:.0f} s analyzed)")
    print(f"worst     {100 * areas.max():.1f}% of the screen flashing at {ts(worst / fps)}")
    for label, mask in (("FAIL", fail), ("warning", warn & ~fail)):
        sp = spans(mask)
        if sp:
            print(f"{label:9s} {len(sp)} stretch(es), {mask.sum() / fps:.1f} s in total:")
            for a, b in sp[:10]:
                print(f"          {ts(a)} - {ts(b)}")
    print("RESULT    " + ("FAIL - rapid flashing over a large area" if fail.any() else
                          "PASS (some small flashing areas)" if warn.any() else "PASS"))
    return 1 if fail.any() else 0


if __name__ == "__main__":
    sys.exit(main())
