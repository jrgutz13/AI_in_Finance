"""Blender Worlds: an endless bioluminescent alien landscape, flown through
at eye level, rendered frame by frame.

Run inside Blender (tested against 4.0, 4.5 LTS and 5.0):

    blender -b --factory-startup -P world_gen.py -- --seed 7 --start 0 --end 300 \\
        --outdir frames --width 1920 --height 1080 --fps 30

or render one preview still at t seconds:

    blender -b --factory-startup -P world_gen.py -- --seed 7 --still 42 --out look.png

Everything — terrain, every speck, tree and mushroom, the sky, the camera —
is a pure function of (seed, world position, time). Nothing depends on what
was rendered before, so separate runs over different frame ranges join into
one seamless, continuous flight. That is what lets the driver render in
crash-safe chunks.

The world is streamed in 40 m tiles: tiles ahead of the camera are built as
they come into view and tiles behind are deleted, so memory stays flat no
matter how long the video is.

Blender's Python API has changed a lot between 4.0 and 5.x (render engine
names, mesh internals, EEVEE settings). Every version-sensitive call goes
through setp()/set_engine() so one script runs on all of them.
"""

import argparse
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Vector

TAU = 2.0 * math.pi
TILE = 40.0          # world streamed in tiles this long (m, along the path)
VIEW = 380.0         # how far ahead tiles exist; fog hides the far edge
WATER = 0.0          # water surface height
SPEED = 2.2          # camera travel, m/s — a slow meditative glide


# ---------------------------------------------------------------------------
# version-proofing
# ---------------------------------------------------------------------------

def setp(obj, attr, value):
    """Set obj.attr if this Blender version has it; silently skip otherwise."""
    try:
        if hasattr(obj, attr):
            setattr(obj, attr, value)
            return True
    except (AttributeError, TypeError, ValueError):
        pass
    return False


def set_engine(scene, want):
    if want == "cycles":
        scene.render.engine = "CYCLES"
        return "CYCLES"
    # 4.2-4.5 call the new EEVEE "BLENDER_EEVEE_NEXT"; 4.0/4.1 and 5.x
    # call it "BLENDER_EEVEE"
    for eid in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = eid
            return eid
        except TypeError:
            continue
    raise RuntimeError("no EEVEE render engine found in this Blender")


# ---------------------------------------------------------------------------
# deterministic noise (numpy, float64 — identical on every machine)
# ---------------------------------------------------------------------------

def _hash2(ix, iy, s):
    h = (ix * 374761393 + iy * 668265263 + s * 1442695041) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return (h & 0xFFFFFF).astype(np.float64) / 16777216.0


def vnoise(x, y, s):
    xf = np.floor(x)
    yf = np.floor(y)
    fx, fy = x - xf, y - yf
    xi, yi = xf.astype(np.int64), yf.astype(np.int64)
    u = fx * fx * (3.0 - 2.0 * fx)
    v = fy * fy * (3.0 - 2.0 * fy)
    a = _hash2(xi, yi, s)
    b = _hash2(xi + 1, yi, s)
    c = _hash2(xi, yi + 1, s)
    d = _hash2(xi + 1, yi + 1, s)
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v


def fbm(x, y, s, octaves=5):
    x = np.asarray(x, np.float64)
    y = np.asarray(y, np.float64)
    total = np.zeros(np.broadcast(x, y).shape)
    amp, norm = 0.5, 0.0
    for i in range(octaves):
        total = total + amp * vnoise(x, y, s + i * 101)
        norm += amp
        # rotate between octaves to hide the lattice
        x, y = 0.8 * x - 0.6 * y, 0.6 * x + 0.8 * y
        x, y = x * 2.03, y * 2.03
        amp *= 0.5
    return total / norm


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def smootherstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)


# ---------------------------------------------------------------------------
# the world: a meandering water channel through bioluminescent islands
# ---------------------------------------------------------------------------

def channel_x(y):
    """Centerline of the channel the camera glides along."""
    return (14.0 * np.sin(y / 140.0) + 7.0 * np.sin(y / 53.0 + 1.3)
            + 3.0 * np.sin(y / 23.0 + 0.4))


def terrain(x, y, seed):
    x = np.asarray(x, np.float64)
    y = np.asarray(y, np.float64)
    dx = x - channel_x(y)
    h = (fbm(x / 26.0, y / 26.0, seed, 5) - 0.47) * 8.0
    h = h + (fbm(x / 4.5, y / 4.5, seed + 9, 3) - 0.5) * 0.9     # rocky detail
    # carve the channel: always safely below the water under the camera
    g = np.exp(-(dx / 10.0) ** 2)
    h = h * (1.0 - 0.85 * g) - 1.4 * g
    # far hills rising into mountains on both sides
    far = smoothstep(70.0, 240.0, np.abs(dx))
    ridge = 1.0 - np.abs(2.0 * fbm(x / 80.0 + 13.0, y / 80.0 - 7.0, seed + 3, 4) - 1.0)
    return h + far * (4.0 + 38.0 * ridge ** 2.2)


def terrain_normals(x, y, seed, e=0.5):
    hx = terrain(x - e, y, seed) - terrain(x + e, y, seed)
    hy = terrain(x, y - e, seed) - terrain(x, y + e, seed)
    n = np.stack([hx / (2 * e), hy / (2 * e), np.ones_like(hx)], -1)
    return n / np.linalg.norm(n, axis=-1, keepdims=True)


# ---------------------------------------------------------------------------
# biomes: the look drifts continuously between these as the journey goes on
# ---------------------------------------------------------------------------

