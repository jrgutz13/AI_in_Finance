#!/usr/bin/env python3
"""Enhance Clips: string a folder of short clips into one long video, following
a plan you write - which clips, in what order, which in slow motion, which
part of each - with crossfades and music.

    python3 enhance_clips.py "C:\\Users\\me\\Videos\\clips"

The first run writes a starter plan, clips_plan.txt, inside the clips folder,
listing every clip. Edit it (see the notes at its top), then run again:

    length: 3h            the clip sequence repeats until the video is this long
    resolution: 1080p     every clip is upscaled to this (720p/1080p/1440p/4k)
    crossfade: 2          seconds each clip blends into the next
    music: C:\\...\\songs    a music file or a folder of songs (optional)
    music order: Song A; Song B

    ghost_forest.mp4  slow 2         half speed, smooth AI slow motion
    candles.mp4       trim 2-8       only seconds 2-8 of the clip
    moon.mp4          slow 1.5  repeat 2

Slow motion and upscaling use free AI tools on the graphics card - RIFE
(frame interpolation) and Real-ESRGAN (upscaling), downloaded on first use
into tools\\ - and fall back to ffmpeg's methods if they're unavailable.
Each clip is processed once and reused every time the sequence repeats, and
everything is cached in a work folder, so after a crash, or after changing
the order, the crossfade or the music, a re-run only redoes what changed."""

import argparse
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpg", ".mpeg", ".wmv"}
PLAN_NAME = "clips_plan.txt"
RESOLUTIONS = {"720p": (1280, 720), "1080p": (1920, 1080), "1440p": (2560, 1440),
               "4k": (3840, 2160), "2160p": (3840, 2160)}

TOOLS = {
    "rife": {
        "exe": "rife-ncnn-vulkan",
        "urls": {"Windows": "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/"
                            "rife-ncnn-vulkan-20221029-windows.zip",
                 "Linux": "https://github.com/nihui/rife-ncnn-vulkan/releases/download/20221029/"
                          "rife-ncnn-vulkan-20221029-ubuntu.zip"},
        "what": "RIFE (AI slow motion)",
    },
    "upscaler": {
        "exe": "realesrgan-ncnn-vulkan",
        "urls": {"Windows": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
                            "realesrgan-ncnn-vulkan-20220424-windows.zip",
                 "Linux": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
                          "realesrgan-ncnn-vulkan-20220424-ubuntu.zip"},
        "what": "Real-ESRGAN (AI upscaling)",
    },
}


# ---------------------------------------------------------------------------
# small helpers

def fmt(sec):
    sec = max(0.0, sec)
    return f"{int(sec // 3600)}:{int(sec % 3600 // 60):02d}:{int(sec % 60):02d}"


def parse_duration(text):
    text = str(text).strip().lower()
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return float(text)
    if ":" in text:
        parts = [float(p) for p in text.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0.0)
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    found = re.findall(r"(\d+(?:\.\d+)?)\s*(h|hr|hrs|hours?|m|min|mins|minutes?|s|sec|secs|seconds?)\b",
                       text)
    if not found:
        raise ValueError(f"can't read the length '{text}' (examples: 3h, 90m, 1:30:00)")
    return sum(float(v) * {"h": 3600, "m": 60, "s": 1}[u[0]] for v, u in found)


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:format=duration", "-of", "json", path],
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"can't read {os.path.basename(path)}: {out.stderr.strip()[:200]}")
    d = json.loads(out.stdout)
    st = d["streams"][0]
    num, den = (st.get("r_frame_rate") or "24/1").split("/")
    return {"w": int(st["width"]), "h": int(st["height"]),
            "fps": float(num) / float(den or 1), "dur": float(d["format"]["duration"])}


def run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        tail = "\n".join((r.stderr or r.stdout or "").strip().splitlines()[-6:])
        raise RuntimeError(f"{what} failed:\n{tail}")
    return r


def _norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def nvenc_works():
    try:
        r = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                            "color=black:s=1920x1080:d=0.2", "-c:v", "h264_nvenc", "-f", "null", "-"],
                           capture_output=True, timeout=60)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# ---------------------------------------------------------------------------
# the plan file

