#!/usr/bin/env python3
"""Clip Stitcher: turns a folder of short video clips and/or still images
into one long, continuous video with smooth crossfades.

    python stitcher/stitch.py "C:\\my clips" --duration 3h --audio music.mp3
    python stitcher/stitch.py --resume          # after a crash/power cut

- Video clips (mp4/mov/webm/mkv...) are scaled to fill the frame, stripped of
  sound, and optionally slowed down with motion interpolation (--slow 2).
- Still images (png/jpg/webp...) become slow cinematic shots: a gentle
  push-in or pull-back with a drift across the picture, different each time.
- The sources are shuffled and looped (with no clip following itself) until
  the video reaches the target length.

How it stays fast and crash-safe with a thousand clips: the video is built
from small pieces — the untouched middle of each clip, and each crossfade
between two neighbours — rendered one at a time into short segments that are
joined at the end without re-encoding. A manifest records finished pieces,
so --resume continues where a crash stopped, and memory use never grows
with the length of the video.
"""

import argparse
import glob
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time

VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MANIFEST = "manifest.json"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def parse_duration(text):
    text = str(text).strip().lower()
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return float(text)
    if ":" in text:
        parts = [float(p) for p in text.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    found = re.findall(r"(\d+(?:\.\d+)?)\s*([hms])", text)
    if not found:
        raise argparse.ArgumentTypeError(f"can't parse duration '{text}'")
    return sum(float(v) * {"h": 3600, "m": 60, "s": 1}[u] for v, u in found)


def fmt_ts(sec):
    s = int(sec)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    try:
        return float(out.strip())
    except ValueError:
        return None


def auto_maxrate_mbps(w, h, fps):
    return max(6, round(w * h * fps * 0.16 / 1e6))


# ---------------------------------------------------------------------------
# planning
# ---------------------------------------------------------------------------

def scan_sources(folder, still_seconds, slow, fade):
    """Returns [{path, kind, length}] where length is the time the source
    occupies in the output (after slow-motion)."""
    items, skipped = [], []
    for path in sorted(glob.glob(os.path.join(folder, "*"))):
        ext = os.path.splitext(path)[1].lower()
        if ext in IMAGE_EXT:
            items.append({"path": os.path.abspath(path), "kind": "image",
                          "length": float(still_seconds)})
        elif ext in VIDEO_EXT:
            d = probe_duration(path)
            if d is None:
                skipped.append((path, "could not be read"))
                continue
            length = d * slow
            if length < 2 * fade + 0.5:
                skipped.append((path, f"only {length:.1f}s long, too short for "
                                      f"{fade:.1f}s crossfades on both ends"))
                continue
            items.append({"path": os.path.abspath(path), "kind": "video",
                          "length": round(length, 3)})
    return items, skipped


def build_playlist(items, target, fade, order, seed):
    """Loop the sources (reshuffled each pass, never the same one twice in a
    row) until the crossfaded total reaches the target length."""
    rng = random.Random(seed)
    playlist, total = [], 0.0
    while total < target:
        batch = list(range(len(items)))
        if order == "shuffle":
            rng.shuffle(batch)
            if playlist and len(batch) > 1 and batch[0] == playlist[-1]["src"]:
                batch.append(batch.pop(0))
        for idx in batch:
            playlist.append({"src": idx,
                             # per-shot randomness for still-image camera moves
                             "motion": rng.random(), "drift": [rng.random() for _ in range(4)]})
            total += items[idx]["length"] - (fade if len(playlist) > 1 else 0.0)
            if total >= target:
                break
    return playlist


def plan_pieces(items, playlist, fade, target=None):
    """Pieces in order: body of shot 0, fade 0->1, body of shot 1, ...
    Each piece is (kind, shot, start, end) in the shot's own output time.
    With a target, the last body is cut so the video ends exactly on time
    (trimming the joined file instead would cut at a packet boundary)."""
    pieces = []
    n = len(playlist)
    elapsed = 0.0
    for i, shot in enumerate(playlist):
        L = items[shot["src"]]["length"]
        a = fade if i > 0 else 0.0
        b = L - fade if i < n - 1 else L
        if i == n - 1 and target is not None:
            b = min(b, max(a + 1.0 / 30, a + (target - elapsed)))
        pieces.append({"type": "body", "shot": i, "start": a, "end": b})
        elapsed += b - a
        if i < n - 1:
            pieces.append({"type": "fade", "shot": i})
            elapsed += fade
    return pieces


# ---------------------------------------------------------------------------
# rendering one piece
# ---------------------------------------------------------------------------

def source_input(item, shot, start, end, s):
    """ffmpeg input args + filter chain producing frames [start, end) of a
    shot, normalized to the output size, rate and format."""
    W, H, fps = s["width"], s["height"], s["fps"]
    dur = end - start
    fit = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
           f"crop={W}:{H},setsar=1,format=yuv420p,setpts=PTS-STARTPTS")
    norm = f"fps={fps}," + fit
    if item["kind"] == "video":
        slow = s["slow"]
        args = ["-ss", f"{start / slow:.4f}", "-t", f"{dur / slow + 0.2:.4f}",
                "-i", item["path"]]
        chain = ""
        if slow > 1.0:
            # stretch time, then invent the in-between frames by motion
            # estimation so the slowed clip stays smooth instead of stuttering
            chain = (f"setpts={slow}*PTS,minterpolate=fps={fps}:mi_mode=mci:"
                     f"mc_mode=aobmc:me_mode=bidir:vsbmc=1,")
        chain += f"{norm},trim=duration={dur:.4f},setpts=PTS-STARTPTS"
        return args, chain

    # still image: a slow push-in (or pull-back) drifting between two points.
    # Rendered from a 3x upscale so sub-pixel motion doesn't stair-step.
    total = int(round(item["length"] * fps))
    off = int(round(start * fps))
    frames = int(round(dur * fps))
    k = 3 if W <= 2560 else 2
    zin = shot["motion"] < 0.6
    z0, z1 = (1.0, 1.22) if zin else (1.22, 1.0)
    px0, py0, px1, py1 = (0.3 + 0.4 * d for d in shot["drift"])
    t = f"((on+{off})/{max(total - 1, 1)})"
    chain = (f"scale={W * k}:{H * k}:force_original_aspect_ratio=increase,"
             f"crop={W * k}:{H * k},"
             f"zoompan=z='{z0}+({z1 - z0:.4f})*{t}':"
             f"x='(iw-iw/zoom)*({px0:.4f}+({px1 - px0:.4f})*{t})':"
             f"y='(ih-ih/zoom)*({py0:.4f}+({py1 - py0:.4f})*{t})':"
             # no fps= after zoompan: it already emits exactly `frames` frames
             # at the output rate, and an fps filter here drops the last one
             f"d={frames}:s={W}x{H}:fps={fps},{fit}")
    return ["-i", item["path"]], chain


