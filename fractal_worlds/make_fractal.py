#!/usr/bin/env python3
"""Fractal Worlds: an endless, collision-free flight over a fractal alien
landscape, rendered by Mandelbulber2 (free, open source).

    python fractal_worlds/make_fractal.py --duration 3h --audio music.mp3
    python fractal_worlds/make_fractal.py --preview 60      # one still at t=60 s
    python fractal_worlds/make_fractal.py --speed-test
    python fractal_worlds/make_fractal.py --resume          # after a crash

How it works
  1. Plan: a never-repeating route is laid over the landscape, and the ground
     height is MEASURED every half rock-width along it (Mandelbulber has no
     distance output; see mb.depth_probe for the two-fog-color trick). The
     camera altitude is then computed to always clear the ground, climbing
     smoothly well before spires.
  2. Render: in 60-second chunks. Each chunk is a Mandelbulber keyframe
     animation with one keyframe per frame (our code decides every pose),
     encoded with a bloom/film pass and its frames deleted.
  3. Join: chunks are concatenated without re-encoding, music is added, and
     a credits file is written.
Light and color drift continuously through "moods" (golden hour, magenta
dusk, teal dawn...) while the sun slowly circles the sky.

Crash-safe: the plan and finished chunks are kept in a _parts folder with a
manifest. --resume continues; inside an unfinished chunk Mandelbulber skips
frames already on disk.
"""

import argparse
import glob
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mb  # noqa: E402
import planner as pl  # noqa: E402

PRESETS = {
    "golden_spires": {
        "file": "golden_spires.fract",
        "title": "Golden Spires",
        "clearance": 0.35,         # in rock-widths (the scene's scale unit L)
        "speed": 0.35,             # rock-widths per second
        "credit": ("Fractal scene adapted from Mandelbulber2 example 'aexion002' "
                   "(formula: Aexion). Mandelbulber2 (c) Krzysztof Marczak and "
                   "contributors, GPL v3 - https://github.com/buddhi1980/mandelbulber2"),
    },
}
DS = 0.5          # ground probe spacing along the route, in rock-widths
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


def film_filter(height, out_fmt="yuv420p"):
    """Bloom (two blurred highlight layers screened back on), faint lens
    fringing, a vignette and fine moving grain — same look as Blender Worlds."""
    s1 = max(1.0, height / 180.0)
    s2 = max(2.0, height / 45.0)
    ca = max(1, round(height / 1080))
    return (f"[0:v]format=gbrp,split=3[a][b][c];"
            f"[b]curves=all='0/0 0.70/0 1/1',gblur=sigma={s1:.2f}[g1];"
            f"[c]curves=all='0/0 0.62/0 1/1',gblur=sigma={s2:.2f}[g2];"
            f"[a][g1]blend=all_mode=screen:all_opacity=0.6[t];"
            f"[t][g2]blend=all_mode=screen:all_opacity=0.35,"
            f"rgbashift=rh=-{ca}:bh={ca},vignette=angle=PI/5,"
            f"format={out_fmt},noise=c0s=3:c0f=t[out]")


def auto_maxrate_mbps(w, h, fps):
    return max(6, round(w * h * fps * 0.16 / 1e6))


# ---------------------------------------------------------------------------
# world: scene + plan
# ---------------------------------------------------------------------------