def write_starter(folder, plan_path, clips):
    lines = [
        f"# Enhance Clips plan for: {folder}",
        "# Lines starting with # are notes. Edit this file, save it, then run",
        "# enhance_clips.bat again.",
        "#",
        "# ---- the whole video ----",
        "length: 3h",
        "# (the clips below play in order, and the whole sequence repeats until the",
        "#  video is this long; delete the line to play the sequence just once)",
        "resolution: 1080p",
        "# (720p, 1080p, 1440p or 4k - every clip is upscaled to this)",
        "crossfade: 2",
        "# (seconds each clip blends into the next)",
        "# music: C:\\path\\to\\a song or a folder of songs",
        "# music order: First Song; Second Song",
        "# (remove the # at the start of those two lines to add music; songs",
        "#  crossfade into each other and the playlist repeats for the whole video)",
        "#",
        "# ---- the clips, in the order they play ----",
        "# After a clip's name you can add:",
        "#   slow 2      half speed, smooth AI slow motion (slow 1.5, slow 3 ... work too;",
        "#               a bigger number is slower: slow 3 = one-third speed)",
        "#   trim 2-8    use only seconds 2 to 8 of the clip",
        "#   repeat 2    play it twice in a row",
        "# for example:   ghost forest.mp4   slow 2   trim 1-9",
        "# Delete a line to leave that clip out. Move lines to change the order.",
        "",
    ] + clips
    with open(plan_path, "w", encoding="utf-8", newline="\r\n" if os.name == "nt" else "\n") as f:
        f.write("\n".join(lines) + "\n")


OPTION_RE = re.compile(r"\s+(slow\s+[\d.]+x?|trim\s+[\d.:]+\s*-\s*[\d.:]+|repeat\s+\d+x?)\s*$", re.I)
HEADER_KEYS = {"length", "resolution", "crossfade", "fps", "music", "musicorder",
               "musiccrossfade", "output"}


