# Portal Machine

A video generator for long-form psychedelic visuals: portal tunnels,
kaleidoscopes, infinite zooms of many kinds, wormholes, mandalas, and
Refik Anadol-style data sculptures — 19 styles in all. It renders videos of
any length (3-hour meditation videos included), and every run produces a
completely different video. No stock footage, no licensing.

Everything is rendered procedurally on the GPU with GLSL shaders and piped
straight into ffmpeg.

## Easiest way (Windows)

1. Install **Python 3.12** from https://www.python.org/downloads/windows/
   (the graphics packages need 3.10–3.13; 3.14+ is too new for them). On the
   first installer screen, check **"Add python.exe to PATH"**.
2. Double-click **`setup.bat`** (one time only — installs everything else).
3. Double-click **`make_video.bat`**, type a length like `3h`, pick a style
   and resolution, optionally drag a music file into the window, press Enter.

The finished MP4 appears in the `output` folder along with a chapters file
for the YouTube description.

## Setup (Mac / Linux / manual)

Requires Python 3.9+, ffmpeg, and OpenGL (any desktop GPU works; on headless
Linux, Mesa works too).

```bash
pip install -r requirements.txt
# ffmpeg: https://ffmpeg.org/download.html  (or: apt install ffmpeg / brew install ffmpeg)
```

## Quick start

```bash
# 60-second 1080p test video with a random seed
python3 generate.py

# 3 hours of one continuously evolving spiral dive, with music
python3 generate.py --duration 3h --scenes spiral_dive --audio music.mp3

# 4K mix of everything
python3 generate.py --duration 3h --resolution 3840x2160 --audio music.mp3
```

Each run prints its seed and writes `output/portal_<seed>.mp4` plus a
`..._chapters.txt` file with YouTube-ready chapter timestamps.

## Two modes: continuous vs. montage

- **One style** (e.g. `--scenes wormhole`, or picking a single style in the
  Windows menu) renders in **continuous mode**: a single unbroken flight that
  never restarts. The motion runs forever while the shape and colors *drift*
  slowly between random waypoints, so the video keeps evolving but has no
  cuts or re-blends. Every video draws fresh random waypoints, so no two
  renders evolve the same way.
- **A mix of styles** (the default, or the "Mix of everything" menu option)
  renders in **montage mode**: random 7–10 second clips of different styles
  crossfaded together for variety.

Add `--clips` to force montage mode for a single style, or `--continuous`
to force a single-style continuous render.

## Scenes

| scene | look |
| --- | --- |
| `neon_tunnel` | glowing neon polygon portals flying past, like a laser tunnel |
| `kaleidoscope` | razor-sharp stained-glass kaleidoscope with sparkle |
| `fractal_zoom` | continuous zoom into bubbling fractal foam |
| `wormhole` | flight down an organic textured tube with luminous rings |
| `mandala` | crisp geometric mandala with pulsing rings and petals |
| `hyperdrive` | warp-speed light streaks over a nebula, star dust, chromatic core |
| `liquid` | slow liquid-marble flow, sometimes kaleido-folded |
| `machine_dream` | Refik Anadol-style churning cloud of a million data-particles |
| `data_wind` | luminous streamlines flowing through invisible turbulence |
| `machine_bloom` | Anadol "Unsupervised" style: a living bloom of particle pigment |
| `data_tide` | Anadol ocean style: rolling waves of luminous particles |
| `spiral_dive` | true infinite zoom down a logarithmic spiral |
| `droste_zoom` | endless rings of glowing gems growing from the center |
| `infinite_flower` | petals bloom from the center forever, golden-angle turned |
| `julia_dive` | dive into a morphing Julia fractal with electric tendrils |
| `nested_squares` | hypnotic hard-edged polygons nesting out of the center |
| `vortex` | whirlpool of glowing filaments spiraling outward forever |
| `galaxy_dive` | flying into a spiral galaxy: arms, dust lanes, star streams |
| `ripple_dive` | soft luminous ripples gliding out of infinite depth |
| `alien_world` | POV flight over a photoreal-style alien landscape with real atmosphere |

### True 3D scenes (raymarched)

These trace a ray per pixel through real 3D space, so they have genuine
perspective, parallax, surface lighting, specular highlights and volumetric
fog — the camera is physically flying through modeled geometry rather than
through a flat pattern that imitates depth.