def render_piece(piece, items, playlist, s, out_ts):
    fade = s["fade"]
    enc = ["-c:v", "libx264", "-crf", str(s["crf"]), "-preset", "medium",
           "-maxrate", f"{s['maxrate']}M", "-bufsize", f"{2 * s['maxrate']}M",
           "-an", "-f", "mpegts"]
    if piece["type"] == "body":
        shot = playlist[piece["shot"]]
        a, b = piece["start"], piece["end"]
        args, chain = source_input(items[shot["src"]], shot, a, b, s)
        cmd = (["ffmpeg", "-y", "-loglevel", "error"] + args
               + ["-filter_complex", f"[0:v]{chain}[out]", "-map", "[out]",
                  "-frames:v", str(int(round((b - a) * s["fps"])))] + enc)
    else:
        i = piece["shot"]
        sa, sb = playlist[i], playlist[i + 1]
        La = items[sa["src"]]["length"]
        args_a, chain_a = source_input(items[sa["src"]], sa, La - fade, La, s)
        args_b, chain_b = source_input(items[sb["src"]], sb, 0.0, fade, s)
        graph = (f"[0:v]{chain_a}[a];[1:v]{chain_b}[b];"
                 f"[a][b]xfade=transition=fade:duration={fade}:offset=0[out]")
        cmd = (["ffmpeg", "-y", "-loglevel", "error"] + args_a + args_b
               + ["-filter_complex", graph, "-map", "[out]",
                  "-frames:v", str(int(round(fade * s["fps"])))] + enc)
    subprocess.run(cmd + [out_ts + ".part"], check=True)
    os.replace(out_ts + ".part", out_ts)


# ---------------------------------------------------------------------------
# manifest / resume
# ---------------------------------------------------------------------------

def write_manifest(pdir, state, done):
    tmp = os.path.join(pdir, MANIFEST + ".tmp")
    with open(tmp, "w") as f:
        json.dump(dict(state, done=sorted(done)), f)
    os.replace(tmp, os.path.join(pdir, MANIFEST))


def load_manifest(pdir):
    with open(os.path.join(pdir, MANIFEST)) as f:
        state = json.load(f)
    return state, set(state.pop("done"))


def find_unfinished(outdir="output"):
    c = glob.glob(os.path.join(outdir, "stitch_*_parts", MANIFEST))
    return os.path.dirname(max(c, key=os.path.getmtime)) if c else None


