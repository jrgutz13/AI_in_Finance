#!/usr/bin/env python3
"""Add music to a finished video WITHOUT re-rendering it.

The picture is copied as-is (no re-encoding), so even a 3-hour video takes
only a few minutes. The music repeats back to back for the whole video,
exactly as the track plays (it is decoded once and the decoded audio is
looped, so no gaps or clicks creep in at the repeats), and fades out over the
last 5 seconds. Any sound already in the video is replaced.

    python3 add_music.py "output\\portal_12345.mp4" "my music.mp3"

writes  output\\portal_12345_music.mp4  next to the video. The two can be
given in either order.

The music can also be a FOLDER of songs: the songs crossfade into each other
(4 s by default, see --crossfade), and the playlist repeats - crossfading from the last song back
into the first - for the length of the video. Songs named with --order play
first, in that order (names can be partial and ignore case/punctuation); the
rest follow alphabetically:

    python3 add_music.py video.mp4 "output\\Halloween" --order "Skeleton Dance;Dark Walk"
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

SR = 48000                    # working sample rate (stereo, 16-bit)
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".aiff", ".aif"}


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def playlist(folder, order):
    """Songs in the folder: the ones named in `order` first (in that order,
    matched loosely), then the rest alphabetically. Returns (files, missing)."""
    songs = sorted((f for f in os.listdir(folder)
                    if os.path.splitext(f)[1].lower() in AUDIO_EXTS
                    and os.path.isfile(os.path.join(folder, f))), key=str.lower)
    chosen, missing = [], []
    for name in order:
        key = _norm(name)
        if not key:
            continue
        hits = [f for f in songs if f not in chosen and key in _norm(os.path.splitext(f)[0])]
        if hits:
            chosen.append(min(hits, key=len))      # the closest (shortest) name
        else:
            missing.append(name)
    rest = [f for f in songs if f not in chosen]
    return [os.path.join(folder, f) for f in chosen + rest], missing


def decode_raw(src, dst):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn", "-ar", str(SR),
                    "-ac", "2", "-f", "s16le", dst], check=True)


def crossfade_stream(raws, xfade, total_samples, sink):
    """Feed the playlist to sink(int16 frames), cycling through the songs with
    equal-power crossfades between each pair (including last -> first) until
    total_samples frames have been produced."""
    import numpy as np
    n = int(xfade * SR)
    sent = 0
    tail = None
    i = 0

    def send(block):
        nonlocal sent
        if len(block) and sent < total_samples:
            sink(np.clip(block, -32768, 32767).astype(np.int16).tobytes())
            sent += len(block)

    while sent < total_samples:
        x = np.fromfile(raws[i % len(raws)], dtype=np.int16).reshape(-1, 2).astype(np.float32)
        i += 1
        if tail is not None:
            k = min(len(tail), len(x) // 3)               # overlap, shorter for tiny songs
            if k > 0:
                ang = (np.arange(k, dtype=np.float32) + 0.5) / k * (np.pi / 2)
                send(tail[:len(tail) - k])
                send(tail[len(tail) - k:] * np.cos(ang)[:, None] + x[:k] * np.sin(ang)[:, None])
                x = x[k:]
            else:
                send(tail)
        hold = min(n, len(x) // 2)                         # keep the tail for the next fade
        for a in range(0, len(x) - hold, SR * 30):         # send in 30 s blocks
            send(x[a:min(a + SR * 30, len(x) - hold)])
            if sent >= total_samples:
                return
        tail = x[len(x) - hold:]
    # (the end of the video cuts in here; the final fade-out is done by ffmpeg)


def fmt(sec):
    return f"{int(sec // 3600)}:{int(sec % 3600 // 60):02d}:{int(sec % 60):02d}"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Add music to a finished video without re-rendering it.")
    ap.add_argument("files", nargs=2, metavar="FILE",
                    help="the video, and a music file or folder of songs (any order)")
    ap.add_argument("--order", default="",
                    help='songs to play first, separated by ";" (folder of songs only)')
    ap.add_argument("--confirm", action="store_true", help="ask before starting")
    ap.add_argument("--out", default=None, help="output path (default: <video>_music.mp4)")
    ap.add_argument("--fade", type=float, default=5.0,
                    help="seconds of fade-out at the end (0 = none, default 5)")
    ap.add_argument("--crossfade", type=float, default=None,
                    help="seconds songs overlap (default 4 for a folder of songs; a single "
                         "file loops exactly, without crossfading, unless this is set)")
    args = ap.parse_args(argv)

    a, b = (os.path.abspath(f.strip().strip('"')) for f in args.files)
    for f in (a, b):
        if not os.path.exists(f):
            print(f"Not found: {f}")
            return 1
    a_is_audio = os.path.isdir(a) or os.path.splitext(a)[1].lower() in AUDIO_EXTS
    b_is_audio = os.path.isdir(b) or os.path.splitext(b)[1].lower() in AUDIO_EXTS
    if a_is_audio == b_is_audio:
        print("Give one video file and one music file or folder of songs.")
        return 1
    video, music = (b, a) if a_is_audio else (a, b)
    out = args.out or os.path.splitext(video)[0] + "_music.mp4"
    if os.path.abspath(out) == video:
        print("The output can't overwrite the original video.")
        return 1

    dur = duration(video)
    print(f"video   {video}  ({fmt(dur)})")
    if os.path.isdir(music):
        songs, missing = playlist(music, [n.strip() for n in args.order.split(";")])
        if not songs:
            print(f"No music files found in {music}")
            return 1
        lengths = [duration(f) for f in songs]
        total = sum(lengths)
        print(f"music   {len(songs)} songs from {music}, in this order:")
        for i, (f, ln) in enumerate(zip(songs, lengths), 1):
            print(f"        {i:2d}. {os.path.basename(f)}  ({fmt(ln)})")
        print(f"        playlist {fmt(total)}, plays {dur / total:.1f} times to fill the video")
        for name in missing:
            print(f"WARNING: no song matching \"{name}\" was found in the folder")
    else:
        songs = [music]
        print(f"music   {music}  ({duration(music):.0f} s, repeated to fill the video)")
    xfade = args.crossfade if args.crossfade is not None else (4.0 if os.path.isdir(music) else 0.0)
    if xfade > 0:
        print(f"        each song crossfades into the next over {xfade:g} s")
    print(f"output  {out}")
    if args.confirm:
        ans = input("\nStart? [Y/n]: ").strip().lower()
        if ans.startswith("n"):
            print("Cancelled.")
            return 1


    free = shutil.disk_usage(os.path.dirname(os.path.abspath(out)) or ".").free
    if free < os.path.getsize(video) * 1.1:
        print("Not enough free disk space for the new copy of the video.")
        return 1
    # faststart rewrites the file once more at the end: only when it fits
    faststart = ["-movflags", "+faststart"] if free > os.path.getsize(video) * 2.2 else []
    endfade = (["-af", f"afade=t=out:st={max(0.0, dur - args.fade):.3f}:d={args.fade}"]
               if args.fade > 0 else [])
    audio_out = ["-c:a", "aac", "-b:a", "192k", "-t", f"{dur:.3f}"]

    tmp = tempfile.mkdtemp(prefix="add_music_")
    try:
        if xfade > 0:
            # decode each song once, then stream the crossfaded playlist
            # straight into ffmpeg (no 3-hour temporary audio file)
            raws = []
            for i, f in enumerate(songs):
                raw = os.path.join(tmp, f"song_{i:03d}.raw")
                decode_raw(f, raw)
                raws.append(raw)
            cmd = (["ffmpeg", "-y", "-loglevel", "error", "-stats", "-i", video,
                    "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "pipe:0",
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy"]
                   + endfade + audio_out + faststart + [out])
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            try:
                crossfade_stream(raws, xfade, int((dur + 1.0) * SR), proc.stdin.write)
            except (BrokenPipeError, OSError):
                pass                       # ffmpeg reached the video's end and stopped reading
            finally:
                try:
                    proc.stdin.close()
                except OSError:
                    pass
            if proc.wait() != 0:
                raise RuntimeError("ffmpeg failed - see the message above")
        else:
            # exact repeats: decode once and loop the decoded audio gaplessly
            parts = []
            for i, f in enumerate(songs):
                part = os.path.join(tmp, f"song_{i:03d}.wav")
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f, "-vn",
                                "-ar", str(SR), "-ac", "2", "-c:a", "pcm_s16le", part], check=True)
                parts.append(part)
            wav = os.path.join(tmp, "music.wav")
            if len(parts) == 1:
                os.replace(parts[0], wav)
            else:
                listfile = os.path.join(tmp, "songs.txt")
                with open(listfile, "w") as lf:
                    for part in parts:              # names only: relative to the list
                        lf.write(f"file '{os.path.basename(part)}'\n")
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                                "-i", listfile, "-c", "copy", wav], check=True)
            cmd = (["ffmpeg", "-y", "-loglevel", "error", "-stats", "-i", video,
                    "-stream_loop", "-1", "-i", wav, "-map", "0:v", "-map", "1:a", "-c:v", "copy"]
                   + endfade + audio_out + ["-shortest"] + faststart + [out])
            subprocess.run(cmd, check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\ndone    {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
