#!/usr/bin/env python3
"""Blender Worlds driver: renders a long bioluminescent-landscape flight with
Blender, crash-safely, and encodes it into one MP4.

    python blender_worlds/make_world.py --duration 3h --audio music.mp3
    python blender_worlds/make_world.py --resume        # after a crash/power cut
    python blender_worlds/make_world.py --preview 42    # one PNG at t=42 s

How it stays crash-safe: the video is rendered in chunks (60 s by default).
Blender writes each chunk's frames as JPEGs; the moment a chunk is complete
it is encoded (with bloom glow) into a small video segment and its JPEGs are
deleted. A manifest records which chunks are done. Re-running with --resume
skips finished chunks, and inside the unfinished chunk Blender skips frames
already on disk — so a power cut costs at most the frame in progress. Every
frame is a pure function of seed + time, so a resumed video is identical to
an uninterrupted one.
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

HERE = os.path.dirname(os.path.abspath(__file__))
WORLD_GEN = os.path.join(HERE, "world_gen.py")
MANIFEST = "manifest.json"
QUALITY = {"draft": 8, "standard": 16, "high": 32}


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
    total = 0.0
    found = re.findall(r"(\d+(?:\.\d+)?)\s*([hms])", text)
    if not found:
        raise argparse.ArgumentTypeError(f"can't parse duration '{text}'")
    for value, unit in found:
        total += float(value) * {"h": 3600, "m": 60, "s": 1}[unit]
    return total


def fmt_ts(sec):
    s = int(sec)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def find_blender(explicit=None):
    """Explicit path > BLENDER env var > PATH > the usual install locations."""
    cands = [explicit, os.environ.get("BLENDER"), shutil.which("blender")]
    pats = [r"C:\Program Files\Blender Foundation\Blender *\blender.exe",
            r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\Blender Foundation\Blender *\blender.exe"),
            "/Applications/Blender.app/Contents/MacOS/Blender",
            "/usr/bin/blender", "/snap/bin/blender"]
    for pat in pats:
        # newest version first, so "Blender 4.5" beats "Blender 4.2"
        cands.extend(sorted(glob.glob(pat), reverse=True))
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def bloom_filter(height, out_fmt="yuv420p"):
    """Post-processing applied to every frame:
    - bloom: two blurred copies of the highlights screened back over the
      frame (a tight halo and a wide one) so bright things glow
    - film: faint lens color fringing, a gentle vignette and fine moving
      grain, which take the clinical computer-graphics edge off the image
    Done in ffmpeg rather than Blender because Blender's bloom settings
    differ between versions, while this is identical everywhere."""
    s1 = max(1.0, height / 180.0)
    s2 = max(2.0, height / 45.0)
    ca = max(1, round(height / 1080))
    return (f"[0:v]format=gbrp,split=3[a][b][c];"
            f"[b]curves=all='0/0 0.62/0 1/1',gblur=sigma={s1:.2f}[g1];"
            f"[c]curves=all='0/0 0.55/0 1/1',gblur=sigma={s2:.2f}[g2];"
            f"[a][g1]blend=all_mode=screen:all_opacity=0.85[t];"
            f"[t][g2]blend=all_mode=screen:all_opacity=0.45,"
            f"rgbashift=rh=-{ca}:bh={ca},vignette=angle=PI/5,"
            f"format={out_fmt},noise=c0s=3:c0f=t[out]")


def auto_maxrate_mbps(w, h, fps):
    return max(6, round(w * h * fps * 0.16 / 1e6))


# ---------------------------------------------------------------------------
# chunk rendering
# ---------------------------------------------------------------------------

def run_blender(settings, first, last, frames_dir, progress):
    cmd = [settings["blender"], "-b", "--factory-startup", "-P", WORLD_GEN, "--",
           "--seed", str(settings["seed"]), "--start", str(first), "--end", str(last),
           "--outdir", frames_dir, "--width", str(settings["width"]),
           "--height", str(settings["height"]), "--fps", str(settings["fps"]),
           "--samples", str(settings["samples"]), "--speed", str(settings["speed"]),
           "--engine", settings.get("engine", "eevee")]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace")
    tail = []
    for line in proc.stdout:
        if line.startswith("FRAME "):
            progress(int(line.split()[1]))
        else:
            tail = (tail + [line.rstrip()])[-25:]      # keep context for errors
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError("Blender stopped with an error. Last output:\n  "
                           + "\n  ".join(tail))


def encode_chunk(settings, first, count, frames_dir, out_ts):
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-framerate", str(settings["fps"]), "-start_number", str(first),
           "-i", os.path.join(frames_dir, "f_%07d.jpg"), "-frames:v", str(count),
           "-filter_complex", bloom_filter(settings["height"]), "-map", "[out]",
           "-c:v", "libx264", "-crf", str(settings["crf"]), "-preset", "medium",
           "-maxrate", f"{settings['maxrate']}M", "-bufsize", f"{2 * settings['maxrate']}M",
           "-f", "mpegts", out_ts + ".part"]
    subprocess.run(cmd, check=True)
    os.replace(out_ts + ".part", out_ts)


def benchmark(settings, frames=8):
    """Render a few real frames and project how long full videos would take.
    The first two frames are excluded: Blender compiles shaders and builds
    the first stretch of world on them, which a long render only pays once."""
    tmp = os.path.join("output", "_speedtest")
    shutil.rmtree(tmp, ignore_errors=True)
    times = []
    start = int(120 * settings["fps"])                  # somewhere mid-journey
    proc = subprocess.Popen(
        [settings["blender"], "-b", "--factory-startup", "-P", WORLD_GEN, "--",
         "--seed", str(settings["seed"]), "--start", str(start),
         "--end", str(start + frames + 2), "--outdir", tmp,
         "--width", str(settings["width"]), "--height", str(settings["height"]),
         "--fps", str(settings["fps"]), "--samples", str(settings["samples"]),
         "--engine", settings.get("engine", "eevee")],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    for line in proc.stdout:
        if line.startswith("FRAME "):
            times.append(float(line.split()[2]))
            sys.stdout.write(f"\r  test frame {len(times)}/{frames + 2}: {times[-1]:.2f} s   ")
            sys.stdout.flush()
    proc.wait()
    shutil.rmtree(tmp, ignore_errors=True)
    print()
    if len(times) < 3:
        print("Speed test failed - Blender did not render frames.")
        return 1
    per = sum(times[2:]) / len(times[2:])
    print(f"\n  {settings['width']}x{settings['height']}, {settings['fps']} fps: "
          f"{per:.2f} seconds per frame")
    for label, sec in (("10 minutes", 600), ("1 hour", 3600), ("3 hours", 10800)):
        print(f"  a {label:10s} video would take about {fmt_ts(per * sec * settings['fps'])}")
    return 0


def write_manifest(pdir, settings, done):
    tmp = os.path.join(pdir, MANIFEST + ".tmp")
    with open(tmp, "w") as f:
        json.dump({"settings": settings, "done": sorted(done)}, f, indent=1)
    os.replace(tmp, os.path.join(pdir, MANIFEST))


def load_manifest(pdir):
    with open(os.path.join(pdir, MANIFEST)) as f:
        d = json.load(f)
    return d["settings"], set(d["done"])


def find_unfinished(outdir="output"):
    c = glob.glob(os.path.join(outdir, "world_*_parts", MANIFEST))
    return os.path.dirname(max(c, key=os.path.getmtime)) if c else None


def render(settings):
    fps = settings["fps"]
    total = int(round(settings["duration"] * fps))
    per = int(round(settings["chunk"] * fps))
    chunks = [(a, min(a + per, total)) for a in range(0, total, per)]
    pdir = settings["parts_dir"]
    os.makedirs(pdir, exist_ok=True)
    try:
        _, done = load_manifest(pdir)
    except FileNotFoundError:
        done = set()
    write_manifest(pdir, settings, done)

    started = time.time()
    frames_done_at_start = sum(b - a for i, (a, b) in enumerate(chunks) if i in done)
    rendered = [0]

    for i, (a, b) in enumerate(chunks):
        if i in done:
            continue
        fdir = os.path.join(pdir, f"frames_{i:05d}")

        def progress(frame, i=i, a=a):
            rendered[0] += 1
            el = time.time() - started
            rate = rendered[0] / max(el, 1e-6)
            left = (total - frames_done_at_start - rendered[0]) / max(rate, 1e-6)
            sys.stdout.write(f"\r  chunk {i + 1}/{len(chunks)}  frame {frame + 1}/{total}"
                             f"  {rate:5.2f} fps  ETA {fmt_ts(left)}   ")
            sys.stdout.flush()

        run_blender(settings, a, b, fdir, progress)
        missing = [f for f in range(a, b)
                   if not os.path.exists(os.path.join(fdir, f"f_{f:07d}.jpg"))]
        if missing:
            raise RuntimeError(f"chunk {i + 1}: {len(missing)} frames missing after render")
        encode_chunk(settings, a, b - a, fdir, os.path.join(pdir, f"chunk_{i:05d}.ts"))
        shutil.rmtree(fdir, ignore_errors=True)          # frames no longer needed
        done.add(i)
        write_manifest(pdir, settings, done)
    print()
    return chunks


def join(settings, chunks):
    pdir = settings["parts_dir"]
    out = settings["out"]
    listfile = os.path.join(pdir, "list.txt")
    with open(listfile, "w") as f:
        for i in range(len(chunks)):
            f.write(f"file 'chunk_{i:05d}.ts'\n")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
           "-i", listfile]
    audio = settings.get("audio")
    if audio and os.path.isfile(audio):
        cmd += ["-stream_loop", "-1", "-i", audio, "-map", "0:v", "-map", "1:a",
                "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-map", "0:v"]
    cmd += ["-c:v", "copy"]
    size = sum(os.path.getsize(os.path.join(pdir, f"chunk_{i:05d}.ts"))
               for i in range(len(chunks)))
    if shutil.disk_usage(os.path.dirname(os.path.abspath(out))).free > size * 2.4:
        cmd += ["-movflags", "+faststart"]
    cmd += ["-t", f"{settings['duration']:.3f}", out]
    subprocess.run(cmd, check=True)
    shutil.rmtree(pdir, ignore_errors=True)


# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Render a Blender Worlds flight.")
    ap.add_argument("--duration", type=parse_duration, default=parse_duration("1m"))
    ap.add_argument("--resolution", default="1920x1080")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--quality", choices=list(QUALITY), default="standard",
                    help="draft = fastest, high = cleanest (default standard)")
    ap.add_argument("--engine", choices=["eevee", "cycles"], default="eevee",
                    help="eevee = fast; cycles = photoreal path tracing, much slower")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--audio", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--speed-scale", type=float, default=1.0,
                    help="how fast the camera travels; 0.5 = half speed")
    ap.add_argument("--chunk", type=float, default=60.0,
                    help="seconds per crash-safe chunk (default 60)")
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--blender", default=None, help="path to blender(.exe)")
    ap.add_argument("--preview", type=float, default=None, metavar="T",
                    help="render one PNG still at T seconds instead of a video")
    ap.add_argument("--speed-test", action="store_true",
                    help="render a few frames and estimate full render times")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--resume-info", action="store_true")
    ap.add_argument("--ignore-space", action="store_true")
    args = ap.parse_args(argv)

    if args.resume or args.resume_info:
        pdir = find_unfinished()
        if pdir is None:
            print("No interrupted world render found.")
            return 1
        settings, done = load_manifest(pdir)
        n = -(-int(round(settings["duration"] * settings["fps"]))
              // int(round(settings["chunk"] * settings["fps"])))
        print(f"Interrupted world render found: {settings['out']}")
        print(f"  {settings['width']}x{settings['height']}, {fmt_ts(settings['duration'])},"
              f" seed {settings['seed']}, {len(done)}/{n} chunks finished")
        if args.resume_info:
            return 0
        blender = find_blender(args.blender) or settings.get("blender")
        if not blender or not os.path.isfile(blender):
            print("Blender not found. Install Blender 4.5 LTS from blender.org.")
            return 1
        settings["blender"] = blender
        join(settings, render(settings))
        print(f"done       {settings['out']}")
        return 0

    blender = find_blender(args.blender)
    if not blender:
        print("Blender was not found on this computer.")
        print("Install Blender 4.5 LTS (free) from https://www.blender.org/download/lts/")
        print("or pass its location with --blender \"C:\\path\\to\\blender.exe\"")
        return 1

    m = re.fullmatch(r"(\d+)x(\d+)", args.resolution.lower())
    if not m:
        ap.error("resolution must look like 1920x1080")
    w, h = int(m.group(1)) // 2 * 2, int(m.group(2)) // 2 * 2
    seed = args.seed if args.seed is not None else random.randrange(1, 10 ** 9)
    os.makedirs("output", exist_ok=True)
    out = args.out or os.path.join("output", f"world_{seed}.mp4")

    if args.preview is not None:
        png = out.rsplit(".", 1)[0] + f"_t{args.preview:.0f}.png"
        subprocess.run([blender, "-b", "--factory-startup", "-P", WORLD_GEN, "--",
                        "--seed", str(seed), "--still", str(args.preview), "--out", png,
                        "--width", str(w), "--height", str(h),
                        "--samples", str(QUALITY[args.quality]),
                        "--speed", str(args.speed_scale), "--engine", args.engine],
                       check=True, stdout=subprocess.DEVNULL)
        glow = png.rsplit(".", 1)[0] + "_glow.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", png,
                        "-filter_complex", bloom_filter(h, "rgb24"),
                        "-map", "[out]", glow], check=True)
        os.replace(glow, png)
        print(f"wrote      {png}")
        return 0

    settings = {
        "seed": seed, "duration": args.duration, "width": w, "height": h,
        "fps": args.fps, "samples": QUALITY[args.quality], "speed": args.speed_scale,
        "engine": args.engine,
        "chunk": args.chunk, "crf": args.crf, "maxrate": auto_maxrate_mbps(w, h, args.fps),
        "audio": os.path.abspath(args.audio) if args.audio else None,
        "out": out, "parts_dir": out.rsplit(".", 1)[0] + "_parts", "blender": blender,
    }
    if args.speed_test:
        print(f"Speed test: {w}x{h}, quality {args.quality}, engine {args.engine}")
        return benchmark(settings)

    worst = settings["maxrate"] * 1e6 / 8 * args.duration / 1e9
    frames_tmp = args.chunk * args.fps * w * h * 0.25 / 1e9     # one chunk of JPEGs
    free = shutil.disk_usage(os.path.abspath("output")).free / 1e9
    print(f"seed       {seed}")
    print(f"video      {w}x{h} @ {args.fps} fps, {fmt_ts(args.duration)}, "
          f"quality {args.quality}, engine {args.engine}")
    print(f"blender    {blender}")
    print(f"output     {out}")
    print(f"size       up to ~{worst:.1f} GB (+{frames_tmp:.1f} GB working space)")
    print(f"disk free  {free:.1f} GB")
    if not args.ignore_space and worst + frames_tmp > free * 0.95:
        print("\nWARNING: this may not fit on the drive. Free space, shorten the")
        print("video, or lower the resolution. (--ignore-space to override)")
        return 1

    chunks = render(settings)
    print("joining chunks...")
    join(settings, chunks)
    print(f"done       {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