def run(state, done):
    s, items, playlist = state["settings"], state["items"], state["playlist"]
    pieces = plan_pieces(items, playlist, s["fade"], s["duration"])
    pdir = s["parts_dir"]
    os.makedirs(pdir, exist_ok=True)
    write_manifest(pdir, state, done)
    started, rendered = time.time(), 0
    todo = len(pieces) - len(done)
    for k, piece in enumerate(pieces):
        if k in done:
            continue
        render_piece(piece, items, playlist, s, os.path.join(pdir, f"p_{k:06d}.ts"))
        done.add(k)
        write_manifest(pdir, state, done)
        rendered += 1
        rate = rendered / max(time.time() - started, 1e-6)
        sys.stdout.write(f"\r  piece {len(done)}/{len(pieces)}  ETA "
                         f"{fmt_ts((todo - rendered) / max(rate, 1e-6))}   ")
        sys.stdout.flush()
    print()

    listfile = os.path.join(pdir, "list.txt")
    with open(listfile, "w") as f:
        for k in range(len(pieces)):
            f.write(f"file 'p_{k:06d}.ts'\n")
    out = s["out"]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listfile]
    if s.get("audio") and os.path.isfile(s["audio"]):
        cmd += ["-stream_loop", "-1", "-i", s["audio"], "-map", "0:v", "-map", "1:a",
                "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-map", "0:v"]
    cmd += ["-c:v", "copy"]
    size = sum(os.path.getsize(os.path.join(pdir, f"p_{k:06d}.ts")) for k in range(len(pieces)))
    if shutil.disk_usage(os.path.dirname(os.path.abspath(out))).free > size * 2.4:
        cmd += ["-movflags", "+faststart"]
    subprocess.run(cmd + ["-t", f"{s['duration']:.3f}", out], check=True)

    # a simple "what's where" list: when each shot starts in the final video
    t, lines = 0.0, []
    for i, shot in enumerate(playlist):
        if t >= s["duration"]:
            break
        lines.append(f"{fmt_ts(t)} {os.path.basename(items[shot['src']]['path'])}")
        t += items[shot["src"]]["length"] - s["fade"]
    with open(out.rsplit(".", 1)[0] + "_shots.txt", "w") as f:
        f.write("\n".join(lines) + "\n")
    shutil.rmtree(pdir, ignore_errors=True)


# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Stitch clips and images into one long video.")
    ap.add_argument("source", nargs="?", help="folder of video clips and/or images")
    ap.add_argument("--duration", type=parse_duration, default=parse_duration("10m"))
    ap.add_argument("--resolution", default="1920x1080")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--crossfade", type=float, default=2.0,
                    help="seconds of crossfade between shots (default 2)")
    ap.add_argument("--still-seconds", type=float, default=12.0,
                    help="how long each still image is shown (default 12)")
    ap.add_argument("--slow", type=float, default=1.0,
                    help="slow video clips down, e.g. 2 = half speed with smooth "
                         "motion interpolation (makes each clip go further; "
                         "rendering is much slower)")
    ap.add_argument("--order", choices=["shuffle", "name"], default="shuffle")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--audio", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--resume-info", action="store_true")
    args = ap.parse_args(argv)

    if args.resume or args.resume_info:
        pdir = find_unfinished()
        if pdir is None:
            print("No interrupted stitch found.")
            return 1
        state, done = load_manifest(pdir)
        n = len(plan_pieces(state["items"], state["playlist"], state["settings"]["fade"],
                             state["settings"]["duration"]))
        print(f"Interrupted stitch found: {state['settings']['out']}")
        print(f"  {fmt_ts(state['settings']['duration'])} from {len(state['items'])} sources,"
              f" {len(done)}/{n} pieces finished")
        if args.resume_info:
            return 0
        run(state, done)
        print(f"done       {state['settings']['out']}")
        return 0

    if not args.source or not os.path.isdir(args.source):
        ap.error("give the folder that holds your clips / images")
    m = re.fullmatch(r"(\d+)x(\d+)", args.resolution.lower())
    if not m:
        ap.error("resolution must look like 1920x1080")
    w, h = int(m.group(1)) // 2 * 2, int(m.group(2)) // 2 * 2
    if args.slow < 1.0:
        ap.error("--slow must be 1 or more")

    items, skipped = scan_sources(args.source, args.still_seconds, args.slow, args.crossfade)
    for path, why in skipped:
        print(f"skipping   {os.path.basename(path)}: {why}")
    if not items:
        print("No usable clips or images found in that folder.")
        return 1

    seed = args.seed if args.seed is not None else random.randrange(1, 10 ** 9)
    os.makedirs("output", exist_ok=True)
    out = args.out or os.path.join("output", f"stitch_{seed}.mp4")
    playlist = build_playlist(items, args.duration, args.crossfade, args.order, seed)
    settings = {"seed": seed, "duration": args.duration, "width": w, "height": h,
                "fps": args.fps, "fade": args.crossfade, "slow": args.slow,
                "crf": args.crf, "maxrate": auto_maxrate_mbps(w, h, args.fps),
                "audio": os.path.abspath(args.audio) if args.audio else None,
                "out": out, "parts_dir": out.rsplit(".", 1)[0] + "_parts"}
    n_vid = sum(i["kind"] == "video" for i in items)
    print(f"sources    {n_vid} clips, {len(items) - n_vid} images")
    print(f"video      {w}x{h} @ {args.fps} fps, {fmt_ts(args.duration)},"
          f" {len(playlist)} shots, {args.crossfade:g}s crossfades")
    uses = len(playlist) / len(items)
    if uses > 3:
        print(f"note       each source appears ~{uses:.0f} times; more sources = less repetition")
    print(f"output     {out}")
    run({"settings": settings, "items": items, "playlist": playlist}, set())
    print(f"done       {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
