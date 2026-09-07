#!/usr/bin/env python3
"""Reverse an already-rendered video WITHOUT re-rendering it.

The obvious `ffmpeg -vf reverse` buffers the whole file into RAM, so it can't
handle long videos. This splits the file into short chunks, reverses each one
(bounded memory), and concatenates them in reverse order to produce a fully
reversed video. Audio is reversed in sync (use --mute to drop it instead).

    python3 reverse_video.py "output\\portal_12345.mp4"

writes  output\\portal_12345_reversed.mp4  next to the original."""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format",
         "-of", "json", path],
        capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    has_audio = any(s.get("codec_type") == "audio" for s in info["streams"])
    dur = float(info["format"].get("duration", 0.0))
    return has_audio, dur


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Reverse a video file without re-rendering it.")
    ap.add_argument("input", help="the video file to reverse")
    ap.add_argument("--out", default=None,
                    help="output path (default: <name>_reversed.mp4)")
    ap.add_argument("--segment", type=float, default=8.0,
                    help="seconds per work chunk; lower it if a 4K reverse "
                         "runs out of memory (default 8)")
    ap.add_argument("--codec", default="libx264",
                    help="libx264 (default) or h264_nvenc / hevc_nvenc")
    ap.add_argument("--crf", type=int, default=16,
                    help="quality of the reversed copy, lower = better (default 16)")
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--mute", action="store_true",
                    help="drop the audio instead of reversing it")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.input):
        ap.error(f"file not found: {args.input}")

    has_audio, dur = probe(args.input)
    if args.mute:
        has_audio = False

    base, ext = os.path.splitext(args.input)
    out = args.out or base + "_reversed" + ext
    out_dir = os.path.dirname(os.path.abspath(out)) or "."
    os.makedirs(out_dir, exist_ok=True)

    print(f"input      {args.input}  ({int(dur//3600)}:{int(dur%3600//60):02d}:{int(dur%60):02d})")
    print(f"output     {out}")
    print(f"audio      {'reversed' if has_audio else 'none'}")

    tmp = tempfile.mkdtemp(prefix="reverse_", dir=out_dir)
    try:
        # 1) split into chunks by stream copy (fast, no quality loss)
        sys.stdout.write("splitting...  "); sys.stdout.flush()
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", args.input,
             "-c", "copy", "-map", "0",
             "-f", "segment", "-segment_time", str(args.segment),
             "-reset_timestamps", "1",
             os.path.join(tmp, "part_%05d.ts")],
            check=True)
        parts = sorted(glob.glob(os.path.join(tmp, "part_*.ts")))
        print(f"{len(parts)} chunks")
        if not parts:
            raise RuntimeError("no chunks produced — is the input a valid video?")

        # 2) reverse each chunk. Process the ORIGINAL LAST chunk first so the
        #    rev_ files, in numeric order, already form the reversed timeline.
        for i, part in enumerate(reversed(parts)):
            rev = os.path.join(tmp, f"rev_{i:05d}.ts")
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", part, "-vf", "reverse"]
            cmd += ["-af", "areverse"] if has_audio else ["-an"]
            cmd += ["-c:v", args.codec]
            if args.codec == "libx264":
                cmd += ["-crf", str(args.crf), "-preset", args.preset]
            elif args.codec.endswith("_nvenc"):
                cmd += ["-cq", str(args.crf), "-preset", "p5", "-rc", "vbr"]
            if has_audio:
                cmd += ["-c:a", "aac", "-b:a", "192k"]
            cmd += ["-f", "mpegts", rev]
            subprocess.run(cmd, check=True)
            sys.stdout.write(f"\r  reversing chunk {i+1}/{len(parts)}   ")
            sys.stdout.flush()
        print()

        # 3) concatenate the reversed chunks (already in the right order)
        sys.stdout.write("stitching...  "); sys.stdout.flush()
        listfile = os.path.join(tmp, "list.txt")
        with open(listfile, "w") as f:
            for i in range(len(parts)):
                f.write(f"file 'rev_{i:05d}.ts'\n")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", listfile,
             "-c", "copy", "-movflags", "+faststart", out],
            check=True)
        print("done")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\nreversed video written to  {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
