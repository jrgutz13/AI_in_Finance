"""GPU renderer: draws each scene shader into an offscreen framebuffer,
crossfades pairs of scenes in a composite pass, and pipes raw frames into
ffmpeg for encoding."""

import subprocess
import sys
import time

import moderngl
import numpy as np

from .scenes import SCENES, common_source
from .sequencer import active_clips

_VERTEX = """
#version 330
in vec2 in_pos;
out vec2 v_uv;
void main() {
    v_uv = in_pos * 0.5 + 0.5;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

# Composite pass also flips vertically: GL framebuffers are bottom-up,
# ffmpeg rawvideo expects top-down.
_COMPOSITE = """
#version 330
uniform sampler2D texA;
uniform sampler2D texB;
uniform float u_fade;
in vec2 v_uv;
out vec4 fragColor;
void main() {
    vec2 uv = vec2(v_uv.x, 1.0 - v_uv.y);
    fragColor = mix(texture(texA, uv), texture(texB, uv), u_fade);
}
"""


def _create_context():
    for kwargs in ({}, {"backend": "egl"}):
        try:
            return moderngl.create_context(standalone=True, **kwargs)
        except Exception:
            continue
    raise RuntimeError(
        "Could not create an OpenGL context. On a headless Linux box install "
        "Mesa EGL (apt install libegl1 libgl1-mesa-dri)."
    )


class Renderer:
    def __init__(self, width, height, scene_names=None):
        self.width, self.height = width, height
        self.ctx = _create_context()

        quad = np.array([-1, -1, 3, -1, -1, 3], dtype="f4")
        self._vbo = self.ctx.buffer(quad.tobytes())

        common = common_source()
        self.programs = {}
        self.vaos = {}
        for name in (scene_names or SCENES.keys()):
            frag = common + "\n" + SCENES[name].source()
            prog = self.ctx.program(vertex_shader=_VERTEX, fragment_shader=frag)
            self.programs[name] = prog
            self.vaos[name] = self.ctx.vertex_array(prog, [(self._vbo, "2f", "in_pos")])

        self.composite = self.ctx.program(vertex_shader=_VERTEX, fragment_shader=_COMPOSITE)
        self.composite["texA"] = 0
        self.composite["texB"] = 1
        self.vao_composite = self.ctx.vertex_array(
            self.composite, [(self._vbo, "2f", "in_pos")])

        def make_target():
            tex = self.ctx.texture((width, height), 4)
            tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
            return tex, self.ctx.framebuffer(color_attachments=[tex])

        self.texA, self.fboA = make_target()
        self.texB, self.fboB = make_target()
        _, self.fbo_out = make_target()

    def _draw_scene(self, fbo, scene, params, palette, local_time,
                    continuous=False):
        prog = self.programs[scene]
        prog["u_resolution"] = (float(self.width), float(self.height))
        prog["u_time"] = local_time
        a, b, c, d = palette
        prog["u_colA"], prog["u_colB"] = a, b
        prog["u_colC"], prog["u_colD"] = c, d
        for key in ("speed", "p1", "p2", "p3", "p4"):
            # GLSL drops uniforms a shader doesn't use; skip those
            if "u_" + key in prog:
                prog["u_" + key] = params[key]
        # only some shaders declare u_continuous; ignore where it's absent
        if "u_continuous" in prog:
            prog["u_continuous"] = 1.0 if continuous else 0.0
        fbo.use()
        self.vaos[scene].render()

    def _composite(self, fade, has_b):
        self.composite["u_fade"] = fade
        self.texA.use(0)
        (self.texB if has_b else self.texA).use(1)
        self.fbo_out.use()
        self.vao_composite.render()
        return self.fbo_out.read(components=3)

    def render_frame(self, clips, t):
        a, b, fade = active_clips(clips, t)
        self._draw_scene(self.fboA, a.scene, a.params, a.palette,
                         (t - a.start) + a.phase)
        if b is not None and fade > 0.0:
            self._draw_scene(self.fboB, b.scene, b.params, b.palette,
                             (t - b.start) + b.phase)
        return self._composite(fade, b is not None)

    def render_continuous(self, track, t):
        params, palette = track.eval(t)
        self._draw_scene(self.fboA, track.scene, params, palette,
                         t + track.phase0, continuous=True)
        return self._composite(0.0, False)


def auto_maxrate_mbps(width, height, fps):
    """Bitrate ceiling in Mbit/s, scaled to resolution/fps (~0.16 bits per
    pixel — comfortably above YouTube's recommended upload bitrates).
    Without a ceiling, noisy scenes like fractal foam can push CRF encoding
    to hundreds of Mbit/s and fill the disk."""
    return max(6, round(width * height * fps * 0.16 / 1e6))


def encode(renderer, frame_fn, duration, fps, out_path, audio=None,
           codec="libx264", crf=20, preset="medium", maxrate_mbps=None,
           t_start=0.0, container="mp4", label="", quiet=False):
    """frame_fn(t) -> rgb24 bytes for the frame at time t (seconds).

    maxrate_mbps: bitrate ceiling; None = auto from resolution, 0 = uncapped.
    t_start/container: used by crash-safe part rendering — frames are pulled
    from absolute time t_start.., and "ts" writes an MPEG-TS segment (no
    faststart, no audio; those happen when the parts are joined).
    """
    w, h = renderer.width, renderer.height
    if maxrate_mbps is None:
        maxrate_mbps = auto_maxrate_mbps(w, h, fps)
    cap = ["-maxrate", f"{maxrate_mbps}M", "-bufsize", f"{2 * maxrate_mbps}M"] \
        if maxrate_mbps else []
    if container == "ts":
        audio = None
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
    ]
    if audio:
        cmd += ["-stream_loop", "-1", "-i", audio]
    cmd += ["-map", "0:v"]
    if audio:
        cmd += ["-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd += ["-c:v", codec]
    if codec == "libx264":
        cmd += ["-crf", str(crf), "-preset", preset] + cap
    elif codec.endswith("_nvenc"):
        cmd += ["-cq", str(crf), "-preset", "p5", "-rc", "vbr"] + cap
    cmd += ["-pix_fmt", "yuv420p"]
    if container == "ts":
        cmd += ["-f", "mpegts"]
    else:
        cmd += ["-movflags", "+faststart"]
    cmd += ["-t", f"{duration:.3f}", out_path]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    total = int(round(duration * fps))
    started = time.time()
    last_report = 0.0
    try:
        for frame in range(total):
            t = t_start + frame / fps
            try:
                proc.stdin.write(frame_fn(t))
            except (BrokenPipeError, OSError):
                # ffmpeg died mid-render (most often: disk full)
                break
            now = time.time()
            if not quiet and (now - last_report > 2.0 or frame == total - 1):
                last_report = now
                done = frame + 1
                rate = done / max(now - started, 1e-6)
                eta = (total - done) / max(rate, 1e-6)
                sys.stderr.write(
                    f"\r  {label}frame {done}/{total}  ({100*done/total:5.1f}%)  "
                    f"{rate:6.1f} fps  ETA {int(eta//3600)}:{int(eta%3600//60):02d}:{int(eta%60):02d}   ")
                sys.stderr.flush()
    finally:
        try:
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        ret = proc.wait()
        if not quiet:
            sys.stderr.write("\n")
    if ret != 0:
        raise RuntimeError(
            f"ffmpeg exited with code {ret}. If its messages above say "
            f"'No space left on device', free some disk space and delete the "
            f"partial file ({out_path}), then render again.")
