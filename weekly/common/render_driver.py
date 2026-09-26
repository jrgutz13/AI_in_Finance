#!/usr/bin/env python3
"""Renders a weekly Blender video: any scene script that follows the weekly
convention, turned into one long seamless MP4, crash-safely.

    python weekly/common/render_driver.py --scene weekly/<week>/<scene>.py --duration 3h
    python weekly/common/render_driver.py --scene ... --speed-test
    python weekly/common/render_driver.py --scene ... --preview 60
    python weekly/common/render_driver.py --resume

Scene script convention (run inside Blender as `blender -b -P script -- args`):
    --seed N --start F --end F --outdir DIR --width W --height H --fps FPS
    --samples S   -> renders frames F..F-1 as DIR/f_0000123.jpg, skipping
                     frames already on disk, printing "FRAME <n> <seconds>"
    --still T --out PNG  -> renders one still at T seconds
Every frame must be a pure function of (seed, time): that is what makes
separately rendered chunks join seamlessly.

Crash safety: the video is rendered in 60-second chunks. Each finished chunk
is encoded (with a glow pass) into a small segment and its frames deleted; a
manifest records progress. --resume continues from the last frame on disk.
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

MANIFEST = "manifest.json"


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


def find_blender(explicit=None):
    """Explicit path > BLENDER env var > PATH > the usual install locations,
    newest version first."""
    cands = [explicit, os.environ.get("BLENDER"), shutil.which("blender")]
    pats = [r"C:\Program Files\Blender Foundation\Blender *\blender.exe",
            r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
            os.path.expanduser(r"~\AppData\Local\Programs\Blender Foundation\Blender *\blender.exe"),
            "/Applications/Blender.app/Contents/MacOS/Blender",
            "/usr/bin/blender", "/snap/bin/blender"]
    for pat in pats:
        cands.extend(sorted(glob.glob(pat), reverse=True))
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def glow_filter(height, out_fmt="yuv420p"):
    """Glow around bright things, keeping blacks black: only the highlights
    are blurred and screened back on (a tight halo and a wide one). Done in
    ffmpeg, identical on every Blender version."""
    s1 = max(1.0, height / 200.0)
    s2 = max(2.0, height / 55.0)
    s3 = max(4.0, height / 16.0)
    return (f"[0:v]format=gbrp,split=4[a][b][c][d];"
            f"[b]curves=all='0/0 0.50/0 1/1',gblur=sigma={s1:.2f}[g1];"
            f"[c]curves=all='0/0 0.40/0 1/1',gblur=sigma={s2:.2f}[g2];"
            f"[d]curves=all='0/0 0.45/0 1/0.8',gblur=sigma={s3:.2f}[g3];"
            f"[a][g1]blend=all_mode=screen:all_opacity=0.9[t];"
            f"[t][g2]blend=all_mode=screen:all_opacity=0.6[u];"
            f"[u][g3]blend=all_mode=screen:all_opacity=0.35,"
            f"vignette=angle=PI/5,format={out_fmt}[out]")


def auto_maxrate_mbps(w, h, fps):
    return max(8, round(w * h * fps * 0.2 / 1e6))


# ---------------------------------------------------------------------------

_SHOWN = []      # the device line is printed once per run, not once per chunk


def device_note(line):
    """Turn the scene's 'BLENDER 4.5.3 ENGINE OPTIX' line into plain words."""
    parts = line.split()
    dev = parts[-1] if len(parts) >= 4 else "?"
    if dev in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
        return f"Blender {parts[1]}: photoreal (Cycles) on the graphics card ({dev})"
    if dev == "CPU":
        return (f"Blender {parts[1]}: photoreal (Cycles) on the CPU - no supported graphics "
                "card found, this will be very slow. Update the NVIDIA driver, then in "
                "Blender: Edit > Preferences > System > Cycles Render Devices > OptiX.")
    return f"Blender {parts[1]}: standard look (EEVEE) on the graphics card"


def blender_args(s, extra):
    return ([s["blender"], "-b", "--factory-startup", "-P", s["scene"], "--",
             "--seed", str(s["seed"]), "--width", str(s["width"]),
             "--height", str(s["height"]), "--fps", str(s["fps"]),
             "--samples", str(s["samples"]), "--engine", s.get("engine", "eevee")] + extra)


def run_blender(s, first, last, frames_dir, progress):
    proc = subprocess.Popen(blender_args(s, ["--start", str(first), "--end", str(last),
                                             "--outdir", frames_dir]),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, errors="replace")
    tail = []
    for line in proc.stdout:
        if line.startswith("FRAME "):
            parts = line.split()
            progress(int(parts[1]), float(parts[2]))
        elif line.startswith("BLENDER ") and not _SHOWN:
            _SHOWN.append(line)
            print(f"  {device_note(line)}")
        else:
            tail = (tail + [line.rstrip()])[-25:]
    if proc.wait() != 0:
        raise RuntimeError("Blender stopped with an error. Last output:\n  " + "\n  ".join(tail))