def parse_plan(path):
    settings = {"length": None, "resolution": "1080p", "crossfade": 2.0, "fps": 24,
                "music": None, "musicorder": "", "musiccrossfade": 4.0, "output": None}
    entries, problems = [], []
    with open(path, encoding="utf-8-sig") as f:
        lines = f.read().splitlines()
    for n, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z][A-Za-z ]*?)\s*:\s*(.*)$", line)
        if m and _norm(m.group(1)) in HEADER_KEYS:
            key, value = _norm(m.group(1)), m.group(2).strip()
            value = re.sub(r"\s+#.*$", "", value)
            value = re.sub(r"\s*\([^)]*\)\s*$", "", value).strip().strip('"')
            try:
                if key == "length":
                    settings[key] = parse_duration(value) if value else None
                elif key in ("crossfade", "musiccrossfade"):
                    settings[key] = float(re.sub(r"[^\d.]", "", value) or 0)
                elif key == "fps":
                    settings[key] = int(float(value))
                else:
                    settings[key] = value or None
            except ValueError as e:
                problems.append(f"line {n}: {e}")
            continue
        # a clip line: name, then options
        line = re.sub(r"\s+#.*$", "", line)
        opts = {"slow": 1.0, "trim": None, "repeat": 1}
        while True:
            m = OPTION_RE.search(line)
            if not m:
                break
            word = m.group(1).lower()
            nums = re.findall(r"[\d.:]+", word)
            try:
                if word.startswith("slow"):
                    opts["slow"] = float(nums[0])
                elif word.startswith("trim"):
                    opts["trim"] = (parse_duration(nums[0]), parse_duration(nums[1]))
                else:
                    opts["repeat"] = int(nums[0])
            except (ValueError, IndexError):
                problems.append(f"line {n}: can't read '{m.group(1)}'")
            line = line[:m.start()]
        name = line.strip().strip('"')
        if not name:
            continue
        if opts["slow"] < 1.0 or opts["slow"] > 8.0:
            problems.append(f"line {n}: slow must be between 1 and 8 ({name})")
            opts["slow"] = min(max(opts["slow"], 1.0), 8.0)
        entries.append({"line": n, "name": name, **opts})
    res = str(settings["resolution"]).lower().replace(" ", "")
    if res in RESOLUTIONS:
        settings["size"] = RESOLUTIONS[res]
    elif re.fullmatch(r"\d+x\d+", res):
        w, h = (int(v) for v in res.split("x"))
        settings["size"] = (w // 2 * 2, h // 2 * 2)
    else:
        problems.append(f"resolution '{settings['resolution']}' - use 720p, 1080p, 1440p or 4k")
        settings["size"] = RESOLUTIONS["1080p"]
    return settings, entries, problems


def match_clip(name, files):
    """The clip file a plan line means: exact name, then name without
    extension, then a unique partial match (ignoring case and punctuation)."""
    low = name.lower()
    for f in files:
        if f.lower() == low:
            return f, None
    stems = [f for f in files if os.path.splitext(f)[0].lower() == os.path.splitext(low)[0]]
    if len(stems) == 1:
        return stems[0], None
    key = _norm(os.path.splitext(name)[0])
    hits = [f for f in files if key and key in _norm(os.path.splitext(f)[0])]
    if len(hits) == 1:
        return hits[0], None
    if len(hits) > 1:
        return None, f"matches several clips ({', '.join(hits[:4])})"
    return None, "no clip with that name in the folder"


# ---------------------------------------------------------------------------
# AI tools

def find_tool(tools_dir, key):
    exe = TOOLS[key]["exe"] + (".exe" if os.name == "nt" else "")
    hits = glob.glob(os.path.join(tools_dir, key, "**", exe), recursive=True)
    return hits[0] if hits else None


def download_tool(tools_dir, key):
    url = TOOLS[key]["urls"].get(platform.system())
    if not url:
        return None
    dest = os.path.join(tools_dir, key)
    os.makedirs(dest, exist_ok=True)
    zpath = os.path.join(dest, "download.zip")
    print(f"  downloading {TOOLS[key]['what']} ...")
    with urllib.request.urlopen(url, timeout=120) as r, open(zpath + ".part", "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    os.replace(zpath + ".part", zpath)
    with zipfile.ZipFile(zpath) as z:
        z.extractall(dest)
    os.remove(zpath)
    exe = find_tool(tools_dir, key)
    if exe and os.name != "nt":
        os.chmod(exe, 0o755)
    return exe


def get_tools(tools_dir, mode, ask):
    """{key: exe or None}. mode: auto (download if missing) or off."""
    found = {k: (find_tool(tools_dir, k) if mode != "off" else None) for k in TOOLS}
    missing = [k for k, v in found.items() if not v]
    if mode == "off" or not missing:
        return found
    what = " and ".join(TOOLS[k]["what"] for k in missing)
    if ask:
        ans = input(f"\nDownload the free {what} tools (about 500 MB, one time only)? [Y/n]: ")
        if ans.strip().lower().startswith("n"):
            return found
    for k in missing:
        try:
            found[k] = download_tool(tools_dir, k)
        except Exception as e:                   # network, disk, zip - fall back
            print(f"  could not download {TOOLS[k]['what']}: {e}")
    return found


# ---------------------------------------------------------------------------
# preparing one clip: trim, slow motion, upscale, normalize

FILL = "scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},setsar=1"


def prep_ffmpeg(src, start, length, slow, S, out):
    W, H = S["size"]
    fps = S["fps"]
    n = int(round(length * slow * fps))
    chain = ""
    if slow > 1.0:
        chain = (f"setpts={slow}*PTS,minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:"
                 f"me_mode=bidir:vsbmc=1,")
    chain += f"fps={fps}," + FILL.format(W=W, H=H) + ",format=yuv420p,tpad=stop_mode=clone:stop_duration=2"
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.4f}", "-t", f"{length + 0.5:.4f}",
         "-i", src, "-an", "-vf", chain, "-frames:v", str(n), "-r", str(fps),
         "-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p", out],
        "standard slow motion / scaling")
    return n