class World:
    def __init__(self, settings, exe):
        self.s = settings
        self.exe = exe
        preset = PRESETS[settings["preset"]]
        self.preset = preset
        self.scene = mb.Scene.load(os.path.join(HERE, "presets", preset["file"]))
        cam0 = mb.num3(self.scene.main["camera"])
        tgt0 = mb.num3(self.scene.main["target"])
        self.L = float(np.linalg.norm(tgt0 - cam0))
        self.z0 = float(cam0[2])
        self.route = pl.Route(cam0[:2], self.L, settings["seed"])
        self.moods = pl.MoodTrack(settings["seed"], settings["start_at"] + settings["duration"])
        self.speed = preset["speed"] * self.L * settings["speed_scale"]
        self.flight = None

    def s_at(self, t):
        return self.speed * t

    def plan(self, pdir, log=print):
        """Probe the ground along the whole route (cached in pdir/plan.npz)."""
        cache = os.path.join(pdir, "plan.npz")
        ds = DS * self.L
        s_end = self.s_at(self.s["start_at"] + self.s["duration"]) + 30 * self.L
        n = int(math.ceil(s_end / ds)) + 1
        if os.path.exists(cache):
            ground = np.load(cache)["ground"]
            if len(ground) >= n:
                self.flight = pl.Flight(self.route, ground, ds, self.preset["clearance"])
                return
        ZP = self.z0 + 8 * self.L
        ground = np.full(n, np.nan)
        batch = 400
        t0 = time.time()
        for a in range(0, n, batch):
            b = min(n, a + batch)
            xy = self.route.xy(np.arange(a, b) * ds)
            poses = [((x, y, ZP), (x, y, ZP - self.L), (0.0, 1.0, 0.0)) for x, y in xy]
            d = mb.depth_probe(self.exe, self.scene, poses, vis=8 * self.L,
                               workdir=os.path.join(pdir, "probe"), res=8, fov=0.15,
                               gpu=self.s["gpu"])
            for i, di in enumerate(d):
                c = di[2:6, 2:6]
                if np.isfinite(c).any():
                    ground[a + i] = ZP - c[np.isfinite(c)].min()
            rate = b / max(time.time() - t0, 1e-6)
            sys.stdout.write(f"\r  mapping terrain {b}/{n}  ETA {fmt_ts((n - b) / rate)}   ")
            sys.stdout.flush()
        print()
        shutil.rmtree(os.path.join(pdir, "probe"), ignore_errors=True)
        missing = int(np.isnan(ground).sum())
        if missing:
            log(f"note       {missing} of {n} terrain samples found no ground; using nearby heights")
            idx = np.arange(n)
            ok = np.isfinite(ground)
            ground = np.interp(idx, idx[ok], ground[ok])
        np.savez(cache, ground=ground)
        self.flight = pl.Flight(self.route, ground, ds, self.preset["clearance"])

    def frame_keys(self, frame):
        t = self.s["start_at"] + frame / self.s["fps"]
        cols = mb.pose_columns(*self.flight.pose(self.s_at(t)))
        cols.update(pl.mood_columns(self.moods.at(t)))
        return cols

    def write_chunk(self, path, first, last):
        """Scene file whose keyframes 0..(last-first) are frames first..last."""
        kfs = [self.frame_keys(f) for f in range(first, last + 1)]
        sc = self.scene.copy().set(frames_per_keyframe=1,
                                   keyframe_last_to_render=last - first,
                                   jpeg_quality=95,
                                   image_width=self.s["width"], image_height=self.s["height"])
        sc.write(path, kfs)


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def gpu_works(exe, workdir):
    """One tiny OpenCL render; False if there is no usable GPU driver."""
    os.makedirs(workdir, exist_ok=True)
    out = os.path.join(workdir, "gputest.png")
    fract = os.path.join(HERE, "presets", PRESETS["golden_spires"]["file"])
    try:
        r = subprocess.run([exe, "--nogui", "--gpu", "--res", "64x36", "--format", "png",
                            "--output", out, fract], stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=300)
    except subprocess.TimeoutExpired:
        return False
    ok = r.returncode == 0 and os.path.exists(out)
    shutil.rmtree(workdir, ignore_errors=True)
    return ok


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
    c = glob.glob(os.path.join(outdir, "fractal_*_parts", MANIFEST))
    return os.path.dirname(max(c, key=os.path.getmtime)) if c else None


