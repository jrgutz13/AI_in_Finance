"""Scene registry: each scene is a GLSL fragment shader plus the ranges its
random parameters are drawn from. p1..p4 mean something different per scene
(documented at the top of each .glsl file)."""

import os
from dataclasses import dataclass, field

_HERE = os.path.dirname(__file__)


@dataclass
class SceneDef:
    name: str
    title: str
    # (min, max) for each generic parameter; "choices" entries pick from a list
    speed: tuple = (0.7, 1.3)
    p1: tuple = (0.0, 1.0)
    p2: tuple = (0.0, 1.0)
    p3: tuple = (0.0, 1.0)
    p4: tuple = (0.0, 1.0)
    choices: dict = field(default_factory=dict)  # param name -> list of values
    # max random local-time offset; scenes with exponential zoom need a small
    # value or float precision collapses the image (see fractal_zoom.glsl)
    phase_max: float = 100.0
    # params that must stay constant in continuous mode. "speed" is always
    # locked; list here any param that multiplies time (drifting it would make
    # the motion lurch), must be a whole number, or is an on/off fold.
    locked: tuple = ()

    def source(self):
        with open(os.path.join(_HERE, self.name + ".glsl")) as f:
            return f.read()

    def random_params(self, rng):
        params = {}
        for key in ("speed", "p1", "p2", "p3", "p4"):
            if key in self.choices:
                params[key] = float(rng.choice(self.choices[key]))
            else:
                lo, hi = getattr(self, key)
                params[key] = rng.uniform(lo, hi)
        return params

    def locked_params(self):
        """Param names held constant in continuous mode (speed always is)."""
        return {"speed", *self.locked}

    def free_params(self):
        """Param names that drift smoothly over time in continuous mode."""
        return [k for k in ("p1", "p2", "p3", "p4") if k not in self.locked]