def encode_chunk(s, first, count, frames_dir, out_ts):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(s["fps"]),
                    "-start_number", str(first), "-i", os.path.join(frames_dir, "f_%07d.jpg"),
                    "-frames:v", str(count), "-filter_complex", glow_filter(s["height"]),
                    "-map", "[out]", "-c:v", "libx264", "-crf", str(s["crf"]),
                    "-preset", "slow", "-maxrate", f"{s['maxrate']}M",
                    "-bufsize", f"{2 * s['maxrate']}M", "-f", "mpegts", out_ts + ".part"],
                   check=True)
    os.replace(out_ts + ".part", out_ts)


def write_manifest(pdir, s, done):
    tmp = os.path.join(pdir, MANIFEST + ".tmp")
    with open(tmp, "w") as f:
        json.dump({"settings": s, "done": sorted(done)}, f, indent=1)
    os.replace(tmp, os.path.join(pdir, MANIFEST))


def load_manifest(pdir):
    with open(os.path.join(pdir, MANIFEST)) as f:
        d = json.load(f)
    return d["settings"], set(d["done"])


def find_unfinished(outdir="output"):
    c = glob.glob(os.path.join(outdir, "*_parts", MANIFEST))
    return os.path.dirname(max(c, key=os.path.getmtime)) if c else None


def render(s):
    fps = s["fps"]
    total = int(round(s["duration"] * fps))
    per = int(round(s["chunk"] * fps))
    chunks = [(a, min(a + per, total)) for a in range(0, total, per)]
    pdir = s["parts_dir"]
    os.makedirs(pdir, exist_ok=True)
    try:
        _, done = load_manifest(pdir)
    except FileNotFoundError:
        done = set()
    write_manifest(pdir, s, done)
    started = time.time()
    finished_before = sum(b - a for i, (a, b) in enumerate(chunks) if i in done)
    count = [0]

    for i, (a, b) in enumerate(chunks):
        if i in done:
            continue
        fdir = os.path.join(pdir, f"frames_{i:05d}")

        def progress(frame, secs, i=i):
            count[0] += 1
            rate = count[0] / max(time.time() - started, 1e-6)
            left = (total - finished_before - count[0]) / max(rate, 1e-9)
            sys.stdout.write(f"\r  chunk {i + 1}/{len(chunks)}  frame {frame + 1}/{total}"
                             f"  {secs:5.2f} s/frame  ETA {fmt_ts(left)}   ")
            sys.stdout.flush()

        run_blender(s, a + s["start_frame"], b + s["start_frame"], fdir, progress)
        missing = [f for f in range(a, b) if not os.path.exists(
            os.path.join(fdir, f"f_{f + s['start_frame']:07d}.jpg"))]
        if missing:
            raise RuntimeError(f"chunk {i + 1}: {len(missing)} frames missing after render")
        encode_chunk(s, a + s["start_frame"], b - a, fdir, os.path.join(pdir, f"chunk_{i:05d}.ts"))
        shutil.rmtree(fdir, ignore_errors=True)
        done.add(i)
        write_manifest(pdir, s, done)
    print()
    return chunks


def join(s, chunks):
    pdir, out = s["parts_dir"], s["out"]
    listfile = os.path.join(pdir, "list.txt")
    with open(listfile, "w") as f:
        for i in range(len(chunks)):
            f.write(f"file 'chunk_{i:05d}.ts'\n")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listfile]
    if s.get("audio") and os.path.isfile(s["audio"]):
        cmd += ["-stream_loop", "-1", "-i", s["audio"], "-map", "0:v", "-map", "1:a",
                "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-map", "0:v"]
    cmd += ["-c:v", "copy"]
    size = sum(os.path.getsize(os.path.join(pdir, f"chunk_{i:05d}.ts")) for i in range(len(chunks)))
    if shutil.disk_usage(os.path.dirname(os.path.abspath(out))).free > size * 2.4:
        cmd += ["-movflags", "+faststart"]
    subprocess.run(cmd + ["-t", f"{s['duration']:.3f}", out], check=True)
    shutil.rmtree(pdir, ignore_errors=True)