def srgb(h):
    h = h.lstrip("#")
    c = np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _biome(**kw):
    out = {}
    for k, v in kw.items():
        if isinstance(v, str):
            out[k] = srgb(v)
        elif isinstance(v, (list, tuple)):
            out[k] = np.stack([srgb(c) for c in v])
        else:
            out[k] = np.float64(v)
    return out


BIOMES = [
    _biome(  # sunset shores: indigo sky, orange horizon, glowing islands
        zenith="#1c1a4e", mid="#6c3a7c", horizon="#ff7a3c", glow="#ffb25a",
        cloud_lit="#e8627c", cloud_dark="#3c2452", stars=0.35,
        fog="#7a4a8a", fog_density=0.0060, ground="#0e0b18", ground_gain=1.0,
        water="#0a0d20", water_glow="#20ffd0", sun="#ffb070", sun_energy=1.4,
        speck=["#35e0ff", "#ff4fd8", "#ff8a3a"], canopy=["#40ffc0", "#ff5ad0"],
        fungus=["#ff9a4a", "#ff6fb0", "#b070ff"], orb="#a8ecff", band="#ff7a30", rock="#6c2c3c"),
    _biome(  # blue night forest: navy sky, cyan orbs, pink canopies
        zenith="#060a26", mid="#15225e", horizon="#3c2c8e", glow="#7a5aff",
        cloud_lit="#3e3e96", cloud_dark="#0a0c2c", stars=1.0,
        fog="#22327e", fog_density=0.0085, ground="#070812", ground_gain=1.0,
        water="#05060f", water_glow="#30b8ff", sun="#6070ff", sun_energy=0.05,
        speck=["#3ab0ff", "#ff5ab0", "#ffa040"], canopy=["#3ad0ff", "#ff5ad8"],
        fungus=["#ff70d0", "#40e0ff", "#ffb050"], orb="#80f0ff", band="#ff4aa0", rock="#1c1c3c"),
    _biome(  # magenta dream: near-black violet, red and cyan sparks
        zenith="#12061f", mid="#3c1047", horizon="#b2306c", glow="#ff5282",
        cloud_lit="#a23072", cloud_dark="#200a29", stars=0.7,
        fog="#521a52", fog_density=0.0080, ground="#0a0610", ground_gain=1.0,
        water="#08040c", water_glow="#ff3a7a", sun="#ff6090", sun_energy=0.25,
        speck=["#ff3a5a", "#3ad8ff", "#ff9030"], canopy=["#ff3a8a", "#40e8ff"],
        fungus=["#ff4060", "#40f0ff", "#ff8a30"], orb="#ff9ad2", band="#40e8ff", rock="#3c142a"),
    _biome(  # pink dusk desert: lavender sky, warm ground, pale glow
        zenith="#3c4ca2", mid="#b272c2", horizon="#ffb28c", glow="#ffd2a2",
        cloud_lit="#ff92a2", cloud_dark="#6c4c92", stars=0.0,
        fog="#c28caa", fog_density=0.0050, ground="#3a2440", ground_gain=2.2,
        water="#3c2c52", water_glow="#7affff", sun="#ffc292", sun_energy=2.4,
        speck=["#ffe2a2", "#7affff", "#ff7c5c"], canopy=["#7cffd2", "#ffb2f2"],
        fungus=["#ffd2a2", "#9cffff", "#ff9c8c"], orb="#ffffff", band="#ff9c6c", rock="#c4525c"),
]


class BiomeTrack:
    """Biome waypoints every few hundred meters; everything in between is a
    smooth blend, so the world evolves continuously and never cuts."""

    def __init__(self, seed):
        rng = np.random.default_rng([seed, 777])
        ys, ids = [-400.0], [int(rng.integers(len(BIOMES)))]
        y = -400.0
        while y < 120000.0:                      # ~15 h of travel
            y += float(rng.uniform(320.0, 520.0))
            nb = int(rng.integers(len(BIOMES) - 1))
            if nb >= ids[-1]:
                nb += 1                          # never the same biome twice
            ys.append(y)
            ids.append(nb)
        self.ys = np.array(ys)
        self.ids = ids

    def at(self, y):
        i = int(np.clip(np.searchsorted(self.ys, y) - 1, 0, len(self.ys) - 2))
        f = smootherstep((y - self.ys[i]) / (self.ys[i + 1] - self.ys[i]))
        a, b = BIOMES[self.ids[i]], BIOMES[self.ids[i + 1]]
        return {k: a[k] + (b[k] - a[k]) * f for k in a}


# ---------------------------------------------------------------------------
# mesh building (fast: numpy + foreach_set, no per-vertex Python)
# ---------------------------------------------------------------------------

OCT_V = np.array([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]], np.float64)
OCT_F = np.array([[0, 2, 4], [2, 1, 4], [1, 3, 4], [3, 0, 4],
                  [2, 0, 5], [1, 2, 5], [3, 1, 5], [0, 3, 5]], np.int64)


def build_mesh(name, verts, faces, colors=None, normals=None):
    verts = np.asarray(verts, np.float32).reshape(-1, 3)
    faces = np.asarray(faces, np.int32).reshape(-1, 3)
    nf = len(faces)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.ravel())
    me.loops.add(nf * 3)
    me.loops.foreach_set("vertex_index", faces.ravel())
    me.polygons.add(nf)
    me.polygons.foreach_set("loop_start", np.arange(0, nf * 3, 3, dtype=np.int32))
    try:  # settable before 4.0; derived (read-only) afterwards
        me.polygons.foreach_set("loop_total", np.full(nf, 3, np.int32))
    except (AttributeError, TypeError, RuntimeError):
        pass
    me.update(calc_edges=True)
    me.polygons.foreach_set("use_smooth", np.ones(nf, dtype=bool))
    if colors is not None:
        ca = me.color_attributes.new("col", "FLOAT_COLOR", "POINT")
        ca.data.foreach_set("color", np.asarray(colors, np.float32).ravel())
    if normals is not None:
        # custom normals from the analytic terrain gradient: without them
        # each tile shades its edges on its own and seams appear between tiles
        setp(me, "use_auto_smooth", True)            # required before 4.1
        try:
            me.normals_split_custom_set_from_vertices(
                np.asarray(normals, np.float32).reshape(-1, 3).tolist())
        except (AttributeError, RuntimeError, TypeError):
            pass
    return me