SCENES = {
    s.name: s
    for s in [
        SceneDef(
            "neon_tunnel", "Neon Portal Tunnel",
            speed=(0.8, 1.4),
            p2=(-0.5, 0.5),        # twist
            p3=(-0.4, 0.4),        # spin
            p4=(0.5, 2.0),         # core glow
            choices={"p1": [3, 4, 5, 6, 8]},  # polygon sides
            locked=("p1", "p3"),   # sides (integer), spin (scales time)
        ),
        SceneDef(
            "kaleidoscope", "Kaleidoscope",
            speed=(0.6, 1.2),
            p2=(0.1, 0.35),        # breathe
            p3=(1.5, 4.0),         # pattern scale
            p4=(0.3, 1.2),         # radial color drift
            choices={"p1": [5, 6, 7, 8, 10, 12]},  # wedges
            locked=("p1",),        # wedges (integer)
        ),
        SceneDef(
            "fractal_zoom", "Infinite Fractal Zoom",
            speed=(0.7, 1.2),
            p1=(0.5, 1.2),         # fractal c.x
            p2=(0.4, 1.1),         # fractal c.y
            p3=(0.5, 1.2),         # zoom rate
            choices={"p4": [0, 0, 1]},  # mirror fold 1/3 of the time
            phase_max=3.0,
            locked=("p3", "p4"),   # zoom rate (scales time), mirror fold
        ),
        SceneDef(
            "wormhole", "Wormhole",
            speed=(0.7, 1.3),
            p1=(2.0, 6.0),         # angular repeat
            p2=(-1.5, 1.5),        # swirl
            p3=(4.0, 10.0),        # ring frequency
            p4=(0.6, 1.4),         # fly speed
            locked=("p1", "p4"),   # angular repeat (integer), fly speed (scales time)
        ),
        SceneDef(
            "mandala", "Mandala Bloom",
            speed=(0.6, 1.1),
            p2=(0.8, 2.0),         # ring frequency
            p3=(1.5, 5.0),         # petal sharpness
            p4=(0.5, 1.5),         # pulse
            choices={"p1": [6, 8, 10, 12, 16]},  # petals
            locked=("p1",),        # petals (integer)
        ),
        SceneDef(
            "hyperdrive", "Hyperdrive",
            speed=(0.8, 1.4),
            p1=(0.7, 1.5),         # streak density
            p2=(0.6, 1.2),         # fly speed
            p3=(0.4, 0.9),         # streak length
            p4=(0.3, 1.5),         # color spread
            locked=("p1", "p2"),   # density (re-seeds streaks), speed (scales time)
        ),
        SceneDef(
            "liquid", "Liquid Marble",
            speed=(0.7, 1.3),
            p1=(1.2, 3.0),         # scale
            p2=(2.0, 4.5),         # warp
            p3=(0.5, 1.2),         # flow speed
            choices={"p4": [0, 0, 0, 6, 8]},  # occasional kaleido fold
            locked=("p3", "p4"),   # flow speed (scales time), fold (integer)
        ),
        SceneDef(
            "machine_dream", "Machine Dream (Data Sculpture)",
            speed=(0.5, 1.0),
            p1=(1.1, 2.2),         # structure scale
            p2=(2.5, 5.0),         # churn strength
            p3=(0.5, 1.1),         # flow speed
            p4=(0.75, 1.3),        # sculpture size
            locked=("p3",),        # flow speed (scales time)
        ),
        SceneDef(
            "data_wind", "Data Wind",
            speed=(0.6, 1.1),
            p1=(7.0, 14.0),        # stream line frequency
            p2=(1.5, 3.2),         # turbulence
            p3=(0.7, 1.4),         # drift speed
            p4=(0.5, 2.0),         # curl amount
            locked=("p3",),        # drift speed (scales time)
        ),
        SceneDef(
            "machine_bloom", "Machine Bloom (Data Sculpture)",
            speed=(0.5, 1.0),
            p1=(1.1, 2.0),         # structure scale
            p2=(2.5, 4.5),         # churn strength
            p3=(0.5, 1.1),         # surge speed
            p4=(0.8, 1.25),        # bloom size
            locked=("p3",),        # surge speed (scales time)
        ),
        SceneDef(
            "data_tide", "Data Tide (Particle Ocean)",
            speed=(0.6, 1.1),
            p1=(2.0, 4.0),         # wave scale
            p2=(0.8, 1.8),         # turbulence
            p3=(0.6, 1.3),         # drift speed
            p4=(0.7, 1.4),         # swell amount
            locked=("p3",),        # drift speed (scales time)
        ),
        SceneDef(
            "spiral_dive", "Infinite Spiral Dive",
            speed=(0.7, 1.2),
            p2=(1.2, 3.5),         # twist tightness
            p3=(0.6, 1.3),         # dive speed
            p4=(0.5, 1.2),         # detail amount
            choices={"p1": [2, 3, 4, 5, 6]},  # arms
            locked=("p1", "p3"),   # arms (integer), dive speed (scales time)
        ),
        SceneDef(
            "droste_zoom", "Infinite Gem Rings",
            speed=(0.7, 1.2),
            p2=(0.0, 1.0),         # gem roundness
            p3=(0.8, 1.6),         # zoom speed
            p4=(0.4, 1.5),         # color spread
            choices={"p1": [5, 6, 7, 8, 9]},  # gems per ring
            locked=("p1", "p3"),   # gems (integer), zoom speed (scales time)
        ),
        SceneDef(
            "infinite_flower", "Infinite Flower",
            speed=(0.6, 1.1),
            p2=(-0.6, 0.6),        # petal curl
            p3=(0.8, 1.6),         # bloom speed
            p4=(0.8, 2.0),         # glow amount
            choices={"p1": [5, 6, 7, 8, 9]},  # petals per ring
            locked=("p1", "p3"),   # petals (integer), bloom speed (scales time)
        ),
        SceneDef(
            "julia_dive", "Julia Fractal Dive",
            speed=(0.7, 1.2),
            p1=(-0.80, -0.72),     # Julia c.x (seahorse valley)
            p2=(0.13, 0.20),       # Julia c.y
            p3=(0.5, 1.1),         # zoom rate
            p4=(0.4, 1.0),         # trap color mix
            phase_max=3.0,
            locked=("p3",),        # zoom rate (scales time)
        ),
        SceneDef(
            "nested_squares", "Hypno Polygons",
            speed=(0.6, 1.1),
            p2=(0.1, 0.5),         # twist per layer
            p3=(0.7, 1.4),         # zoom speed
            p4=(0.5, 1.5),         # color cycle spread
            choices={"p1": [3, 4, 4, 5, 6]},  # sides
            locked=("p1", "p3"),   # sides (integer), zoom speed (scales time)
        ),
        SceneDef(
            "vortex", "Vortex",
            speed=(0.7, 1.2),
            p2=(1.0, 2.8),         # twist tightness
            p3=(0.6, 1.3),         # flow speed
            p4=(0.5, 1.5),         # spark amount
            choices={"p1": [3, 4, 5, 6, 7]},  # filament arms
            locked=("p1", "p3"),   # arms (integer), flow speed (scales time)
        ),
        SceneDef(
            "galaxy_dive", "Galaxy Dive",
            speed=(0.6, 1.1),
            p2=(0.8, 1.6),         # nebula density
            p3=(0.8, 1.6),         # dive speed
            p4=(0.6, 1.4),         # star density
            choices={"p1": [2, 2, 3, 3, 4]},  # spiral arms
            locked=("p1", "p3", "p4"),  # arms (int), speed (time), density (re-seeds)
        ),
        SceneDef(
            "mandelbulb_3d", "3D Mandelbulb",
            speed=(0.6, 1.0),
            p1=(6.0, 9.0),         # fractal power
            p2=(0.2, 0.8),         # orbit tilt
            p3=(0.7, 1.3),         # orbit speed
            p4=(0.5, 1.4),         # glow
            locked=("p3",),        # orbit speed (scales time)
        ),
        SceneDef(
            "menger_3d", "3D Menger Corridors",
            speed=(0.6, 1.1),
            p1=(0.9, 1.35),        # hole size
            p2=(0.0, 1.6),         # lattice twist
            p3=(0.7, 1.3),         # fly speed
            p4=(0.5, 1.4),         # glow
            locked=("p3",),        # fly speed (scales time)
        ),
        SceneDef(
            "kaleido_3d", "3D Kaleidoscope",
            speed=(0.6, 1.1),
            p2=(0.4, 1.6),         # fold tightness
            p3=(0.7, 1.3),         # fly speed
            p4=(0.5, 1.4),         # glow
            choices={"p1": [5, 6, 7, 8, 10]},  # mirror wedges
            locked=("p1", "p3"),   # wedges (integer), fly speed (scales time)
        ),
        SceneDef(
            "crystal_3d", "3D Crystal Caves",
            speed=(0.6, 1.1),
            p1=(0.55, 0.95),       # crystal size
            p2=(0.6, 1.6),         # cluster spread
            p3=(0.7, 1.3),         # drift speed
            p4=(0.5, 1.3),         # inner glow
            locked=("p3",),        # drift speed (scales time)
        ),
        SceneDef(
            "wormhole_3d", "3D Wormhole",
            speed=(0.6, 1.1),
            p1=(0.85, 1.25),       # tube radius
            p2=(0.5, 1.5),         # wall ripple
            p3=(0.7, 1.3),         # fly speed
            p4=(0.5, 1.4),         # energy glow
            locked=("p3",),        # fly speed (scales time)
        ),
        SceneDef(
            "tunnel_3d", "3D Portal Tunnel (raymarched)",
            speed=(0.7, 1.2),
            p1=(0.85, 1.25),       # tunnel radius
            p2=(0.15, 0.55),       # path wobble
            p3=(0.7, 1.3),         # fly speed
            p4=(0.6, 1.6),         # glow amount
            locked=("p3",),        # fly speed (scales time)
        ),
        SceneDef(
            "ripple_dive", "Ripple Dive",
            speed=(0.6, 1.1),
            p1=(2.5, 5.0),         # ripple frequency
            p2=(0.4, 1.2),         # wobble amount
            p3=(0.6, 1.3),         # dive speed
            p4=(0.4, 1.2),         # color spread
            locked=("p3",),        # dive speed (scales time)
        ),
    ]
}


def common_source():
    with open(os.path.join(_HERE, "common.glsl")) as f:
        return f.read()
