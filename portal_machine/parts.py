"""Crash-safe rendering for long videos.

Long renders are split into ~10-minute parts, each written as a finished
MPEG-TS segment. A manifest.json in the parts folder records the settings
and which parts are done. If the machine shuts off mid-render, running with
--resume (or answering the prompt in make_video.bat) re-renders only the
part that was interrupted and everything after it — hours of finished work
survive. When all parts exist they are joined (stream copy, no quality
loss), the music is muxed in, and the parts folder is deleted.

Everything is deterministic from the seed, so a resumed render is
bit-identical to what an uninterrupted one would have produced."""

import glob
import json
import os
import shutil
import subprocess

from .renderer import decode_audio, encode, looped_audio_args

MANIFEST = "manifest.json"


def parts_dir_for(out_path):
    return out_path.rsplit(".", 1)[0] + "_parts"


def plan_parts(duration, part_length):
    """List of (start, end) covering [0, duration)."""
    spans = []
    t = 0.0
    while t < duration:
        spans.append((t, min(t + part_length, duration)))
        t += part_length
    return spans


def write_manifest(pdir, settings, done):
    tmp = os.path.join(pdir, MANIFEST + ".tmp")
    with open(tmp, "w") as f:
        json.dump({"settings": settings, "done": sorted(done)}, f, indent=1)
    os.replace(tmp, os.path.join(pdir, MANIFEST))


def load_manifest(pdir):
    with open(os.path.join(pdir, MANIFEST)) as f:
        data = json.load(f)
    return data["settings"], set(data["done"])


def find_unfinished(output_dir="output"):
    """Most recently touched parts folder with a manifest, or None."""
    candidates = glob.glob(os.path.join(output_dir, "*_parts", MANIFEST))
    if not candidates:
        return None
    return os.path.dirname(max(candidates, key=os.path.getmtime))


def render_parts(renderer, frame_fn, settings, done_cb=None):
    """Renders all missing parts. Returns the parts dir."""
    out = settings["out"]
    pdir = parts_dir_for(out)
    os.makedirs(pdir, exist_ok=True)
    spans = plan_parts(settings["duration"], settings["part_length"])
    try:
        _, done = load_manifest(pdir)
    except FileNotFoundError:
        done = set()
    write_manifest(pdir, settings, done)

    for i, (t0, t1) in enumerate(spans):
        if i in done:
            continue
        part_path = os.path.join(pdir, f"part_{i:05d}.ts")
        encode(renderer, frame_fn, t1 - t0, settings["fps"], part_path,
               codec=settings["codec"], crf=settings["crf"],
               preset=settings["preset"], maxrate_mbps=settings["maxrate"],
               t_start=t0, container="ts",
               label=f"part {i + 1}/{len(spans)}  ")
        done.add(i)
        write_manifest(pdir, settings, done)
        if done_cb:
            done_cb(len(done), len(spans))
    return pdir


def join_parts(settings):
    """Concatenates finished parts into the final mp4, muxes audio, and
    removes the parts folder."""
    out = settings["out"]
    pdir = parts_dir_for(out)
    spans = plan_parts(settings["duration"], settings["part_length"])
    listfile = os.path.join(pdir, "list.txt")
    with open(listfile, "w") as f:
        for i in range(len(spans)):
            f.write(f"file 'part_{i:05d}.ts'\n")

    audio = settings.get("audio")
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "concat", "-safe", "0", "-i", listfile]
    a_in, a_out = [], []
    if audio:
        wav = decode_audio(audio, os.path.join(pdir, "music.wav"))
        a_in, a_out = looped_audio_args(wav, settings["duration"])
    cmd += a_in + ["-map", "0:v"] + a_out
    cmd += ["-c:v", "copy"]
    # faststart makes ffmpeg rewrite the whole file through a temp copy at
    # the end — that needs ANOTHER final-file-sized chunk of disk on top of
    # the parts + the final file. Only ask for it when that clearly fits
    # (it only helps direct progressive playback; YouTube re-encodes anyway).
    parts_bytes = sum(
        os.path.getsize(os.path.join(pdir, f"part_{i:05d}.ts"))
        for i in range(len(spans)))
    free = shutil.disk_usage(os.path.dirname(os.path.abspath(out)) or ".").free
    if free > parts_bytes * 2.4:
        cmd += ["-movflags", "+faststart"]
    else:
        print("(skipping faststart remux to stay inside free disk space)")
    cmd += ["-t", f"{settings['duration']:.3f}", out]
    subprocess.run(cmd, check=True)
    shutil.rmtree(pdir, ignore_errors=True)
