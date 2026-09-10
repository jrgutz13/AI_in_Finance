"""Command line interface for the portal machine."""

import argparse
import os
import random
import re
import shutil
import subprocess
import sys

from .continuous import ContinuousTrack
from .parts import find_unfinished, join_parts, load_manifest, render_parts
from .renderer import Renderer, auto_maxrate_mbps, encode
from .scenes import SCENES
from .sequencer import build_timeline


def parse_duration(text):
    """Accepts '3h', '2h30m', '90m', '45s', '1:30:00', or plain seconds."""
    text = text.strip().lower()
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return float(text)
    if ":" in text:
        parts = [float(p) for p in text.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        h, m, s = parts
        return h * 3600 + m * 60 + s
    total, matched = 0.0, False
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([hms])", text):
        total += float(value) * {"h": 3600, "m": 60, "s": 1}[unit]
        matched = True
    if not matched:
        raise argparse.ArgumentTypeError(f"can't parse duration '{text}'")
    return total


def parse_resolution(text):
    m = re.fullmatch(r"(\d+)x(\d+)", text.strip().lower())
    if not m:
        raise argparse.ArgumentTypeError("resolution must look like 1920x1080")
    w, h = int(m.group(1)), int(m.group(2))
    return w - w % 2, h - h % 2  # encoder needs even dimensions


def fmt_ts(seconds):
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def write_chapters(clips, path):
    """YouTube-style chapter list, one line per clip (paste into description)."""
    with open(path, "w") as f:
        for c in clips:
            f.write(f"{fmt_ts(c.start)} {SCENES[c.scene].title}\n")


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="portal-machine",
        description="Generates random psychedelic portal/kaleidoscope videos.",
    )
    ap.add_argument("--duration", type=parse_duration, default="60s",
                    help="video length, e.g. 3h, 90m, 45s, 1:30:00 (default 60s)")
    ap.add_argument("--resolution", type=parse_resolution, default="1920x1080",
                    help="WxH, e.g. 3840x2160 (default 1920x1080)")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--seed", type=int, default=None,
                    help="same seed + settings = same video (default: random)")
    ap.add_argument("--out", default=None,
                    help="output file (default output/portal_<seed>.mp4)")
    ap.add_argument("--audio", default=None,
                    help="music file to loop under the video (mp3/wav/m4a)")
    ap.add_argument("--clip-min", type=float, default=7.0,
                    help="shortest clip length in seconds (default 7)")
    ap.add_argument("--clip-max", type=float, default=10.0,
                    help="longest clip length in seconds (default 10)")
    ap.add_argument("--crossfade", type=float, default=1.0,
                    help="crossfade seconds between clips, 0 = hard cuts (default 1)")
    ap.add_argument("--scenes", default=None,
                    help="comma-separated subset of scenes to use")
    ap.add_argument("--continuous", dest="continuous", action="store_true",
                    default=None,
                    help="one endless evolving instance with no clip breaks "
                         "(automatic when a single style is chosen)")
    ap.add_argument("--clips", dest="continuous", action="store_false",
                    help="force the clip/crossfade montage even for one style")
    ap.add_argument("--codec", default="libx264",
                    help="libx264 (default), or h264_nvenc / hevc_nvenc on NVIDIA")
    ap.add_argument("--crf", type=int, default=20,
                    help="quality, lower = better/bigger (default 20)")
    ap.add_argument("--preset", default="medium",
                    help="x264 speed/size preset (default medium)")
    ap.add_argument("--maxrate", type=int, default=None, metavar="MBPS",
                    help="bitrate ceiling in Mbit/s; keeps file size bounded "
                         "even on very noisy scenes (default: auto from "
                         "resolution, 0 = no ceiling)")
    ap.add_argument("--speed-scale", type=float, default=1.0, metavar="X",
                    help="multiply how fast everything moves: 0.5 = half "
                         "speed, 2 = double (default 1)")
    ap.add_argument("--ignore-space", action="store_true",
                    help="skip the free-disk-space check before rendering")
    ap.add_argument("--part-length", type=float, default=600.0, metavar="SEC",
                    help="videos longer than this render in crash-safe parts "
                         "of this many seconds (default 600; 0 = single pass)")
    ap.add_argument("--resume", action="store_true",
                    help="continue the most recent interrupted render "
                         "(all other options are taken from its manifest)")
    ap.add_argument("--resume-info", action="store_true",
                    help="describe the most recent interrupted render if any "
                         "(exit code 0), else exit code 1")
    ap.add_argument("--still", type=float, default=None, metavar="T",
                    help="render a single PNG frame at time T instead of a video")
    ap.add_argument("--list-scenes", action="store_true")
    args = ap.parse_args(argv)

    if args.list_scenes:
        for name, scene in SCENES.items():
            print(f"{name:16s} {scene.title}")
        return 0

    if args.resume_info or args.resume:
        pdir = find_unfinished()
        if pdir is None:
            print("No interrupted render found.")
            return 1
        settings, done = load_manifest(pdir)
        total_parts = -(-settings["duration"] // settings["part_length"])
        print(f"Interrupted render found: {settings['out']}")
        print(f"  {settings['width']}x{settings['height']} @ {settings['fps']} fps, "
              f"{fmt_ts(settings['duration'])}, seed {settings['seed']}")
        print(f"  {len(done)}/{int(total_parts)} parts finished "
              f"({100 * len(done) / total_parts:.0f}%)")
        if args.resume_info:
            return 0
        return run(settings, resuming=True)

    if isinstance(args.duration, str):
        args.duration = parse_duration(args.duration)
    if isinstance(args.resolution, str):
        args.resolution = parse_resolution(args.resolution)

    seed = args.seed if args.seed is not None else random.randrange(10 ** 9)
    scene_names = args.scenes.split(",") if args.scenes else None
    if scene_names:
        for n in scene_names:
            if n not in SCENES:
                ap.error(f"unknown scene '{n}' (see --list-scenes)")
    if args.audio and not os.path.isfile(args.audio):
        ap.error(f"audio file not found: {args.audio}")

    # continuous by default when exactly one distinct style is requested
    unique = list(dict.fromkeys(scene_names)) if scene_names else list(SCENES)
    continuous = args.continuous
    if continuous is None:
        continuous = len(unique) == 1
    if continuous and len(unique) != 1:
        ap.error("--continuous needs exactly one --scenes style")

    w, h = args.resolution
    settings = {
        "seed": seed,
        "duration": args.duration,
        "width": w, "height": h,
        "fps": args.fps,
        "scenes": args.scenes,
        "continuous": continuous,
        "clip_min": args.clip_min, "clip_max": args.clip_max,
        "crossfade": args.crossfade,
        "codec": args.codec, "crf": args.crf, "preset": args.preset,
        "maxrate": args.maxrate if args.maxrate is not None
                   else auto_maxrate_mbps(w, h, args.fps),
        "audio": os.path.abspath(args.audio) if args.audio else None,
        "out": args.out or os.path.join("output", f"portal_{seed}.mp4"),
        "part_length": args.part_length,
        "speed_scale": args.speed_scale,
    }
    return run(settings, still=args.still, ignore_space=args.ignore_space)


def run(settings, still=None, ignore_space=False, resuming=False):
    """Renders a video from a settings dict (also stored in part manifests,
    which is what makes --resume reproduce the identical video)."""
    seed = settings["seed"]
    w, h = settings["width"], settings["height"]
    duration, fps = settings["duration"], settings["fps"]
    out, maxrate = settings["out"], settings["maxrate"]
    scene_names = settings["scenes"].split(",") if settings["scenes"] else None
    unique = list(dict.fromkeys(scene_names)) if scene_names else list(SCENES)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    if settings["audio"] and not os.path.isfile(settings["audio"]):
        print(f"NOTE: audio file no longer found ({settings['audio']}); "
              f"rendering silent.")
        settings["audio"] = None

    rng = random.Random(seed)
    clips = None
    if settings["continuous"]:
        track = ContinuousTrack(unique[0], duration, rng)
        frame_fn = lambda t: renderer.render_continuous(track, t)
        mode_desc = f"continuous {SCENES[unique[0]].title}"
    else:
        clips = build_timeline(
            duration, seed,
            clip_min=settings["clip_min"], clip_max=settings["clip_max"],
            crossfade=settings["crossfade"], scene_names=scene_names,
        )
        frame_fn = lambda t: renderer.render_frame(clips, t)
        mode_desc = f"{len(clips)} clips"

    if not resuming:
        print(f"seed       {seed}")
        print(f"video      {w}x{h} @ {fps} fps, {fmt_ts(duration)}, {mode_desc}")
        print(f"output     {out}")

    # worst-case size from the bitrate ceiling; real files usually land at
    # 40-70% of this. Refuse to start a render that cannot fit on disk.
    if maxrate and still is None and not resuming:
        worst_gb = maxrate * 1e6 / 8 * duration / 1e9
        free_gb = shutil.disk_usage(os.path.dirname(os.path.abspath(out))).free / 1e9
        print(f"size       up to ~{worst_gb:.1f} GB "
              f"(bitrate capped at {maxrate} Mbit/s; typical is well under the cap)")
        print(f"disk free  {free_gb:.1f} GB")
        if not ignore_space and worst_gb > free_gb * 0.95:
            print()
            print("WARNING: the worst-case file size may not fit on this drive.")
            print("Options: free up space, use a shorter --duration, a lower")
            print("resolution, --crf 23, or a lower --maxrate.")
            if sys.stdin is not None and sys.stdin.isatty():
                answer = input("Continue anyway? [y/N] ").strip().lower()
                if answer not in ("y", "yes"):
                    print("Stopped before rendering. Nothing was written.")
                    return 1
            else:
                print("Stopped before rendering (use --ignore-space to override).")
                return 1

    # .get() so part manifests written before this option existed still resume
    renderer = Renderer(w, h, scene_names=unique,
                        speed_scale=settings.get("speed_scale", 1.0))

    if still is not None:
        png = out.rsplit(".", 1)[0] + f"_t{still:.0f}.png"
        frame = frame_fn(min(still, duration))
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo",
             "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-i", "-",
             "-frames:v", "1", png],
            input=frame, check=True)
        print(f"wrote      {png}")
        return 0

    if settings["part_length"] and duration > settings["part_length"]:
        # crash-safe mode: parts survive shutdowns; --resume continues them
        render_parts(renderer, frame_fn, settings)
        print("joining parts...")
        join_parts(settings)
    else:
        encode(renderer, frame_fn, duration, fps, out,
               audio=settings["audio"], codec=settings["codec"],
               crf=settings["crf"], preset=settings["preset"],
               maxrate_mbps=maxrate)

    chapters = out.rsplit(".", 1)[0] + "_chapters.txt"
    if settings["continuous"]:
        with open(chapters, "w") as f:
            f.write(f"00:00:00 {SCENES[unique[0]].title}\n")
    else:
        write_chapters(clips, chapters)
    print(f"done       {out}")
    print(f"chapters   {chapters}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
