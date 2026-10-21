#!/usr/bin/env python3
"""Add music to a finished video WITHOUT re-rendering it.

The picture is copied as-is (no re-encoding), so even a 3-hour video takes
only a few minutes. The music repeats back to back for the whole video,
exactly as the track plays (it is decoded once and the decoded audio is
looped, so no gaps or clicks creep in at the repeats), and fades out over the
last 5 seconds. Any sound already in the video is replaced.

    python3 add_music.py "output\\portal_12345.mp4" "my music.mp3"

writes  output\\portal_12345_music.mp4  next to the video. The two files can
be given in either order."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".aiff", ".aif"}


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Add music to a finished video without re-rendering it.")
    ap.add_argument("files", nargs=2, metavar="FILE", help="the video and the music file, in any order")
    ap.add_argument("--out", default=None, help="output path (default: <video>_music.mp4)")
    ap.add_argument("--fade", type=float, default=5.0,
                    help="seconds of fade-out at the end (0 = none, default 5)")
    args = ap.parse_args(argv)

    a, b = (os.path.abspath(f.strip().strip('"')) for f in args.files)
    for f in (a, b):
        if not os.path.isfile(f):
            print(f"File not found: {f}")
            return 1
    a_is_audio = os.path.splitext(a)[1].lower() in AUDIO_EXTS
    b_is_audio = os.path.splitext(b)[1].lower() in AUDIO_EXTS
    if a_is_audio == b_is_audio:
        print("Give one video file and one music file (mp3, wav, m4a, ...).")
        return 1
    video, music = (b, a) if a_is_audio else (a, b)
    out = args.out or os.path.splitext(video)[0] + "_music.mp4"
    if os.path.abspath(out) == video:
        print("The output can't overwrite the original video.")
        return 1

    dur = duration(video)
    print(f"video   {video}  ({int(dur // 3600)}:{int(dur % 3600 // 60):02d}:{int(dur % 60):02d})")
    print(f"music   {music}  ({duration(music):.0f} s, repeated to fill the video)")
    print(f"output  {out}")

    tmp = tempfile.mkdtemp(prefix="add_music_")
    try:
        wav = os.path.join(tmp, "music.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", music, "-vn",
                        "-c:a", "pcm_s16le", wav], check=True)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-stats",
               "-i", video, "-stream_loop", "-1", "-i", wav,
               "-map", "0:v", "-map", "1:a", "-c:v", "copy"]
        if args.fade > 0:
            cmd += ["-af", f"afade=t=out:st={max(0.0, dur - args.fade):.3f}:d={args.fade}"]
        cmd += ["-c:a", "aac", "-b:a", "192k", "-shortest", "-t", f"{dur:.3f}"]
        # faststart rewrites the file once more at the end: only when it fits
        free = shutil.disk_usage(os.path.dirname(os.path.abspath(out)) or ".").free
        if free > os.path.getsize(video) * 2.2:
            cmd += ["-movflags", "+faststart"]
        elif free < os.path.getsize(video) * 1.1:
            print("Not enough free disk space for the new copy of the video.")
            return 1
        subprocess.run(cmd + [out], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\ndone    {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