def prep_ai(src, start, length, slow, S, out, tools, tmp, info):
    """RIFE slow motion at the clip's own size, then Real-ESRGAN upscaling,
    then a final lanczos fit to the output size."""
    W, H = S["size"]
    fps = S["fps"]
    n = int(round(length * slow * fps))
    a, b, c = (os.path.join(tmp, d) for d in ("a", "b", "c"))
    for d in (a, b, c):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    frames = a
    if slow > 1.0 and tools.get("rife"):
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.4f}", "-t", f"{length:.4f}",
             "-i", src, "-an", os.path.join(a, "%08d.png")], "extracting frames")
        if len(os.listdir(a)) < 2:
            raise RuntimeError("clip too short to slow down")
        rife = tools["rife"]
        model = os.path.join(os.path.dirname(rife), "rife-v4.6")
        run([rife, "-i", a, "-o", b, "-m", model, "-n", str(n), "-f", "%08d.png"],
            "AI slow motion (RIFE)")
        if len(os.listdir(b)) < n * 0.9:
            raise RuntimeError(f"RIFE made {len(os.listdir(b))} of {n} frames")
        frames, rate = b, fps
    else:
        # no RIFE: frames at the output rate (slowed with ffmpeg's method if asked)
        chain = (f"setpts={slow}*PTS,minterpolate=fps={fps}:mi_mode=mci:mc_mode=aobmc:"
                 f"me_mode=bidir:vsbmc=1," if slow > 1.0 else "") + f"fps={fps}"
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.4f}", "-t", f"{length + 0.5:.4f}",
             "-i", src, "-an", "-vf", chain, "-frames:v", str(n), os.path.join(a, "%08d.png")],
            "extracting frames")
        rate = fps
    if info["h"] < H * 0.95 and tools.get("upscaler"):
        esr = tools["upscaler"]
        scale = 2 if info["h"] * 2 >= H * 0.95 else (3 if info["h"] * 3 >= H * 0.95 else 4)
        run([esr, "-i", frames, "-o", c, "-n", "realesr-animevideov3", "-s", str(scale),
             "-m", os.path.join(os.path.dirname(esr), "models"), "-f", "jpg"],
            "AI upscaling (Real-ESRGAN)")
        if len(os.listdir(c)) < len(os.listdir(frames)):
            raise RuntimeError("Real-ESRGAN did not upscale every frame")
        frames, ext = c, "jpg"
    else:
        ext = "png"
    run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(rate), "-i",
         os.path.join(frames, f"%08d.{ext}"), "-vf",
         FILL.format(W=W, H=H) + ",format=yuv420p,tpad=stop_mode=clone:stop_duration=2",
         "-frames:v", str(n), "-r", str(fps), "-c:v", "libx264", "-crf", "14", "-preset", "medium",
         "-pix_fmt", "yuv420p", out], "encoding the prepared clip")
    for d in (a, b, c):
        shutil.rmtree(d, ignore_errors=True)
    return n


# ---------------------------------------------------------------------------

def encode_args(S):
    if S["codec"] == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-cq", "19", "-preset", "p5", "-rc", "vbr", "-g", str(S["fps"] * 2)]
    return ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-g", str(S["fps"] * 2)]


