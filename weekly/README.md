# Weekly videos (3D, rendered with Blender)

One custom 3D video per week, each in its own folder:

| week | video | folder |
| --- | --- | --- |
| 2026-09-26 | 3D Kaleidoscope | `2026-09-26_kaleidoscope/` |

## How each week works

1. You name the theme; a Blender scene is designed for it and a 10-second
   sample is rendered for approval.
2. Once approved, the week's folder has everything needed to render the
   full video on your own computer:
   - **`speed_test.bat`** — renders a few frames and estimates how long
     the render takes on your machine. Run it first. It also says whether
     Blender found your graphics card.
   - **`render.bat`** — renders the full video (3 hours by default), with
     your music, crash-safely. After a power cut or crash, just run it
     again and answer **Y** to finish the interrupted render.
   - Everything is **photoreal** (Cycles path tracing on the graphics card:
     real refraction, glowing things light their surroundings).
   - **Seamless loop:** only a 10-minute loop is rendered and it is repeated
     to fill the 3 hours (18 times), so the render takes a fraction of the
     time. The world is built to come back exactly to its starting state
     after one loop, so the joins are invisible — no fade, no cut.
   - Step-by-step instructions for each week are in its folder
     (e.g. `2026-09-26_kaleidoscope/HOW_TO_MAKE_THE_VIDEO.txt`).
3. The approved sample is literally a 10-second excerpt of the final video
   (the launcher uses the same seed), so the full render looks exactly like
   what you approved.

## Requirements

- **Blender 4.5 LTS** (free): https://www.blender.org/download/lts/ — not
  Blender 5, which renders the gems' glowing volumes extremely slowly (the
  launchers pick 4.5 automatically when both are installed).
- The PortalMachine setup already done (`setup.bat`), which provides Python
  and ffmpeg.
- Blender renders on your graphics card automatically. On an NVIDIA RTX
  card it uses OptiX (the RTX ray-tracing cores); keep the NVIDIA driver up
  to date.

## Why every video is seamless

Every frame is computed purely from its timestamp, and the world streams in
ahead of the camera, so the video can be rendered in chunks (and resumed
after a crash) and still play as one unbroken journey. Chunk joins are
checked frame-by-frame for any jump.

## For the scene author

A scene is a Python script run by Blender (`blender -b -P scene.py -- ...`)
that accepts `--seed --start --end --outdir --width --height --fps
--samples --engine {cycles,eevee} --loop SECONDS` (the world must return
exactly to its starting state after SECONDS; print `BLENDER <version> ENGINE <device>`
first; render frames to `outdir/f_0000123.jpg`, skip existing ones,
print `FRAME <n> <seconds>`) and `--still T --out file.png`. The shared
`common/render_driver.py` handles chunking, resume, the glow pass,
joining, music and the speed test.