| scene | look |
| --- | --- |
| `tunnel_3d` | panelled portal tunnel with lit rings receding into fog |
| `mandelbulb_3d` | orbiting the classic 3D fractal as its surface morphs |
| `menger_3d` | flying the corridors of an infinite Menger sponge |
| `kaleido_3d` | mirrored 3D jewels receding with real depth |
| `crystal_3d` | drifting through caves of glowing faceted crystal |
| `wormhole_3d` | organic ridged tube threaded with bioluminescent veins |

**They cost roughly 3–10x more per frame than the flat scenes.** Render them
at 1080p (or 1440p) rather than 4K: a 3-hour 1080p 3D video is an overnight
job, while 4K could take days. Everything else — continuous evolution,
crash-safe parts, resume, bitrate caps — works exactly the same.

All traveling scenes fly FORWARD (into the screen / toward the viewer), and
the infinite-zoom and 3D scenes use periodic/bounded math, so they can run
for hours without ever repeating or degrading.

Adding a scene = dropping a new `.glsl` file in `portal_machine/scenes/` and
registering it (with the ranges its random parameters are drawn from) in
`portal_machine/scenes/__init__.py`. Helpers (`pal`, `fbm`, `rot`, …) come
from `common.glsl`; four generic uniforms `u_p1..u_p4` carry the randomness.

## If a render gets interrupted (power loss, crash, disk full)

Videos longer than 10 minutes render in **crash-safe parts**: every ~10
minutes of finished video is saved permanently as it goes. If the machine
shuts off mid-render, nothing already finished is lost:

- **Windows:** just run `make_video.bat` again — it notices the unfinished
  video and asks *"Finish this interrupted video? [Y/n]"*. Press Enter.
- **Command line:** `python3 generate.py --resume` (or `--resume-info` to
  see what's pending).

The resumed render re-does only the part that was cut off and everything
after it, then joins all parts into the final MP4 — identical to what an
uninterrupted render would have produced. `--part-length 0` disables
part rendering if you ever want a single-pass render.

## Reversing a finished video

If a render came out flying the wrong way, you don't have to re-render it.
Drag the `.mp4` onto **`reverse_video.bat`** (or run
`python3 reverse_video.py "output/portal_12345.mp4"`). It writes a
`..._reversed.mp4` next to the original. It works on multi-hour files
because it reverses in small chunks rather than loading the whole video into
memory; the audio is reversed in sync (add `--mute` to drop it). If a 4K
reverse runs low on memory, add `--segment 4`.

## File sizes

Every render has an automatic **bitrate ceiling** scaled to its resolution
(about 10 Mbit/s at 1080p30, 18 at 1440p30, 40 at 4K30 — above YouTube's
recommended upload bitrates). This keeps even the noisiest scenes (fractal
foam is the worst) from producing runaway files. Worst-case sizes for 3
hours: ~13 GB at 1080p, ~24 GB at 1440p, ~54 GB at 4K; real files usually
land at 40–70% of the cap.

Before rendering, the tool prints the worst-case size and your free disk
space, and stops (or asks first) if the video might not fit.

- Smaller files: `--crf 23`, or a lower cap like `--maxrate 8`.
- Maximum quality regardless of size: `--maxrate 0` removes the ceiling
  (not recommended for fractal_zoom).
- If a render ever dies with "No space left on device", delete the partial
  `.mp4` it left behind — it is unplayable — then free space and re-run
  with the same seed.

## Useful options

| option | what it does |
| --- | --- |
| `--seed 12345` | reproduce the exact same video again |
| `--scenes vortex` | one style only — a single continuous evolving flight |
| `--scenes neon_tunnel,wormhole` | restrict to a few styles (`--list-scenes` to see all) |
| `--clips` | force the clip/crossfade montage even for a single style |
| `--crossfade 0` | hard cuts between clips instead of 1s crossfades |
| `--speed-scale 0.5` | slow every scene down (0.5 = half speed, 2 = double) |
| `--fps 60` | smoother motion (doubles render time) |
| `--still 95` | render a single PNG frame at t=95s to preview a seed quickly |
| `--codec h264_nvenc` | GPU encoding on NVIDIA — recommended for 4K |

## Performance notes

- Rendering is GPU-bound; encoding is CPU-bound. On a typical desktop GPU,
  1080p renders far faster than realtime, so a 3-hour video takes well under
  3 hours.
- The time estimate in the progress line is accurate after the first minute.

## A note on content

All visuals are generated from mathematics at render time — there is no
third-party footage, so the output is yours. Pair it with music you have the
rights to.