def make_piece(kind, S, out, a, b=None):
    """kind: head / body / tail / fade. a, b: (prepared file, first frame, frame count)."""
    fps, X = S["fps"], S["xf"]
    pa, fa, na = a
    if kind == "fade":
        pb, fb, nb = b
        flt = (f"[0:v]trim=start_frame={fa}:end_frame={fa + na},setpts=PTS-STARTPTS[x];"
               f"[1:v]trim=start_frame={fb}:end_frame={fb + nb},setpts=PTS-STARTPTS[y];"
               f"[x][y]xfade=transition=fade:duration={X / fps:.6f}:offset=0,format=yuv420p[v]")
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", pa, "-i", pb, "-filter_complex", flt,
               "-map", "[v]"]
        frames = nb
    else:
        flt = f"trim=start_frame={fa}:end_frame={fa + na},setpts=PTS-STARTPTS"
        if kind == "head":
            flt += f",fade=t=in:st=0:d={min(1.5, na / fps):.3f}"
        elif kind == "tail":
            flt += f",fade=t=out:st=0:d={na / fps:.3f}"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", pa, "-vf", flt + ",format=yuv420p"]
        frames = na
    run(cmd + ["-frames:v", str(frames), "-r", str(fps), "-an"] + encode_args(S)
        + ["-pix_fmt", "yuv420p", "-f", "mpegts", out + ".part"], f"encoding a {kind}")
    os.replace(out + ".part", out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="String clips into a long video from a plan.")
    ap.add_argument("folder", help="the folder of clips")
    ap.add_argument("--plan", default=None, help=f"plan file (default: {PLAN_NAME} in the folder)")
    ap.add_argument("--out", default=None, help="output video (default: output\\<folder>.mp4)")
    ap.add_argument("--ai", choices=["auto", "off"], default="auto",
                    help="auto: AI slow motion/upscaling on the graphics card, downloading the "
                         "tools on first use; off: ffmpeg's methods only")
    ap.add_argument("--tools-dir", default=os.path.join(HERE, "tools"))
    ap.add_argument("--codec", choices=["auto", "libx264", "h264_nvenc"], default="auto")
    ap.add_argument("--confirm", action="store_true", help="show the plan and ask before starting")
    ap.add_argument("--no-flash-check", action="store_true")
    args = ap.parse_args(argv)

    folder = os.path.abspath(args.folder.strip().strip('"'))
    if not os.path.isdir(folder):
        print(f"Folder not found: {folder}")
        return 1
    files = sorted((f for f in os.listdir(folder)
                    if os.path.splitext(f)[1].lower() in VIDEO_EXTS
                    and os.path.isfile(os.path.join(folder, f))), key=str.lower)
    plan_path = os.path.abspath(args.plan) if args.plan else os.path.join(folder, PLAN_NAME)
    if not os.path.exists(plan_path):
        if not files:
            print(f"No video clips found in {folder}")
            return 1
        write_starter(folder, plan_path, files)
        print(f"Wrote a starter plan listing all {len(files)} clips:\n  {plan_path}")
        print("Edit it (order, slow motion, trims, music), save, and run this again.")
        return 3                                    # tells the .bat to open the plan

    S, entries, problems = parse_plan(plan_path)
    S["xf"] = int(round(S["crossfade"] * S["fps"]))
    W, H = S["size"]
    fps = S["fps"]

    # resolve clip names, read each clip, work out its length
    clips = []
    for e in entries:
        f, err = match_clip(e["name"], files)
        if err:
            problems.append(f"line {e['line']}: \"{e['name']}\" - {err}")
            continue
        path = os.path.join(folder, f)
        try:
            info = probe(path)
        except RuntimeError as ex:
            problems.append(f"line {e['line']}: {ex}")
            continue
        start, end = e["trim"] if e["trim"] else (0.0, info["dur"])
        end = min(end, info["dur"])
        if end - start < 0.5:
            problems.append(f"line {e['line']}: trim {start:g}-{end:g} is outside {f} "
                            f"({info['dur']:.1f} s long)")
            continue
        n = int(round((end - start) * e["slow"] * fps))
        if n < 2 * S["xf"] + 2:
            problems.append(f"line {e['line']}: {f} is too short for a {S['crossfade']:g} s "
                            f"crossfade (it lasts {n / fps:.1f} s)")
            continue
        for _ in range(max(1, e["repeat"])):
            clips.append({"file": f, "path": path, "info": info, "start": start,
                          "len": end - start, "slow": e["slow"], "frames": n})
    if not clips:
        problems.append("no usable clips in the plan")

    # the timeline: one pass, repeated until the requested length; it always
    # ends on a whole clip, which fades out
    X = S["xf"]
    one_pass = sum(c["frames"] for c in clips) - X * max(0, len(clips) - 1)
    target = int(round(S["length"] * fps)) if S["length"] else one_pass
    order, total = [], 0
    while clips and (not order or total < target):
        i = len(order) % len(clips)
        total += clips[i]["frames"] - (X if order else 0)
        order.append(i)

    # music
    music_files, music_missing = [], []
    if S["music"]:
        from add_music import playlist
        mpath = os.path.abspath(os.path.expandvars(S["music"]))
        if os.path.isdir(mpath):
            music_files, music_missing = playlist(mpath, [x.strip() for x in S["musicorder"].split(";")])
        elif os.path.isfile(mpath):
            music_files = [mpath]
        if not music_files:
            problems.append(f"music: nothing found at {S['music']}")

    # ---- summary ----
    print(f"plan       {plan_path}")
    print(f"video      {W}x{H} @ {fps} fps, crossfade {S['crossfade']:g} s")
    print(f"clips      {len(clips)} in the sequence:")
    for k, c in enumerate(clips, 1):
        part = f"{c['start']:g}-{c['start'] + c['len']:g} s" if (c["start"] > 0 or c["len"] < c["info"]["dur"] - 0.05) else "all"
        sl = f"slow {c['slow']:g}" if c["slow"] > 1 else "normal speed"
        up = f"from {c['info']['h']}p" if c["info"]["h"] < H * 0.95 else ""
        print(f"  {k:3d}. {c['file'][:42]:42s} {part:>11s}  {sl:12s} -> {c['frames'] / fps:5.1f} s  {up}")
    if clips:
        print(f"one pass   {fmt(one_pass / fps)}" + (f"; repeats {len(order) / len(clips):.1f} times"
                                                      if len(order) > len(clips) else ""))
        print(f"length     {fmt(total / fps)}" + (f" (asked for {fmt(S['length'])}, rounded up to end on "
                                                   "a whole clip)" if S["length"] else ""))
    if music_files:
        print(f"music      {len(music_files)} song(s), crossfading {S['musiccrossfade']:g} s, "
              "repeating for the whole video")
        for m in music_files[:12]:
            print(f"           - {os.path.basename(m)}")
        for name in music_missing:
            print(f"WARNING: no song matching \"{name}\"")
    for p in problems:
        print(f"PROBLEM: {p}")
    if not clips:
        return 1
    out = os.path.abspath(args.out or S["output"] or os.path.join(HERE, "output",
                                                                    os.path.basename(folder) + ".mp4"))
    print(f"output     {out}")

    tools = get_tools(args.tools_dir, args.ai, args.confirm)
    ai_desc = ", ".join(TOOLS[k]["what"] for k, v in tools.items() if v) or "none (ffmpeg methods)"
    print(f"AI tools   {ai_desc}")
    if args.confirm:
        q = "Some lines have problems (see above) - continue without them?" if problems else "Start?"
        ans = input(f"\n{q} [{'y/N' if problems else 'Y/n'}]: ").strip().lower()
        if (problems and not ans.startswith("y")) or (not problems and ans.startswith("n")):
            print("Stopped. Fix the plan and run again.")
            return 1
    elif problems:
        print("Continuing without the lines above.")

    S["codec"] = ("h264_nvenc" if nvenc_works() else "libx264") if args.codec == "auto" else args.codec
    work = os.path.splitext(out)[0] + "_work"
    os.makedirs(work, exist_ok=True)
    t0 = time.time()

    # ---- 1. prepare each distinct clip once ----
    preps, fallbacks = {}, []
    uniq = []
    for c in clips:
        st = os.stat(c["path"])
        key = hashlib.sha1(json.dumps([c["path"], st.st_size, int(st.st_mtime), round(c["start"], 3),
                                       round(c["len"], 3), c["slow"], W, H, fps]).encode()).hexdigest()[:16]
        c["key"] = key
        if key not in preps:
            preps[key] = None
            uniq.append(c)
    print(f"\npreparing {len(uniq)} clip(s)" + (" (cached ones are reused)" if uniq else ""))
    for k, c in enumerate(uniq, 1):
        path = os.path.join(work, f"prep_{c['key']}.mp4")
        preps[c["key"]] = path
        if os.path.exists(path):
            continue
        label = f"  [{k}/{len(uniq)}] {c['file']}"
        needs_ai = (c["slow"] > 1 and tools.get("rife")) or (c["info"]["h"] < H * 0.95 and tools.get("upscaler"))
        print(label + (" - AI" if needs_ai else ""), end="", flush=True)
        t1 = time.time()
        tmp = os.path.join(work, "frames")
        part = path[:-4] + ".part.mp4"
        try:
            if needs_ai:
                prep_ai(c["path"], c["start"], c["len"], c["slow"], S, part, tools, tmp, c["info"])
            else:
                prep_ffmpeg(c["path"], c["start"], c["len"], c["slow"], S, part)
        except RuntimeError as e:
            if not needs_ai:
                raise
            print(f"\n    AI step failed, using the standard method instead: {str(e).splitlines()[0]}")
            fallbacks.append(c["file"])
            prep_ffmpeg(c["path"], c["start"], c["len"], c["slow"], S, part)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        os.replace(part, path)
        print(f"  ({time.time() - t1:.0f} s)")

    # ---- 2. flash check of the prepared clips ----
    if not args.no_flash_check:
        import flash_check
        flagged = []
        for c in uniq:
            areas, _ = flash_check.analyze(preps[c["key"]], fps)
            if len(areas) and areas.max() >= 0.25:
                flagged.append(c["file"])
        if flagged:
            print("\nWARNING - rapid flashing in: " + ", ".join(sorted(set(flagged))))
            print("  (consider removing these clips or slowing them down)")

    # ---- 3. pieces: head, bodies, crossfades, tail (each encoded once) ----
    plan_pieces = []
    for j, i in enumerate(order):
        c = clips[i]
        n = c["frames"]
        p = preps[c["key"]]
        if j == 0:
            plan_pieces.append(("head", (p, 0, X), None))
        last = j == len(order) - 1
        plan_pieces.append(("body", (p, X, n - 2 * X), None))
        if last:
            plan_pieces.append(("tail", (p, n - X, X), None))
        else:
            nxt = clips[order[j + 1]]
            plan_pieces.append(("fade", (p, n - X, X), (preps[nxt["key"]], 0, X)))
    names = []
    todo = {}
    for kind, a, b in plan_pieces:
        key = hashlib.sha1(json.dumps([kind, os.path.basename(a[0]), a[1:], b and os.path.basename(b[0]),
                                       b and b[1:], S["codec"]]).encode()).hexdigest()[:16]
        name = f"{kind}_{key}.ts"
        names.append(name)
        if not os.path.exists(os.path.join(work, name)):
            todo[name] = (kind, a, b)
    print(f"\nencoding {len(todo)} piece(s) ({len(names)} in the timeline)")
    for k, (name, (kind, a, b)) in enumerate(todo.items(), 1):
        sys.stdout.write(f"\r  {k}/{len(todo)}   ")
        sys.stdout.flush()
        make_piece(kind, S, os.path.join(work, name), a, b)
    print()

    # ---- 4. join, with music ----
    listfile = os.path.join(work, "timeline.txt")
    with open(listfile, "w") as f:
        for name in names:
            f.write(f"file '{name}'\n")
    dur = total / fps
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-stats", "-f", "concat", "-safe", "0", "-i", listfile]
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    free = shutil.disk_usage(os.path.dirname(out)).free
    final_size = sum(os.path.getsize(os.path.join(work, n)) for n in names)   # repeats included
    if free < final_size * 1.05:
        print(f"Not enough free disk space: the video needs about {final_size / 1e9:.1f} GB.")
        return 1
    # faststart rewrites the file once more at the end: only when it fits
    faststart = ["-movflags", "+faststart"] if free > final_size * 2.2 else []
    print("joining" + (" and adding music" if music_files else ""))
    if music_files:
        from add_music import SR, crossfade_stream, decode_raw
        raws = []
        for m_i, m in enumerate(music_files):
            raw = os.path.join(work, f"song_{m_i:03d}.raw")
            decode_raw(m, raw)
            raws.append(raw)
        xf = S["musiccrossfade"] if len(music_files) > 1 else 0.0
        cmd += ["-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "pipe:0", "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-af", f"afade=t=out:st={max(0.0, dur - 5):.3f}:d=5",
                "-c:a", "aac", "-b:a", "192k", "-t", f"{dur:.3f}"] + faststart + [out]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        try:
            if xf > 0:
                crossfade_stream(raws, xf, int((dur + 1) * SR), proc.stdin.write)
            else:                                    # one song: exact repeats
                import numpy as np
                x = np.fromfile(raws[0], dtype=np.int16)
                need = int((dur + 1) * SR) * 2
                while need > 0:
                    proc.stdin.write(x[:need].tobytes())
                    need -= len(x)
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                proc.stdin.close()
            except OSError:
                pass
        if proc.wait() != 0:
            raise RuntimeError("joining failed - see the message above")
        for raw in raws:
            os.remove(raw)
    else:
        subprocess.run(cmd + ["-map", "0:v", "-c:v", "copy", "-t", f"{dur:.3f}"] + faststart + [out],
                       check=True)

    print(f"\ndone       {out}  ({fmt(dur)}, took {fmt(time.time() - t0)})")
    if fallbacks:
        print(f"note       standard (non-AI) method used for: {', '.join(sorted(set(fallbacks)))}")
    print(f"work       {work}")
    print("           (keeps the prepared clips: re-running after changing the order, crossfade or")
    print("            music is quick. Delete this folder when you're happy with the video.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
