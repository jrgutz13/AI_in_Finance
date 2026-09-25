"""Talking to Mandelbulber2: reading/writing its settings files, rendering
keyframe animations, and measuring distances inside a fractal scene.

Mandelbulber's .fract files are plain text with quirks handled here:
  - the header must include "# only modified parameters", or the file is
    read as a complete settings file and anything missing is reset —
    silently turning any scene into the default one
  - decimals use a comma ("0,5"), whatever the computer's locale
  - colors are three 16-bit hex channels ("ff00 0b00 2f00")
  - animation is a [keyframes] table: a header row naming the animated
    parameters (main_camera_x, main_basic_fog_color_R, ...) and one row per
    keyframe. With frames_per_keyframe = 1 every keyframe IS a frame, so our
    code decides the camera path exactly (no spline interpolation by
    Mandelbulber) — which is what lets separately rendered chunks join
    seamlessly. N frames need N+1 keyframes; --end is exclusive.
Command-line overrides (-O) are NOT used: they proved unreliable for camera
and color values, so every change is written into the settings file.
"""

import glob
import math
import os
import shutil
import subprocess

import numpy as np

HEADER = ["# Mandelbulber settings file", "# version 2.20", "# only modified parameters"]
FRACTAL_SECTIONS = ("fractal_1", "fractal_2", "fractal_3", "fractal_4")


# ---------------------------------------------------------------------------
# value formatting
# ---------------------------------------------------------------------------

def fnum(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    return f"{float(v):.15g}".replace(".", ",")


def vec(v):
    return " ".join(fnum(float(x)) for x in v)


def rgb16(c):
    """(r, g, b) in 0..1 -> Mandelbulber's '#### #### ####' 16-bit hex."""
    return " ".join(f"{max(0, min(65535, int(round(x * 65535)))):04x}" for x in c)


def parse_rgb16(s):
    return [int(p, 16) / 65535.0 for p in s.split()]


def gradient(stops):
    """[(pos 0..1, (r, g, b) 0..1), ...] -> Mandelbulber gradient string."""
    out = []
    for pos, c in stops:
        hexc = "".join(f"{max(0, min(255, int(round(x * 255)))):02x}" for x in c)
        out.append(f"{int(round(pos * 10000))} {hexc}")
    return " ".join(out)


def num3(s):
    return np.array([float(x.replace(",", ".")) for x in s.split()])


def to_str(v):
    if isinstance(v, str):
        return v
    if isinstance(v, (tuple, list, np.ndarray)):
        return vec(v)
    return fnum(v)


# ---------------------------------------------------------------------------
# scenes
# ---------------------------------------------------------------------------

class Scene:
    """A Mandelbulber scene: ordered {param: raw string} per section."""

    def __init__(self, main=None, fractals=None):
        self.main = dict(main or {})
        self.fractals = {s: dict((fractals or {}).get(s, {})) for s in FRACTAL_SECTIONS}

    @classmethod
    def load(cls, path):
        sections, cur = {}, None
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\r\n")
                if line.startswith("["):
                    cur = line.strip("[]")
                    sections.setdefault(cur, {})
                    continue
                if cur is None or cur == "keyframes" or not line.strip() or line.startswith("#"):
                    continue
                key, _, val = line.rstrip(";").partition(" ")
                sections[cur][key] = val
        return cls(sections.get("main_parameters", {}),
                   {s: sections.get(s, {}) for s in FRACTAL_SECTIONS})

    def copy(self):
        return Scene(self.main, self.fractals)

    def set(self, **params):
        for k, v in params.items():
            self.main[k] = to_str(v)
        return self

    def write(self, path, keyframes=None):
        """keyframes: list of {column: number} dicts sharing the same keys."""
        lines = HEADER + ["[main_parameters]"]
        lines += [f"{k} {v};" for k, v in self.main.items()]
        for s in FRACTAL_SECTIONS:
            lines.append(f"[{s}]")
            lines += [f"{k} {v};" for k, v in self.fractals[s].items()]
        if keyframes:
            cols = list(keyframes[0].keys())
            lines += ["[keyframes]", "frame;" + ";".join(cols)]
            for i, kf in enumerate(keyframes):
                lines.append(f"{i};" + ";".join(
                    str(int(round(kf[c]))) if c.endswith(("_R", "_G", "_B")) else fnum(kf[c])
                    for c in cols))
        with open(path, "w", newline="\n", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def pose_columns(cam, tgt, top):
    return {"main_camera_x": cam[0], "main_camera_y": cam[1], "main_camera_z": cam[2],
            "main_target_x": tgt[0], "main_target_y": tgt[1], "main_target_z": tgt[2],
            "main_camera_top_x": top[0], "main_camera_top_y": top[1], "main_camera_top_z": top[2]}


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def find_mandelbulber(explicit=None):
    cands = [explicit, os.environ.get("MANDELBULBER"), shutil.which("mandelbulber2")]
    for pat in (r"C:\Program Files\Mandelbulber*\mandelbulber2.exe",
                r"C:\Program Files (x86)\Mandelbulber*\mandelbulber2.exe",
                os.path.expanduser(r"~\Mandelbulber*\mandelbulber2.exe"),
                os.path.expanduser(r"~\Mandelbulber*\*\mandelbulber2.exe"),
                os.path.expanduser(r"~\Downloads\mandelbulber*\mandelbulber2.exe"),
                os.path.expanduser(r"~\Downloads\mandelbulber*\*\mandelbulber2.exe"),
                "/usr/bin/mandelbulber2", "/usr/local/bin/mandelbulber2",
                "/Applications/Mandelbulber2.app/Contents/MacOS/mandelbulber2"):
        cands.extend(sorted(glob.glob(pat), reverse=True))
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def render_keyframes(exe, fract, outdir, first, last, width, height, fmt="jpg",
                     gpu=False, progress=None):
    """Render frames first..last-1 of `fract`. Returns frame paths in order.

    Mandelbulber appends "frame_0000123.jpg" straight onto --output, so the
    folder needs its trailing separator. --never-delete stops it asking
    "purge the output folder? y/n" (which would hang an unattended render)
    when frames from an interrupted run exist; it just skips them."""
    os.makedirs(outdir, exist_ok=True)
    cmd = [exe, "--nogui", "--never-delete", "--keyframe", "--start", str(first),
           "--end", str(last), "--res", f"{width}x{height}", "--format", fmt,
           "--output", os.path.join(outdir, "")]
    if gpu:
        cmd.append("--gpu")
    cmd.append(fract)
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors="replace")
    tail, last_seen = [], -1
    for line in proc.stdout:
        tail = (tail + [line.rstrip()])[-20:]
        if progress:
            done = len(glob.glob(os.path.join(outdir, f"frame_*.{fmt}")))
            if done != last_seen:
                last_seen = done
                progress(done)
    if proc.wait() != 0:
        raise RuntimeError("Mandelbulber stopped with an error:\n  " + "\n  ".join(tail))
    return [os.path.join(outdir, f"frame_{i:07d}.{fmt}") for i in range(first, last)]


def read_png(path, channels=3):
    """8- or 16-bit PNG -> float array in 0..1 (via ffmpeg, no extra modules)."""
    info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v",
                           "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
                          capture_output=True, text=True).stdout.strip().split(",")
    w, h = int(info[0]), int(info[1])
    fmt = {1: "gray16le", 3: "rgb48le"}[channels]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo",
                          "-pix_fmt", fmt, "-"], capture_output=True).stdout
    return (np.frombuffer(raw, np.uint16).reshape(h, w, channels).astype(np.float64)
            / 65535.0)


