"""GPU renderer: draws each scene shader into an offscreen framebuffer,
crossfades pairs of scenes in a composite pass, runs the flash guard, and
pipes raw frames into ffmpeg for encoding.

Flash guard (optional, --flash-guard; off by default because it can soften
fast-moving glows): the picture is divided into blocks
(1/68 of the picture height: 16 pixels at 1080p) and each block's brightness
is watched for back-and-forth flicker. Wherever a block flickers faster than
about 2.5 times a second (with 10% brightness swings, as the standards count
flashes), its brightness is smoothed into a gentle fade (the fine detail is
kept), so nothing can strobe at the rates that can trigger
photosensitive seizures (broadcast rules allow at most 3 flashes per
second), whatever a scene does. Normal motion isn't flicker, so it passes
through untouched."""

import os
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
    vec4 c = mix(texture(texA, uv), texture(texB, uv), u_fade);
    fragColor = vec4(pow(max(c.rgb, 0.0), vec3(2.2)), 1.0);     // to linear light
}
"""

GUARD_SWING = 0.10              # a brightness swing this big (linear) counts as a reversal
                                # (the broadcast/WCAG flash threshold: 10% of white)
GUARD_RATE = 0.6                # while smoothing: max change, 60% of white per second
GUARD_CUTOFF = 0.5              # while smoothing: temporal low-pass cutoff, Hz

# guard pass 1, per block: watch for back-and-forth flicker and, where it is
# found, smooth the block's brightness. Outputs the (possibly smoothed) block
# brightness and the block's tracking state.
_GUARD_STATE = """
#version 330
uniform sampler2D texC;         // current frame, linear, with mipmaps
uniform sampler2D prevS;        // previous block brightness (as output)
uniform sampler2D prevT;        // previous tracking: last extreme, direction, activity
uniform float u_first;
uniform float u_lod;
uniform float u_swing;          // reversal threshold
uniform float u_decay;          // activity decay per frame (1 s memory)
uniform float u_alpha;          // low-pass coefficient while smoothing
uniform float u_step;           // max change per frame while smoothing
in vec2 v_uv;
layout(location = 0) out vec4 outS;
layout(location = 1) out vec4 outT;
layout(location = 2) out vec4 outL;   // the block's own brightness, for pass 2
void main() {
    vec3 L = textureLod(texC, v_uv, u_lod).rgb;
    float Y = dot(L, vec3(0.2126, 0.7152, 0.0722));
    outL = vec4(L, 1.0);
    if (u_first > 0.5) {
        outS = vec4(L, 1.0);
        outT = vec4(Y, 0.0, 0.0, 1.0);
        return;
    }
    vec3 S = texture(prevS, v_uv).rgb;
    vec4 T = texture(prevT, v_uv);
    float ext = T.x, dir = T.y, act = T.z * u_decay;
    bool up = Y - ext >= u_swing, down = ext - Y >= u_swing;
    if ((up && dir <= 0.0) || (down && dir >= 0.0)) {   // a reversal
        act += 1.0;
        ext = Y;
        dir = up ? 1.0 : -1.0;
    } else if (dir > 0.0) {
        ext = max(ext, Y);
    } else if (dir < 0.0) {
        ext = min(ext, Y);
    }
    // act ~ reversals in the last second = 2 x flashes per second: start
    // smoothing at 2.5 flashes/s, fully on by 3.25 (the broadcast limit is
    // 3). Ordinary motion - a line or glow sweeping past - never gets here.
    float k = smoothstep(5.0, 6.5, act);
    vec3 lim = S + clamp(u_alpha * (L - S), -u_step, u_step);
    outS = vec4(mix(L, lim, k), 1.0);
    outT = vec4(ext, dir, act, 1.0);
}
"""

# guard pass 2: swap each block's brightness for the guarded one, keeping
# the fine detail (where nothing was smoothed, the frame is unchanged)
_GUARD_OUT = """
#version 330
uniform sampler2D texC;
uniform sampler2D curS;
uniform sampler2D curL;
in vec2 v_uv;
out vec4 fragColor;
vec3 corr(vec2 uv) { return texture(curS, uv).rgb - texture(curL, uv).rgb; }
void main() {
    // the correction (guarded minus actual block brightness) is zero wherever
    // nothing was smoothed, so the frame is unchanged there; where it isn't,
    // it is spread over neighbouring blocks so it can't show block edges
    vec2 e = 1.0 / vec2(textureSize(curS, 0));
    vec3 D = corr(v_uv) * 0.25
           + (corr(v_uv + vec2(e.x, 0.0)) + corr(v_uv - vec2(e.x, 0.0))
              + corr(v_uv + vec2(0.0, e.y)) + corr(v_uv - vec2(0.0, e.y))) * 0.125
           + (corr(v_uv + e) + corr(v_uv - e)
              + corr(v_uv + vec2(e.x, -e.y)) + corr(v_uv + vec2(-e.x, e.y))) * 0.0625;
    vec3 c = textureLod(texC, v_uv, 0.0).rgb;
    fragColor = vec4(pow(max(c + D, 0.0), vec3(1.0 / 2.2)), 1.0);
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
    def __init__(self, width, height, scene_names=None, speed_scale=1.0, flash_guard=False):
        self.width, self.height = width, height
        # multiplies every scene's motion rate; 0.5 = half speed
        self.speed_scale = speed_scale
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

        # flash guard: the composite goes to a linear float texture with
        # mipmaps; two small ping-pong textures hold the limited brightness
        self.texC = self.ctx.texture((width, height), 4, dtype="f2")
        self.texC.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
        self.fboC = self.ctx.framebuffer(color_attachments=[self.texC])
        # block size ~1/68 of the height (16 px at 1080p, 32 px at 4K)
        lod = max(0, int(round(np.log2(height / 68.0))))
        sw, sh = max(1, width >> lod), max(1, height >> lod)
        # ping-pong sets of (guarded brightness S, tracking state T, block brightness L, fbo)
        self.guard = []
        for _ in range(2):
            texs = []
            for _ in range(3):
                tex = self.ctx.texture((sw, sh), 4, dtype="f4")
                tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
                tex.repeat_x = tex.repeat_y = False
                texs.append(tex)
            texs[0].filter = texs[2].filter = (moderngl.LINEAR, moderngl.LINEAR)   # upsampled
            self.guard.append((texs[0], texs[1], texs[2],
                               self.ctx.framebuffer(color_attachments=texs)))
        self.guard_state = self.ctx.program(vertex_shader=_VERTEX, fragment_shader=_GUARD_STATE)
        self.guard_out = self.ctx.program(vertex_shader=_VERTEX, fragment_shader=_GUARD_OUT)
        self.guard_state["texC"], self.guard_state["prevS"], self.guard_state["prevT"] = 0, 1, 2
        self.guard_state["u_swing"] = GUARD_SWING
        self.guard_out["texC"], self.guard_out["curS"], self.guard_out["curL"] = 0, 1, 2
        self.guard_state["u_lod"] = float(lod)
        self.vao_gstate = self.ctx.vertex_array(self.guard_state, [(self._vbo, "2f", "in_pos")])
        self.vao_gout = self.ctx.vertex_array(self.guard_out, [(self._vbo, "2f", "in_pos")])
        self.fps = 30.0
        self.flash_guard = flash_guard
        self.reset_guard()
        # without the guard, the composite writes the output directly
        self.composite_direct = self.ctx.program(
            vertex_shader=_VERTEX, fragment_shader=_COMPOSITE.replace(
                "fragColor = vec4(pow(max(c.rgb, 0.0), vec3(2.2)), 1.0);     // to linear light",
                # a fixed, invisible dither (+-1 level) breaks up the banding
                # 8-bit video shows in smooth dark gradients
                "vec2 q = floor(gl_FragCoord.xy);"
                " float n = fract(sin(dot(q, vec2(12.9898, 78.233))) * 43758.5453)"
                " + fract(sin(dot(q, vec2(39.3468, 11.135))) * 24634.6345) - 1.0;"
                " fragColor = vec4(c.rgb + n / 255.0, 1.0);"))
        self.composite_direct["texA"], self.composite_direct["texB"] = 0, 1
        self.vao_direct = self.ctx.vertex_array(self.composite_direct,
                                                [(self._vbo, "2f", "in_pos")])

    def reset_guard(self):
        """Forget the guard's history (the next frame passes through as-is)."""
        self._guard_first = True
        self._guard_i = 0

    def _draw_scene(self, fbo, scene, params, palette, local_time,
                    continuous=False):
        prog = self.programs[scene]
        prog["u_resolution"] = (float(self.width), float(self.height))
        prog["u_time"] = local_time
        # shaders with their own color scheme don't use the palette, and GLSL
        # drops unused uniforms: only set the ones that exist
        for name, value in zip(("u_colA", "u_colB", "u_colC", "u_colD"), palette):
            if name in prog:
                prog[name] = value
        for key in ("speed", "p1", "p2", "p3", "p4"):
            # GLSL drops uniforms a shader doesn't use; skip those
            if "u_" + key in prog:
                value = params[key]
                if key == "speed":
                    value *= self.speed_scale
                prog["u_" + key] = value
        # only some shaders declare u_continuous; ignore where it's absent
        if "u_continuous" in prog:
            prog["u_continuous"] = 1.0 if continuous else 0.0
        fbo.use()
        self.vaos[scene].render()

    def _composite(self, fade, has_b):
        if not self.flash_guard:
            self.composite_direct["u_fade"] = fade
            self.texA.use(0)
            (self.texB if has_b else self.texA).use(1)
            self.fbo_out.use()
            self.vao_direct.render()
            return self.fbo_out.read(components=3)
        self.composite["u_fade"] = fade
        self.texA.use(0)
        (self.texB if has_b else self.texA).use(1)
        self.fboC.use()
        self.vao_composite.render()
        self.texC.build_mipmaps()
        # pass 1: per-block flicker tracking and smoothing, ping-pong
        prev_s, prev_t, _, _ = self.guard[self._guard_i]
        cur_tex, _, cur_l, cur_fbo = self.guard[1 - self._guard_i]
        g = self.guard_state
        g["u_step"] = GUARD_RATE / self.fps
        g["u_alpha"] = 1.0 - float(np.exp(-2.0 * np.pi * GUARD_CUTOFF / self.fps))
        g["u_decay"] = float(np.exp(-1.0 / self.fps))
        g["u_first"] = 1.0 if self._guard_first else 0.0
        self.texC.use(0)
        prev_s.use(1)
        prev_t.use(2)
        cur_fbo.use()
        self.vao_gstate.render()
        # pass 2: the output frame
        self.texC.use(0)
        cur_tex.use(1)
        cur_l.use(2)
        self.fbo_out.use()
        self.vao_gout.render()
        self._guard_i = 1 - self._guard_i
        self._guard_first = False
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


def decode_audio(audio, wav_path):
    """Decode the music once to WAV. Repeating an MP3 directly with
    -stream_loop drops a few ms of encoder padding at every repeat (a tiny
    click at each seam); the decoded audio repeats sample-exactly."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", audio, "-vn",
                    "-c:a", "pcm_s16le", wav_path], check=True)
    return wav_path


def looped_audio_args(wav_path, duration, input_index=1):
    """ffmpeg args that loop the decoded music under the whole video and fade
    it out over the last 5 seconds instead of cutting mid-note."""
    fade = max(0.0, duration - 5.0)
    return (["-stream_loop", "-1", "-i", wav_path],
            ["-map", f"{input_index}:a", "-af", f"afade=t=out:st={fade:.3f}:d=5",
             "-c:a", "aac", "-b:a", "192k", "-shortest"])


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
    wav = decode_audio(audio, out_path + ".music.wav") if audio else None
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
    ]
    a_in, a_out = looped_audio_args(wav, duration) if wav else ([], [])
    cmd += a_in + ["-map", "0:v"] + a_out
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

    # flash guard: start from a clean history; a part that starts mid-video
    # first renders the 10 s before it (discarded) so its guard state matches
    # an uninterrupted render and the parts join seamlessly (measured: 10 s
    # brings the difference at a join below 0.001/255; 2 s left a visible step)
    renderer.fps = float(fps)
    renderer.reset_guard()
    warm = int(round(10.0 * fps)) if t_start > 0 and renderer.flash_guard else 0
    for k in range(warm, 0, -1):
        if t_start - k / fps >= 0:
            frame_fn(t_start - k / fps)

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
        if wav and os.path.exists(wav):
            os.remove(wav)
        if not quiet:
            sys.stderr.write("\n")
    if ret != 0:
        raise RuntimeError(
            f"ffmpeg exited with code {ret}. If its messages above say "
            f"'No space left on device', free some disk space and delete the "
            f"partial file ({out_path}), then render again.")