def speed_test(s, frames=6):
    tmp = os.path.join("output", "_speedtest")
    shutil.rmtree(tmp, ignore_errors=True)
    times = []
    start = int(90 * s["fps"])
    proc = subprocess.Popen(blender_args(s, ["--start", str(start), "--end", str(start + frames + 2),
                                             "--outdir", tmp]),
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            errors="replace")
    for line in proc.stdout:
        if line.startswith("BLENDER "):
            print(f"  {device_note(line)}")
        elif line.startswith("FRAME "):
            times.append(float(line.split()[2]))
            sys.stdout.write(f"\r  test frame {len(times)}/{frames + 2}: {times[-1]:.2f} s   ")
            sys.stdout.flush()
    proc.wait()
    shutil.rmtree(tmp, ignore_errors=True)
    print()
    if len(times) < 3:
        print("Speed test failed - Blender did not render frames.")
        return 1
    per = sum(times[2:]) / len(times[2:])      # first frames include warm-up
    print(f"\n  {s['width']}x{s['height']}: {per:.2f} seconds per frame")
    for label, sec in (("10 minutes", 600), ("1 hour", 3600), ("3 hours", 10800)):
        print(f"  a {label:10s} video would take about {fmt_ts(per * sec * s['fps'])}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render a weekly Blender video.")
    ap.add_argument("--scene", help="the week's scene script (.py)")
    ap.add_argument("--duration", type=parse_duration, default=parse_duration("3h"))
    ap.add_argument("--resolution", default="1920x1080")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--engine", choices=["cycles", "eevee"], default="eevee",
                    help="eevee = standard look; cycles = photoreal path tracing (much slower)")
    ap.add_argument("--samples", type=int, default=None,
                    help="default: 48 for cycles (denoised), 16 for eevee")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--start-at", type=float, default=0.0, metavar="SEC")
    ap.add_argument("--audio", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--chunk", type=float, default=60.0)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--blender", default=None, help="path to blender(.exe)")
    ap.add_argument("--preview", type=float, default=None, metavar="T")
    ap.add_argument("--speed-test", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--resume-info", action="store_true")
    ap.add_argument("--ignore-space", action="store_true")
    args = ap.parse_args(argv)

    if args.resume or args.resume_info:
        pdir = find_unfinished()
        if pdir is None:
            print("No interrupted render found.")
            return 1
        s, done = load_manifest(pdir)
        n = -(-int(round(s["duration"] * s["fps"])) // int(round(s["chunk"] * s["fps"])))
        print(f"Interrupted render found: {s['out']}")
        print(f"  {s['width']}x{s['height']}, {fmt_ts(s['duration'])}, {len(done)}/{n} chunks finished")
        if args.resume_info:
            return 0
        s["blender"] = find_blender(args.blender) or s["blender"]
        join(s, render(s))
        print(f"done       {s['out']}")
        return 0

    if not args.scene or not os.path.isfile(args.scene):
        ap.error("--scene must point at the week's scene script")
    blender = find_blender(args.blender)
    if not blender:
        print("Blender was not found. Install Blender 4.5 LTS (free):")
        print("https://www.blender.org/download/lts/")
        return 1
    m = re.fullmatch(r"(\d+)x(\d+)", args.resolution.lower())
    if not m:
        ap.error("resolution must look like 1920x1080")
    w, h = int(m.group(1)) // 2 * 2, int(m.group(2)) // 2 * 2
    seed = args.seed if args.seed is not None else random.randrange(1, 10 ** 6)
    name = os.path.splitext(os.path.basename(args.scene))[0]
    os.makedirs("output", exist_ok=True)
    out = args.out or os.path.join("output", f"{name}_{seed}.mp4")
    s = {"scene": os.path.abspath(args.scene), "blender": blender, "seed": seed,
         "duration": args.duration, "width": w, "height": h, "fps": args.fps,
         "engine": args.engine,
         "samples": args.samples or (48 if args.engine == "cycles" else 16),
         "chunk": args.chunk, "crf": args.crf,
         "start_frame": int(round(args.start_at * args.fps)),
         "maxrate": auto_maxrate_mbps(w, h, args.fps),
         "audio": os.path.abspath(args.audio) if args.audio else None,
         "out": out, "parts_dir": out.rsplit(".", 1)[0] + "_parts"}

    if args.speed_test:
        print(f"Speed test: {w}x{h} @ {args.fps} fps, {args.engine}  (Blender: {blender})")
        return speed_test(s)
    if args.preview is not None:
        png = out.rsplit(".", 1)[0] + f"_t{args.preview:.0f}.png"
        subprocess.run(blender_args(s, ["--still", str(args.preview), "--out", os.path.abspath(png)]),
                       check=True, stdout=subprocess.DEVNULL)
        glow = png + ".glow.png"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", png, "-filter_complex",
                        glow_filter(h, "rgb24"), "-map", "[out]", glow], check=True)
        os.replace(glow, png)
        print(f"wrote      {png}")
        return 0

    worst = s["maxrate"] * 1e6 / 8 * args.duration / 1e9
    tmp = args.chunk * args.fps * w * h * 0.3 / 1e9
    free = shutil.disk_usage(os.path.abspath("output")).free / 1e9
    print(f"video      {name}, {w}x{h} @ {args.fps} fps, {fmt_ts(args.duration)}, seed {seed}")
    print(f"look       {args.engine} ({s['samples']} samples)")
    print(f"blender    {blender}")
    print(f"output     {out}")
    print(f"size       up to ~{worst:.1f} GB (+{tmp:.1f} GB working space); free {free:.0f} GB")
    if not args.ignore_space and worst + tmp > free * 0.95:
        print("\nWARNING: this may not fit on the drive (--ignore-space to override).")
        return 1
    join(s, render(s))
    print(f"done       {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