def render(settings, exe):
    pdir = settings["parts_dir"]
    os.makedirs(pdir, exist_ok=True)
    try:
        _, done = load_manifest(pdir)
    except FileNotFoundError:
        done = set()
    write_manifest(pdir, settings, done)

    world = World(settings, exe)
    world.plan(pdir)

    fps = settings["fps"]
    total = int(round(settings["duration"] * fps))
    per = int(round(settings["chunk"] * fps))
    chunks = [(a, min(a + per, total)) for a in range(0, total, per)]
    started = time.time()
    base = sum(b - a for i, (a, b) in enumerate(chunks) if i in done)
    rendered = [0]

    for i, (a, b) in enumerate(chunks):
        if i in done:
            continue
        fdir = os.path.join(pdir, f"frames_{i:05d}")
        fract = os.path.join(pdir, f"chunk_{i:05d}.fract")
        world.write_chunk(fract, a, b)
        already = len(glob.glob(os.path.join(fdir, "frame_*.jpg")))

        def progress(n_done, i=i, already=already):
            rendered[0] = max(rendered[0], n_done - already + sum(
                bb - aa for j, (aa, bb) in enumerate(chunks) if j < i and j not in done))
            if rendered[0] <= 0:
                # no frame finished yet this session: a rate would be nonsense
                sys.stdout.write(f"\r  chunk {i + 1}/{len(chunks)}  frame {a + n_done}/{total}"
                                 f"  (rendering first frame...)   ")
                sys.stdout.flush()
                return
            el = time.time() - started
            rate = rendered[0] / max(el, 1e-6)
            left = (total - base - rendered[0]) / rate
            spf = 1.0 / rate
            speed = f"{rate:5.2f} fps" if rate >= 1 else f"{spf:5.1f} s/frame"
            sys.stdout.write(f"\r  chunk {i + 1}/{len(chunks)}  frame {a + n_done}/{total}"
                             f"  {speed}  ETA {fmt_ts(left)}   ")
            sys.stdout.flush()

        paths = mb.render_keyframes(exe, fract, fdir, 0, b - a, settings["width"],
                                    settings["height"], fmt="jpg", gpu=settings["gpu"],
                                    progress=progress)
        missing = [p for p in paths if not os.path.exists(p)]
        if missing:
            raise RuntimeError(f"chunk {i + 1}: {len(missing)} frames missing after render")
        out_ts = os.path.join(pdir, f"chunk_{i:05d}.ts")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
                        "-i", os.path.join(fdir, "frame_%07d.jpg"), "-frames:v", str(b - a),
                        "-filter_complex", film_filter(settings["height"]), "-map", "[out]",
                        "-c:v", "libx264", "-crf", str(settings["crf"]), "-preset", "medium",
                        "-maxrate", f"{settings['maxrate']}M",
                        "-bufsize", f"{2 * settings['maxrate']}M",
                        "-f", "mpegts", out_ts + ".part"], check=True)
        os.replace(out_ts + ".part", out_ts)
        shutil.rmtree(fdir, ignore_errors=True)
        done.add(i)
        write_manifest(pdir, settings, done)
    print()
    return world, chunks


def join(settings, world, chunks):
    pdir, out = settings["parts_dir"], settings["out"]
    listfile = os.path.join(pdir, "list.txt")
    with open(listfile, "w") as f:
        for i in range(len(chunks)):
            f.write(f"file 'chunk_{i:05d}.ts'\n")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listfile]
    audio = settings.get("audio")
    if audio and os.path.isfile(audio):
        cmd += ["-stream_loop", "-1", "-i", audio, "-map", "0:v", "-map", "1:a",
                "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-map", "0:v"]
    cmd += ["-c:v", "copy"]
    size = sum(os.path.getsize(os.path.join(pdir, f"chunk_{i:05d}.ts")) for i in range(len(chunks)))
    if shutil.disk_usage(os.path.dirname(os.path.abspath(out))).free > size * 2.4:
        cmd += ["-movflags", "+faststart"]
    subprocess.run(cmd + ["-t", f"{settings['duration']:.3f}", out], check=True)
    with open(out.rsplit(".", 1)[0] + "_credits.txt", "w") as f:
        f.write(world.preset["credit"] + "\n")
    shutil.rmtree(pdir, ignore_errors=True)


# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Fly over a fractal alien landscape (Mandelbulber2).")
    ap.add_argument("--duration", type=parse_duration, default=parse_duration("1m"))
    ap.add_argument("--resolution", default="1920x1080")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--preset", choices=list(PRESETS), default="golden_spires")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--start-at", type=float, default=0.0, metavar="SEC",
                    help="begin this many seconds into the journey")
    ap.add_argument("--speed-scale", type=float, default=1.0)
    ap.add_argument("--audio", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--chunk", type=float, default=60.0)
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--cpu", action="store_true", help="never try the GPU")
    ap.add_argument("--mandelbulber", default=None, help="path to mandelbulber2(.exe)")
    ap.add_argument("--preview", type=float, default=None, metavar="T",
                    help="render one PNG at T seconds instead of a video")
    ap.add_argument("--speed-test", action="store_true")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--resume-info", action="store_true")
    ap.add_argument("--ignore-space", action="store_true")
    args = ap.parse_args(argv)

    exe = mb.find_mandelbulber(args.mandelbulber)

    if args.resume or args.resume_info:
        pdir = find_unfinished()
        if pdir is None:
            print("No interrupted fractal render found.")
            return 1
        settings, done = load_manifest(pdir)
        n = -(-int(round(settings["duration"] * settings["fps"]))
              // int(round(settings["chunk"] * settings["fps"])))
        print(f"Interrupted fractal render found: {settings['out']}")
        print(f"  {settings['width']}x{settings['height']}, {fmt_ts(settings['duration'])},"
              f" seed {settings['seed']}, {len(done)}/{n} chunks finished")
        if args.resume_info:
            return 0
        exe = exe or settings.get("exe")
        if not exe or not os.path.isfile(exe):
            print("Mandelbulber2 not found.")
            return 1
        world, chunks = render(settings, exe)
        print("joining chunks...")
        join(settings, world, chunks)
        print(f"done       {settings['out']}")
        return 0

    if not exe:
        print("Mandelbulber2 was not found on this computer.")
        print("Download it free from https://github.com/buddhi1980/mandelbulber2/releases")
        print('or pass its location with --mandelbulber "C:\\path\\to\\mandelbulber2.exe"')
        return 1

    m = re.fullmatch(r"(\d+)x(\d+)", args.resolution.lower())
    if not m:
        ap.error("resolution must look like 1920x1080")
    w, h = int(m.group(1)) // 2 * 2, int(m.group(2)) // 2 * 2
    seed = args.seed if args.seed is not None else random.randrange(1, 10 ** 9)
    os.makedirs("output", exist_ok=True)
    out = args.out or os.path.join("output", f"fractal_{seed}.mp4")
    pdir = out.rsplit(".", 1)[0] + "_parts"
    gpu = False if args.cpu else gpu_works(exe, os.path.join("output", "_gputest"))
    settings = {
        "preset": args.preset, "seed": seed, "duration": args.duration,
        "start_at": args.start_at, "width": w, "height": h, "fps": args.fps,
        "speed_scale": args.speed_scale, "chunk": args.chunk, "crf": args.crf,
        "maxrate": auto_maxrate_mbps(w, h, args.fps),
        "audio": os.path.abspath(args.audio) if args.audio else None,
        "out": out, "parts_dir": pdir, "exe": exe, "gpu": gpu,
    }
    print(f"seed       {seed}")
    print(f"world      {PRESETS[args.preset]['title']}   renderer: Mandelbulber "
          f"{'GPU (OpenCL)' if gpu else 'CPU'}")

    if args.preview is not None or args.speed_test:
        tmp = os.path.join("output", "_fractal_tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
        t_at = args.preview if args.preview is not None else 60.0
        settings["start_at"], settings["duration"] = t_at, 1.0
        world = World(settings, exe)
        world.plan(tmp)
        frames = 1 if args.preview is not None else 4
        fract = os.path.join(tmp, "p.fract")
        world.write_chunk(fract, 0, frames)
        t0, times = time.time(), []
        paths = mb.render_keyframes(exe, fract, os.path.join(tmp, "f"), 0, frames, w, h,
                                    fmt="png", gpu=gpu,
                                    progress=lambda n: times.append(time.time()))
        if args.speed_test:
            per = (time.time() - t0) / frames
            print(f"\n  {w}x{h}: about {per:.1f} seconds per frame")
            for label, sec in (("10 minutes", 600), ("1 hour", 3600), ("3 hours", 10800)):
                print(f"  a {label:10s} video would take about {fmt_ts(per * sec * args.fps)}")
        else:
            png = out.rsplit(".", 1)[0] + f"_t{t_at:.0f}.png"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", paths[0],
                            "-filter_complex", film_filter(h, "rgb24"), "-map", "[out]", png],
                           check=True)
            print(f"wrote      {png}")
        shutil.rmtree(tmp, ignore_errors=True)
        return 0

    worst = settings["maxrate"] * 1e6 / 8 * args.duration / 1e9
    frames_tmp = args.chunk * args.fps * w * h * 0.25 / 1e9
    free = shutil.disk_usage(os.path.abspath("output")).free / 1e9
    print(f"video      {w}x{h} @ {args.fps} fps, {fmt_ts(args.duration)}")
    print(f"output     {out}")
    print(f"size       up to ~{worst:.1f} GB (+{frames_tmp:.1f} GB working space)")
    if not args.ignore_space and worst + frames_tmp > free * 0.95:
        print("\nWARNING: this may not fit on the drive (--ignore-space to override).")
        return 1
    world, chunks = render(settings, exe)
    print("joining chunks...")
    join(settings, world, chunks)
    print(f"done       {out}")
    print(f"credits    {out.rsplit('.', 1)[0]}_credits.txt  (paste into the video description)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