# ---------------------------------------------------------------------------
# distance probing
# ---------------------------------------------------------------------------

def depth_probe(exe, scene, poses, vis, workdir, res=16, fov=None, gpu=False):
    """Measure true distances inside the scene from several camera poses.

    Mandelbulber has no depth output with absolute units, so this uses its
    fog: the scene is rendered twice with plain exponential fog of two
    different colors (and everything else that alters color switched off).
    In the difference between the two renders the surface's own color
    cancels, leaving the fog amount f per pixel, and exponential fog gives
    distance = -visibility * ln(1 - f). (Verified: the ratio of log-fog at
    two visibilities matches the exponential law to within 1%.)

    poses: list of (cam, target, top). Returns an array [n, res, res] of
    distances (np.inf where the ray met only sky / beyond measurable range).
    """
    os.makedirs(workdir, exist_ok=True)
    frames = []
    for col_name, col in (("a", (1.0, 0.0, 1.0)), ("b", (0.0, 1.0, 0.0))):
        sc = scene.copy()
        c = rgb16(col)
        sc.set(volumetric_fog_enabled=False, DOF_enabled=False, glow_enabled=False,
               glow_intensity=0.0, iteration_fog_enable=False,
               basic_fog_enabled=True, basic_fog_color=c, basic_fog_visibility=vis,
               background_color_1=c, background_color_2=c, background_color_3=c,
               background_3_colors_enable=False, textured_background=False,
               ambient_occlusion_enabled=False, raytraced_reflections=False,
               main_light_volumetric_enabled=False, aux_light_enabled_1=False,
               gamma=1.0, brightness=1.0, contrast=1.0, saturation=1.0, hdr=False,
               hdr_blur_enabled=False, antialiasing_enabled=False,
               frames_per_keyframe=1, keyframe_last_to_render=len(poses))
        if fov is not None:
            sc.set(fov=fov)
        kfs = [pose_columns(*p) for p in poses]
        kfs.append(kfs[-1])                       # endpoint keyframe
        fract = os.path.join(workdir, f"probe_{col_name}.fract")
        sc.write(fract, kfs)
        outdir = os.path.join(workdir, col_name)
        shutil.rmtree(outdir, ignore_errors=True)
        # 8-bit PNG: the only lossless format this Mandelbulber writes for
        # animations (png16 is stills-only; EXR/TIFF crash in animation mode).
        # With visibility ~ the distance being measured, 8-bit fog steps
        # resolve distance to about 1% of the visibility.
        paths = render_keyframes(exe, fract, outdir, 0, len(poses), res, res,
                                 fmt="png", gpu=gpu)
        frames.append(np.stack([read_png(p) for p in paths]))
    a, b = frames
    f = ((a[..., 0] - b[..., 0]) + (b[..., 1] - a[..., 1]) + (a[..., 2] - b[..., 2])) / 3.0
    f = np.clip(f, 0.0, 1.0)
    with np.errstate(divide="ignore"):
        d = -vis * np.log(np.maximum(1.0 - f, 1e-12))
    d[f > 0.995] = np.inf                         # indistinguishable from pure fog
    return d