class Accum:
    """Collects many small pieces that share a material into one mesh."""

    def __init__(self):
        self.v, self.f, self.c = [], [], []
        self.n = 0

    def add(self, verts, faces, color):
        verts = np.asarray(verts, np.float64).reshape(-1, 3)
        color = np.asarray(color, np.float64)
        if color.ndim == 1:
            color = np.broadcast_to(color, (len(verts), color.shape[0]))
        if color.shape[1] == 3:
            color = np.concatenate([color, np.ones((len(color), 1))], 1)
        self.v.append(verts)
        self.f.append(np.asarray(faces, np.int64).reshape(-1, 3) + self.n)
        self.c.append(color)
        self.n += len(verts)

    def build(self, name):
        if not self.v:
            return None
        return build_mesh(name, np.concatenate(self.v), np.concatenate(self.f),
                          np.concatenate(self.c))


def ring_faces(rows, sides):
    """Triangles joining `rows` rings of `sides` vertices (outward winding)."""
    k = np.arange(rows - 1)[:, None]
    s = np.arange(sides)[None, :]
    a = k * sides + s
    b = k * sides + (s + 1) % sides
    c, d = a + sides, b + sides
    return np.concatenate([np.stack([a, b, d], -1).reshape(-1, 3),
                           np.stack([a, d, c], -1).reshape(-1, 3)])


def revolve(radii, zs, sides, center, twist=0.0):
    radii = np.asarray(radii, np.float64)
    zs = np.asarray(zs, np.float64)
    ang = TAU * np.arange(sides) / sides
    th = ang[None, :] + twist * zs[:, None]
    v = np.stack([radii[:, None] * np.cos(th), radii[:, None] * np.sin(th),
                  np.broadcast_to(zs[:, None], th.shape)], -1).reshape(-1, 3)
    return v + np.asarray(center), ring_faces(len(radii), sides)


def tube(points, radii, sides):
    p = np.asarray(points, np.float64)
    r = np.broadcast_to(np.asarray(radii, np.float64), (len(p),))
    t = np.gradient(p, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-9
    ref = np.where(np.abs(t[:, 2:3]) > 0.95, [[1.0, 0.0, 0.0]], [[0.0, 0.0, 1.0]])
    n = np.cross(t, ref)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    b = np.cross(t, n)
    ang = TAU * np.arange(sides) / sides
    v = (p[:, None, :] + r[:, None, None] * (np.cos(ang)[None, :, None] * n[:, None, :]
                                             + np.sin(ang)[None, :, None] * b[:, None, :]))
    return v.reshape(-1, 3), ring_faces(len(p), sides)


def add_specks(acc, pos, size, col):
    pos = np.asarray(pos, np.float64).reshape(-1, 3)
    if len(pos) == 0:
        return
    size = np.broadcast_to(np.asarray(size, np.float64), (len(pos),))
    v = pos[:, None, :] + size[:, None, None] * OCT_V[None]
    f = OCT_F[None] + (np.arange(len(pos)) * 6)[:, None, None]
    acc.add(v.reshape(-1, 3), f.reshape(-1, 3), np.repeat(np.asarray(col), 6, axis=0))


def pick_colors(rng, palette, n, weights=None, lo=0.6, hi=1.4):
    idx = rng.choice(len(palette), size=n, p=weights)
    return palette[idx] * rng.uniform(lo, hi, (n, 1))


# ---------------------------------------------------------------------------
# materials
# ---------------------------------------------------------------------------

def _fresh(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    return m, nt, nt.nodes.new("ShaderNodeOutputMaterial")


def mat_emissive(name, strength):
    m, nt, out = _fresh(name)
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "col"
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = strength
    nt.links.new(at.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


def mat_surface(name, roughness, metallic=0.0):
    m, nt, out = _fresh(name)
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "col"
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bs.inputs["Roughness"].default_value = roughness
    bs.inputs["Metallic"].default_value = metallic
    nt.links.new(at.outputs["Color"], bs.inputs["Base Color"])
    nt.links.new(bs.outputs["BSDF"], out.inputs["Surface"])
    return m


def mat_water():
    """Glossy dark water with moving ripples and drifting glowing patches."""
    m, nt, out = _fresh("water")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    bs = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bs.inputs["Roughness"].default_value = 0.07
    ripple = nt.nodes.new("ShaderNodeTexNoise")
    ripple.noise_dimensions = "4D"
    ripple.inputs["Scale"].default_value = 0.9
    ripple.inputs["Detail"].default_value = 6.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    nt.links.new(geo.outputs["Position"], ripple.inputs["Vector"])
    nt.links.new(ripple.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bs.inputs["Normal"])

    patch = nt.nodes.new("ShaderNodeTexNoise")
    patch.noise_dimensions = "4D"
    patch.inputs["Scale"].default_value = 0.13
    patch.inputs["Detail"].default_value = 4.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.64
    ramp.color_ramp.elements[0].color = (0, 0, 0, 1)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (1, 1, 1, 1)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 0.0
    glowcol = nt.nodes.new("ShaderNodeMath")        # mask * glow strength
    glowcol.operation = "MULTIPLY"
    glowcol.inputs[1].default_value = 0.55
    nt.links.new(geo.outputs["Position"], patch.inputs["Vector"])
    nt.links.new(patch.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], glowcol.inputs[0])
    nt.links.new(glowcol.outputs["Value"], em.inputs["Strength"])
    add = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(bs.outputs["BSDF"], add.inputs[0])
    nt.links.new(em.outputs["Emission"], add.inputs[1])
    nt.links.new(add.outputs["Shader"], out.inputs["Surface"])
    return m, {"bsdf": bs, "ripple": ripple, "patch": patch, "glow": em}


def mat_fog():
    m, nt, out = _fresh("fog")
    vol = nt.nodes.new("ShaderNodeVolumePrincipled")
    vol.inputs["Anisotropy"].default_value = 0.45
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return m, vol


# ---------------------------------------------------------------------------
# sky: gradient + lit clouds + sun glow + stars, all driven per frame
# ---------------------------------------------------------------------------

def build_sky(scene, sun_dir):
    w = bpy.data.worlds.new("sky")
    scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputWorld")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs["Vector"])   # view direction

    def maprange(src, a, b, c=0.0, d=1.0):
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.clamp = True
        mr.inputs["From Min"].default_value = a
        mr.inputs["From Max"].default_value = b
        mr.inputs["To Min"].default_value = c
        mr.inputs["To Max"].default_value = d
        nt.links.new(src, mr.inputs["Value"])
        return mr

    def math(op, a, b):
        mn = nt.nodes.new("ShaderNodeMath")
        mn.operation = op
        for i, x in enumerate((a, b)):
            if isinstance(x, (int, float)):
                mn.inputs[i].default_value = x
            else:
                nt.links.new(x, mn.inputs[i])
        return mn

    # gradient: horizon -> mid -> zenith
    elev = maprange(sep.outputs["Z"], -0.04, 0.55)
    grad = nt.nodes.new("ShaderNodeValToRGB")
    grad.color_ramp.elements[1].position = 1.0
    grad.color_ramp.elements.new(0.22)
    nt.links.new(elev.outputs["Result"], grad.inputs["Fac"])
    bg_sky = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(grad.outputs["Color"], bg_sky.inputs["Color"])

    # sun direction factor
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(tc.outputs["Generated"], dot.inputs[0])
    dot.inputs[1].default_value = sun_dir
    sunward = maprange(dot.outputs["Value"], -0.3, 1.0)

    # clouds: flattened drifting noise in a band above the horizon
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.7, 1.7, 6.0)
    nt.links.new(tc.outputs["Generated"], mapping.inputs["Vector"])
    cn = nt.nodes.new("ShaderNodeTexNoise")
    cn.noise_dimensions = "4D"
    cn.inputs["Scale"].default_value = 3.2
    cn.inputs["Detail"].default_value = 12.0
    nt.links.new(mapping.outputs["Vector"], cn.inputs["Vector"])
    cover = maprange(cn.outputs["Fac"], 0.515, 0.60)
    band_lo = maprange(sep.outputs["Z"], 0.015, 0.10)
    band_hi = maprange(sep.outputs["Z"], 0.32, 0.62, 1.0, 0.0)
    cmask = math("MULTIPLY", math("MULTIPLY", cover.outputs["Result"],
                                  band_lo.outputs["Result"]).outputs["Value"],
                 band_hi.outputs["Result"])
    cmask2 = math("MULTIPLY", cmask.outputs["Value"], 0.92)
    cramp = nt.nodes.new("ShaderNodeValToRGB")
    nt.links.new(sunward.outputs["Result"], cramp.inputs["Fac"])
    bg_cloud = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(cramp.outputs["Color"], bg_cloud.inputs["Color"])
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(cmask2.outputs["Value"], mix.inputs["Fac"])
    nt.links.new(bg_sky.outputs["Background"], mix.inputs[1])
    nt.links.new(bg_cloud.outputs["Background"], mix.inputs[2])

    # sun glow
    sg = maprange(dot.outputs["Value"], 0.55, 1.0)
    sg_pow = math("POWER", sg.outputs["Result"], 3.0)
    sg_amt = math("MULTIPLY", sg_pow.outputs["Value"], 1.0)
    bg_glow = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(sg_amt.outputs["Value"], bg_glow.inputs["Strength"])

    # stars: tight voronoi points, only above the horizon
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 420.0
    nt.links.new(tc.outputs["Generated"], vor.inputs["Vector"])
    pt = maprange(vor.outputs["Distance"], 0.0, 0.06, 1.0, 0.0)
    pt_pow = math("POWER", pt.outputs["Result"], 10.0)
    above = maprange(sep.outputs["Z"], 0.02, 0.25)
    st_mask = math("MULTIPLY", pt_pow.outputs["Value"], above.outputs["Result"])
    st_amt = math("MULTIPLY", st_mask.outputs["Value"], 1.0)
    bg_star = nt.nodes.new("ShaderNodeBackground")
    bg_star.inputs["Color"].default_value = (1.0, 0.96, 0.92, 1.0)
    nt.links.new(st_amt.outputs["Value"], bg_star.inputs["Strength"])

    a1 = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(mix.outputs["Shader"], a1.inputs[0])
    nt.links.new(bg_glow.outputs["Background"], a1.inputs[1])
    a2 = nt.nodes.new("ShaderNodeAddShader")
    nt.links.new(a1.outputs["Shader"], a2.inputs[0])
    nt.links.new(bg_star.outputs["Background"], a2.inputs[1])
    nt.links.new(a2.outputs["Shader"], out.inputs["Surface"])

    return {"grad": grad, "cramp": cramp, "cloud_noise": cn, "glow": bg_glow,
            "glow_amt": sg_amt, "star_amt": st_amt}


def rgba(c, gain=1.0):
    c = np.clip(np.asarray(c) * gain, 0.0, None)
    return (float(c[0]), float(c[1]), float(c[2]), 1.0)


def update_sky(sky, b, t):
    els = sky["grad"].color_ramp.elements
    els[0].color = rgba(b["horizon"])
    els[1].color = rgba(b["mid"])
    els[2].color = rgba(b["zenith"])
    ce = sky["cramp"].color_ramp.elements
    ce[0].color = rgba(b["cloud_dark"])
    ce[1].color = rgba(b["cloud_lit"])
    sky["cloud_noise"].inputs["W"].default_value = t * 0.0035    # slow drift
    sky["glow"].inputs["Color"].default_value = rgba(b["glow"])
    sky["glow_amt"].inputs[1].default_value = 1.1
    sky["star_amt"].inputs[1].default_value = float(b["stars"]) * 3.0


# ---------------------------------------------------------------------------
# tile content
# ---------------------------------------------------------------------------

def build_tree(rng, base, H, b, acc):
    top = 0.56 * H
    r0 = 0.065 * H
    zs = np.linspace(0.0, top, 16)
    s = zs / top
    r = r0 * (1.0 - 0.5 * s) * (1.0 + 0.9 * np.exp(-zs / (0.06 * H)))
    r *= 1.0 + 0.08 * np.sin(zs * 1.7 + rng.uniform(0, 6))
    v, f = revolve(r, zs, 12, base, twist=rng.uniform(-0.25, 0.25))
    acc["bark"].add(v, f, b["ground"] * 1.4)

    # glowing ribbon spiralling up the trunk
    tt = np.linspace(0.0, 1.0, 80)
    ang = tt * TAU * rng.uniform(1.2, 2.2) + rng.uniform(0, TAU)
    zb = 0.10 * H + tt * top * 0.8
    rb = np.interp(zb, zs, r) * 1.05
    pts = np.stack([rb * np.cos(ang), rb * np.sin(ang), zb], -1) + base
    v, f = tube(pts, 0.016 * H * (1.0 - 0.5 * tt), 6)
    acc["band"].add(v, f, b["band"])

    # luminous lampshade canopy: brightest at the throat, fading outward
    hc = 0.24 * H
    R = rng.uniform(0.42, 0.62) * H
    q = np.linspace(0.0, 1.0, 18)
    zh = top + q * hc
    rh = r[-1] + (R - r[-1]) * q ** 2.1
    v, f = revolve(rh, zh, 40, base)
    ca, cb = b["canopy"][0], b["canopy"][1]
    qq = np.repeat(q, 40)[:, None]
    cols = ca * (1.0 - qq) ** 1.4 * 1.6 + cb * qq ** 2 * 0.35
    acc["horn"].add(v, f, cols)

    # ribs strung with fairy lights
    nrib = int(rng.integers(26, 44))
    lights_p, lights_c, lights_s = [], [], []
    for k in range(nrib):
        th = TAU * k / nrib + rng.normal(0.0, 0.03)
        u = np.linspace(0.0, 1.14, 24)
        uc = np.clip(u, 0.0, 1.0)
        rr = np.where(u <= 1.0, r[-1] + (R - r[-1]) * uc ** 2.1, R + (u - 1.0) * 0.4 * R)
        zz = np.where(u <= 1.0, top + uc * hc, top + hc - (u - 1.0) * 0.55 * hc)
        rr = rr + 0.012 * H
        pts = np.stack([rr * np.cos(th), rr * np.sin(th), zz], -1) + base
        v, f = tube(pts, 0.0045 * H, 3)
        acc["rib"].add(v, f, b["ground"] * 0.8)
        # lights along the rib, spaced ~0.35 m
        seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
        L = np.concatenate([[0.0], np.cumsum(seg)])
        nl = max(4, int(L[-1] / 0.35))
        d = np.sort(rng.uniform(0.0, L[-1], nl))
        lp = np.stack([np.interp(d, L, pts[:, i]) for i in range(3)], -1)
        lights_p.append(lp)
        lights_s.append(rng.uniform(0.004, 0.008, nl) * H)
        lights_c.append(pick_colors(rng, np.stack([ca, cb, b["speck"][0]]), nl,
                                    [0.4, 0.45, 0.15], 0.7, 1.5))
    add_specks(acc["speck"], np.concatenate(lights_p), np.concatenate(lights_s),
               np.concatenate(lights_c))

    # sparkles clinging to the trunk
    m = int(60 + 5 * H)
    zt = rng.uniform(0.0, top, m)
    at = rng.uniform(0.0, TAU, m)
    rt = np.interp(zt, zs, r) * 1.02
    add_specks(acc["speck"],
               np.stack([rt * np.cos(at), rt * np.sin(at), zt], -1) + base,
               rng.uniform(0.003, 0.006, m) * H,
               pick_colors(rng, b["speck"], m))


def build_mushroom(pos, h, capr, col, acc):
    sr = capr * 0.22
    pr = [sr * 1.35, sr, sr * 0.9, capr * 0.95, capr, capr * 0.75, capr * 0.25, 0.001]
    pz = [0.0, 0.10 * h, 0.78 * h, 0.80 * h, 0.88 * h, 0.97 * h, 1.0 * h, 1.0 * h]
    v, f = revolve(pr, pz, 12, pos)
    rows = np.repeat(np.arange(len(pr)), 12)[:, None]
    cols = np.where(rows < 3, col * 0.35, col)        # dim stem, bright cap
    acc["fungus"].add(v, f, cols)


def build_plant(rng, pos, h, col, acc):
    for _ in range(int(rng.integers(4, 8))):
        a0 = rng.uniform(0.0, TAU)
        spread = rng.uniform(0.05, 0.35) * h
        curl = rng.uniform(-3.0, 3.0)
        t = np.linspace(0.0, 1.0, 14)
        pts = np.stack([spread * t * np.cos(a0 + curl * t),
                        spread * t * np.sin(a0 + curl * t),
                        h * t * (1.0 - 0.15 * t)], -1) + pos
        v, f = tube(pts, 0.012 * (1.0 - 0.6 * t) + 0.004, 4)
        acc["plant"].add(v, f, col)
        add_specks(acc["plant"], pts[-1:], [0.035], col[None] * 1.3)


def build_lamp_stalk(rng, pos, h, orb_col, b, acc):
    """A tall curving stem with a glowing orb on top (like shot 2's lamps)."""
    lean = rng.uniform(0.0, 0.12) * h
    ang = rng.uniform(0.0, TAU)
    t = np.linspace(0.0, 1.0, 16)
    bend = lean * t ** 2
    pts = np.stack([bend * np.cos(ang), bend * np.sin(ang), h * t], -1) + pos
    v, f = tube(pts, 0.05 * (1.0 - 0.6 * t) + 0.015, 5)
    acc["rib"].add(v, f, b["ground"] * 1.2)
    # sparkles climbing the stem, then the orb itself
    n = int(8 + 4 * h)
    d = rng.uniform(0.05, 0.95, n)
    sp = np.stack([np.interp(d, t, pts[:, i]) for i in range(3)], -1)
    sp += rng.normal(0.0, 0.05, sp.shape)
    add_specks(acc["speck"], sp, rng.uniform(0.02, 0.05, n),
               pick_colors(rng, b["speck"], n))
    add_specks(acc["orb"], pts[-1:] + [0.0, 0.0, 0.12], [rng.uniform(0.22, 0.4)],
               orb_col[None])


def build_rock_pillar(rng, pos, h, col, acc):
    """Stacked, weathered sandstone hoodoo (like shot 4's red pillars)."""
    rows = 20
    zs = np.linspace(0.0, h, rows)
    base_r = rng.uniform(0.18, 0.3) * h
    s = zs / h
    # a few ledges where softer layers eroded back
    ledges = sum(0.12 * np.exp(-((s - c) / 0.05) ** 2) for c in rng.uniform(0.2, 0.9, 3))
    r = base_r * (1.0 - 0.35 * s) * (1.0 - ledges) * (1.0 + 0.1 * rng.normal(0, 1, rows))
    r[-1] = r[-2] * 0.6                       # rounded cap
    v, f = revolve(np.clip(r, 0.05, None), zs, 10, pos, twist=rng.uniform(-0.2, 0.2))
    layers = 0.8 + 0.25 * np.sin(np.repeat(zs, 10) * rng.uniform(2.0, 4.0))
    acc["rock"].add(v, f, col[None, :] * layers[:, None])


def build_tile(idx, seed, track, mats, coll):
    rng = np.random.default_rng([seed, idx + 1000003])
    y0 = idx * TILE
    b = track.at(y0 + TILE * 0.5)
    acc = {k: Accum() for k in ("speck", "bark", "band", "horn", "rib",
                                "fungus", "plant", "orb", "rock")}

    # --- terrain: fine near the path, coarse far out, no T-junctions ---
    xs = np.concatenate([np.arange(-300.0, -70.0, 5.0), np.arange(-70.0, 70.0, 1.0),
                         np.arange(70.0, 300.001, 5.0)])
    ys = np.arange(y0, y0 + TILE + 0.001, 1.0)
    X, Y = np.meshgrid(xs, ys, indexing="xy")
    Z = terrain(X, Y, seed)
    verts = np.stack([X, Y, Z], -1).reshape(-1, 3)
    nx, ny = len(xs), len(ys)
    i = np.arange(nx - 1)[None, :]
    j = np.arange(ny - 1)[:, None]
    a = j * nx + i
    faces = np.concatenate([np.stack([a, a + 1, a + nx + 1], -1).reshape(-1, 3),
                            np.stack([a, a + nx + 1, a + nx], -1).reshape(-1, 3)])
    tone = 0.55 + 0.9 * fbm(X / 3.0, Y / 3.0, seed + 21, 3)
    wet = smoothstep(-0.2, 0.6, Z)
    gcol = (b["ground"][None, None, :] * b["ground_gain"]
            * (tone * (0.45 + 0.55 * wet))[..., None]).reshape(-1, 3)
    normals = terrain_normals(X, Y, seed).reshape(-1, 3)
    me = build_mesh(f"terrain{idx}", verts, faces,
                    np.concatenate([gcol, np.ones((len(gcol), 1))], 1), normals)
    objs = [_link(f"terrain{idx}", me, mats["ground"], coll)]

    cx = lambda yy: channel_x(yy)

    # --- ground specks: dense and small near the path, sparser and larger
    # far away so they never shrink below a pixel and shimmer ---
    for n, lo, hi, smin, smax in ((5200, 3.0, 55.0, 0.030, 0.085),
                                  (2600, 55.0, 170.0, 0.12, 0.26)):
        yy = rng.uniform(y0, y0 + TILE, n)
        off = rng.uniform(lo, hi, n) * rng.choice([-1.0, 1.0], n)
        xx = cx(yy) + off
        hh = terrain(xx, yy, seed)
        keep = hh > WATER + 0.04
        pos = np.stack([xx, yy, hh + 0.02], -1)[keep]
        add_specks(acc["speck"], pos, rng.uniform(smin, smax, keep.sum()),
                   pick_colors(rng, b["speck"], int(keep.sum()), [0.45, 0.35, 0.20]))

    # --- supertrees ---
    for _ in range(int(rng.poisson(1.05))):
        yy = rng.uniform(y0, y0 + TILE)
        off = rng.uniform(16.0, 150.0) * rng.choice([-1.0, 1.0])
        xx = float(cx(yy)) + off
        hg = float(terrain(xx, yy, seed))
        if hg < -1.2:
            continue
        H = rng.uniform(14.0, 40.0) * (1.0 + 0.35 * (abs(off) > 80))
        build_tree(rng, (xx, yy, max(hg, WATER) - 0.4), H, b, acc)

    # --- fungus clusters and neon tendril plants along the banks ---
    for _ in range(int(rng.poisson(11))):
        yy = rng.uniform(y0, y0 + TILE)
        xx = float(cx(yy)) + rng.uniform(7.0, 32.0) * rng.choice([-1.0, 1.0])
        for _ in range(int(rng.integers(3, 8))):
            px, py = xx + rng.normal(0, 0.9), yy + rng.normal(0, 0.9)
            hg = float(terrain(px, py, seed))
            if hg < WATER + 0.05:
                continue
            h = rng.uniform(0.25, 1.4)
            col = b["fungus"][rng.integers(3)] * rng.uniform(0.8, 1.3)
            build_mushroom((px, py, hg - 0.03), h, h * rng.uniform(0.35, 0.6), col, acc)
    for _ in range(int(rng.poisson(7))):
        yy = rng.uniform(y0, y0 + TILE)
        xx = float(cx(yy)) + rng.uniform(6.0, 40.0) * rng.choice([-1.0, 1.0])
        hg = float(terrain(xx, yy, seed))
        if hg < WATER + 0.05:
            continue
        build_plant(rng, (xx, yy, hg), rng.uniform(0.5, 2.2),
                    b["fungus"][rng.integers(3)] * 1.2, acc)

    # --- lamp stalks with glowing orbs ---
    for _ in range(int(rng.poisson(2.2))):
        yy = rng.uniform(y0, y0 + TILE)
        xx = float(cx(yy)) + rng.uniform(8.0, 70.0) * rng.choice([-1.0, 1.0])
        hg = float(terrain(xx, yy, seed))
        if hg < WATER + 0.05:
            continue
        orb = b["orb"] if rng.random() < 0.6 else b["canopy"][rng.integers(2)] * 1.3
        build_lamp_stalk(rng, (xx, yy, hg - 0.05), rng.uniform(2.5, 7.0), orb, b, acc)

    # --- red rock pillars standing in the middle distance ---
    for _ in range(int(rng.poisson(0.55))):
        yy = rng.uniform(y0, y0 + TILE)
        xx = float(cx(yy)) + rng.uniform(30.0, 140.0) * rng.choice([-1.0, 1.0])
        hg = float(terrain(xx, yy, seed))
        if hg < WATER - 0.5:
            continue
        build_rock_pillar(rng, (xx, yy, hg - 0.8), rng.uniform(8.0, 26.0),
                          b["rock"] * rng.uniform(0.8, 1.2), acc)

    # --- floating orbs ---
    for _ in range(int(rng.poisson(1.6))):
        yy = rng.uniform(y0, y0 + TILE)
        xx = float(cx(yy)) + rng.uniform(5.0, 60.0) * rng.choice([-1.0, 1.0])
        hg = max(float(terrain(xx, yy, seed)), WATER)
        add_specks(acc["orb"], [(xx, yy, hg + rng.uniform(2.0, 9.0))],
                   [rng.uniform(0.18, 0.45)], b["orb"][None])

    for key, a_ in acc.items():
        me = a_.build(f"{key}{idx}")
        if me is not None:
            objs.append(_link(f"{key}{idx}", me, mats[key], coll))
    return objs


def _link(name, me, mat, coll):
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    return ob


# ---------------------------------------------------------------------------
# scene assembly
# ---------------------------------------------------------------------------

class World:
    def __init__(self, args):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = scene = bpy.context.scene
        self.seed = args.seed % 2147483647
        self.speed = SPEED * args.speed
        self.track = BiomeTrack(self.seed)
        self.tiles = {}
        self.coll = scene.collection

        self.engine = set_engine(scene, args.engine)
        r = scene.render
        r.resolution_x, r.resolution_y = args.width, args.height
        r.resolution_percentage = 100
        r.fps = int(round(args.fps))
        setp(r, "use_motion_blur", False)
        vs = scene.view_settings
        setp(vs, "view_transform", "Standard")   # keeps neon colors saturated
        setp(vs, "look", "None")
        ee = scene.eevee
        setp(ee, "taa_render_samples", args.samples)
        setp(ee, "use_ssr", True)                # reflections, EEVEE <= 4.1
        setp(ee, "use_raytracing", True)         # reflections, EEVEE 4.2+
        setp(ee, "use_gtao", True)
        setp(ee, "volumetric_start", 0.5)
        setp(ee, "volumetric_end", 440.0)
        setp(ee, "volumetric_tile_size", "8")
        setp(ee, "volumetric_samples", 48)
        setp(ee, "use_volumetric_shadows", False)
        if self.engine == "CYCLES":
            scene.cycles.samples = args.samples * 4
            setp(scene.cycles, "use_denoising", False)

        self.mats = {
            "ground": mat_surface("ground", 0.85),
            "bark": mat_surface("bark", 0.6),
            "rib": mat_surface("rib", 0.35, 0.6),
            "speck": mat_emissive("speck", 1.7),
            "band": mat_emissive("band", 1.5),
            "horn": mat_emissive("horn", 1.3),
            "fungus": mat_emissive("fungus", 1.25),
            "plant": mat_emissive("plant", 2.2),
            "orb": mat_emissive("orb", 3.2),
            "rock": mat_surface("rock", 0.8),
        }

        # sun low and ahead-right: the sunset glow sits in the view
        az, el = math.radians(28.0), math.radians(4.0)
        self.sun_dir = Vector((math.sin(az) * math.cos(el),
                               math.cos(az) * math.cos(el), math.sin(el)))
        self.sky = build_sky(scene, tuple(self.sun_dir))
        sl = bpy.data.lights.new("sun", "SUN")
        sl.angle = 0.03
        self.sun = bpy.data.objects.new("sun", sl)
        self.sun.rotation_euler = self.sun_dir.to_track_quat("Z", "Y").to_euler()
        self.coll.objects.link(self.sun)

        # water: one big plane re-centred under the camera every frame
        wm, self.water = mat_water()
        me = build_mesh("water", [(-700, -700, 0), (700, -700, 0), (700, 700, 0),
                                  (-700, 700, 0)], [(0, 1, 2), (0, 2, 3)])
        self.water_obj = _link("water", me, wm, self.coll)

        # atmospheric haze: a volume box that travels with the camera
        fm, self.fog = mat_fog()
        v, f = revolve([0.001, 1.0, 1.0, 0.001], [-1.0, -1.0, 1.0, 1.0], 4, (0, 0, 0))
        me = build_mesh("fogbox", v, f)
        self.fog_obj = _link("fogbox", me, fm, self.coll)
        self.fog_obj.scale = (560.0, 560.0, 22.0)
        self.fog_obj.rotation_euler = (0.0, 0.0, math.pi / 4)

        cd = bpy.data.cameras.new("cam")
        cd.lens = 24.0
        cd.clip_start = 0.1
        cd.clip_end = 900.0
        cd.dof.use_dof = True
        cd.dof.focus_distance = 14.0
        cd.dof.aperture_fstop = 5.6
        self.cam = bpy.data.objects.new("cam", cd)
        self.coll.objects.link(self.cam)
        scene.camera = self.cam

    # --- per-frame -------------------------------------------------------
    def camera_at(self, t):
        yc = self.speed * t
        wob = lambda tt: 1.2 * math.sin(tt * 0.05)
        x = float(channel_x(yc)) + wob(t)
        z = WATER + 1.30 + 0.18 * math.sin(t * 0.27) + 0.10 * math.sin(t * 0.61)
        ahead = 18.0
        xa = float(channel_x(yc + ahead)) + wob(t + ahead / self.speed)
        yaw = -math.atan2(xa - x, ahead)
        pitch = 0.055 + 0.02 * math.sin(t * 0.07)
        roll = 0.012 * math.sin(t * 0.09)
        return (x, yc, z), (math.pi / 2 + pitch, roll, yaw)

    def stream(self, yc):
        want = set(range(int(math.floor((yc - 40.0) / TILE)),
                         int(math.floor((yc + VIEW) / TILE)) + 1))
        for idx in [i for i in self.tiles if i not in want]:
            for ob in self.tiles.pop(idx):
                me = ob.data
                bpy.data.objects.remove(ob, do_unlink=True)
                bpy.data.meshes.remove(me)
        for idx in sorted(want - set(self.tiles)):
            self.tiles[idx] = build_tile(idx, self.seed, self.track, self.mats, self.coll)

    def update(self, t):
        loc, rot = self.camera_at(t)
        self.cam.location = loc
        self.cam.rotation_euler = rot
        self.stream(loc[1])

        b = self.track.at(loc[1])
        update_sky(self.sky, b, t)
        self.sun.data.color = rgba(b["sun"])[:3]
        self.sun.data.energy = float(b["sun_energy"])
        self.water_obj.location = (loc[0], loc[1], WATER)
        self.water["bsdf"].inputs["Base Color"].default_value = rgba(b["water"])
        self.water["ripple"].inputs["W"].default_value = t * 0.35
        self.water["patch"].inputs["W"].default_value = t * 0.02
        self.water["glow"].inputs["Color"].default_value = rgba(b["water_glow"])
        self.fog_obj.location = (loc[0], loc[1], 12.0)
        self.fog.inputs["Color"].default_value = rgba(b["fog"])
        self.fog.inputs["Density"].default_value = float(b["fog_density"])
        if self.engine == "CYCLES":
            self.scene.cycles.seed = int(t * 1000) % 100000

    def render_to(self, path):
        tmp = path + ".part.jpg" if path.endswith(".jpg") else path + ".part.png"
        self.scene.render.filepath = tmp
        bpy.ops.render.render(write_still=True)
        os.replace(tmp, path)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=1)
    ap.add_argument("--outdir", default="frames")
    ap.add_argument("--still", type=float, default=None, help="render one PNG at t seconds")
    ap.add_argument("--out", default="still.png")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--samples", type=int, default=16)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--engine", default="eevee", choices=["eevee", "cycles"])
    args = ap.parse_args(argv)

    world = World(args)
    print(f"BLENDER {bpy.app.version_string} ENGINE {world.engine}", flush=True)
    img = world.scene.render.image_settings

    if args.still is not None:
        img.file_format = "PNG"
        world.update(args.still)
        out = os.path.abspath(args.out)
        world.render_to(out)
        print("STILL", out, flush=True)
        return

    img.file_format = "JPEG"
    setp(img, "quality", 95)
    os.makedirs(args.outdir, exist_ok=True)
    for f in range(args.start, args.end):
        path = os.path.abspath(os.path.join(args.outdir, f"f_{f:07d}.jpg"))
        if os.path.exists(path) and os.path.getsize(path) > 0:
            continue                                     # already done: resume
        t0 = time.time()
        world.update(f / args.fps)
        world.render_to(path)
        print(f"FRAME {f} {time.time() - t0:.2f}", flush=True)


if __name__ == "__main__":
    main()
