"""3D Kaleidoscope — an endless flight down a tunnel of mirrored jewels.

Render inside Blender (4.2 LTS or newer recommended; also runs on 4.0 and 5.x):

    blender -b --factory-startup -P kaleidoscope.py -- --start 0 --end 240 \\
        --outdir frames --width 1920 --height 1080 --fps 24 --seed 1

    blender -b --factory-startup -P kaleidoscope.py -- --still 5 --out look.png

How it is kaleidoscopic in real 3D: each ring of the tunnel is ONE wedge of
content — faceted jewels, glowing filaments, light beads — copied around the
tunnel axis, every other copy mirrored. Seen from the axis that is exactly
the symmetry of a mirror kaleidoscope, but with real depth, reflections and
parallax. Alternate rings turn in opposite directions and the jewels spin in
perfect sync, so the pattern keeps rearranging itself. New rings arrive with
different symmetry (6/8/10/12-fold) and colors drift through curated
palettes, so the view never settles into a loop.

Deep blacks: the world is pure black and every material fades to black with
distance from the camera, so rings are born invisibly in the dark far ahead.

Seamless: everything is a pure function of (seed, time). Rings are built as
they come into view and deleted behind the camera, so memory stays flat and
separately rendered frame ranges join perfectly.
"""

import argparse
import math
import os
import sys
import time

import bpy
import numpy as np

TAU = 2.0 * math.pi
SEG = 1.6            # distance between rings (Blender units)
RADIUS = 3.0         # tunnel radius
VIEW = 34.0          # rings exist this far ahead (they are pitch black by then)
FADE_NEAR, FADE_FAR = 6.0, 24.0   # full brightness -> black
LENS_FADE = (0.15, 0.8)           # objects this close to the lens fade out
SPEED = 0.95         # camera travel per second: a slow glide


# ---------------------------------------------------------------------------
# version-proofing: Blender renamed engines and shader inputs across 4.x/5.x
# ---------------------------------------------------------------------------

def setp(obj, attr, value):
    try:
        if obj is not None and hasattr(obj, attr):
            setattr(obj, attr, value)
            return True
    except (AttributeError, TypeError, ValueError):
        pass
    return False


def sock(node, *names):
    """First input socket that exists under any of the given names."""
    for n in names:
        if n in node.inputs:
            return node.inputs[n]
    return None


def set_eevee(scene):
    for eid in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = eid
            return eid
        except TypeError:
            continue
    raise RuntimeError("EEVEE not found in this Blender")


# ---------------------------------------------------------------------------
# deterministic randomness
# ---------------------------------------------------------------------------

def rng_for(seed, *key):
    return np.random.default_rng([seed & 0x7FFFFFFF] + [int(k) & 0x7FFFFFFF for k in key])


def srgb(h):
    h = h.lstrip("#")
    c = np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


# Rich jewel palettes: two dominant hues plus an accent. Colors are chosen
# to stay saturated against black (no muddy mid-tones).
PALETTES = [
    [srgb(c) for c in ("#ff1f8e", "#12e0ff", "#ffd23f")],   # magenta / cyan / gold
    [srgb(c) for c in ("#7a2cff", "#ff6a00", "#35ffd0")],   # violet / amber / mint
    [srgb(c) for c in ("#00ff9c", "#ff2a55", "#4d7cff")],   # emerald / ruby / sapphire
    [srgb(c) for c in ("#2f6bff", "#ffb000", "#ff3df5")],   # sapphire / amber / pink
    [srgb(c) for c in ("#ff3b1f", "#b400ff", "#00d9ff")],   # ember / purple / ice
    [srgb(c) for c in ("#00ffd5", "#ff00a8", "#fff06a")],   # aqua / fuchsia / lemon
]


def smootherstep(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * x * (x * (x * 6.0 - 15.0) + 10.0)


class Journey:
    """What the tunnel looks like at each distance along it: palette blend and
    symmetry order. Waypoints every 45-90 units (roughly 50-95 s of flight)."""

    def __init__(self, seed):
        rng = rng_for(seed, 11)
        self.ys, self.pal, self.sym = [-50.0], [int(rng.integers(len(PALETTES)))], [8]
        y = -50.0
        while y < 40000.0:                            # far beyond 3 h of travel
            y += float(rng.uniform(45.0, 90.0))
            p = int(rng.integers(len(PALETTES) - 1))
            if p >= self.pal[-1]:
                p += 1
            self.ys.append(y)
            self.pal.append(p)
            self.sym.append(int(rng.choice([6, 8, 8, 10, 12])))

    def at(self, y):
        i = int(np.clip(np.searchsorted(self.ys, y) - 1, 0, len(self.ys) - 2))
        f = smootherstep((y - self.ys[i]) / (self.ys[i + 1] - self.ys[i]))
        a, b = PALETTES[self.pal[i]], PALETTES[self.pal[i + 1]]
        colors = [ca + (cb - ca) * f for ca, cb in zip(a, b)]
        sym = self.sym[i] if f < 0.5 else self.sym[i + 1]
        return colors, sym


# ---------------------------------------------------------------------------
# mesh building
# ---------------------------------------------------------------------------

def make_mesh(name, verts, faces, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in verts], [], [tuple(map(int, f)) for f in faces])
    me.update()
    for p in me.polygons:
        p.use_smooth = smooth
    return me


def gem_mesh(name, kind, rng):
    """Faceted jewel shapes, centred on the origin, about 1 unit across."""
    if kind == 0:     # brilliant cut: table, crown, girdle, pavilion point
        n = 8
        ang = TAU * np.arange(n) / n
        table = np.stack([0.28 * np.cos(ang), 0.28 * np.sin(ang), np.full(n, 0.22)], 1)
        girdle = np.stack([0.5 * np.cos(ang + TAU / 16), 0.5 * np.sin(ang + TAU / 16),
                           np.zeros(n)], 1)
        verts = np.concatenate([table, girdle, [[0, 0, -0.55]], [[0, 0, 0.22]]])
        faces = []
        for i in range(n):
            j = (i + 1) % n
            faces.append([2 * n + 1, i, j][::-1])           # table fan
            faces.append([i, n + i, j])                      # crown
            faces.append([j, n + i, n + j])
            faces.append([n + i, 2 * n, n + j])              # pavilion
        return make_mesh(name, verts, faces)
    if kind == 1:     # elongated octahedral crystal
        s = rng.uniform(0.7, 1.3)
        verts = [(0.35, 0, 0), (-0.35, 0, 0), (0, 0.35, 0), (0, -0.35, 0),
                 (0, 0, 0.6 * s), (0, 0, -0.6 * s)]
        faces = [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4),
                 (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]
        return make_mesh(name, verts, faces)
    # kind 2: faceted "geode" — a lumpy icosahedron
    t = (1 + 5 ** 0.5) / 2
    v = np.array([(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t),
                  (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)], float)
    v /= np.linalg.norm(v[0])
    v *= 0.42 * rng.uniform(0.85, 1.15, (12, 1))
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4),
         (11, 10, 2), (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8),
         (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    return make_mesh(name, v, f)


def tube(points, radius, sides=6):
    p = np.asarray(points, float)
    tng = np.gradient(p, axis=0)
    tng /= np.linalg.norm(tng, axis=1, keepdims=True) + 1e-9
    ref = np.where(np.abs(tng[:, 1:2]) > 0.9, [[1.0, 0, 0]], [[0, 1.0, 0]])
    n = np.cross(tng, ref)
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    b = np.cross(tng, n)
    ang = TAU * np.arange(sides) / sides
    r = np.broadcast_to(np.asarray(radius, float), (len(p),))
    v = p[:, None, :] + r[:, None, None] * (np.cos(ang)[None, :, None] * n[:, None, :]
                                            + np.sin(ang)[None, :, None] * b[:, None, :])
    faces = []
    for k in range(len(p) - 1):
        for s in range(sides):
            a0, a1 = k * sides + s, k * sides + (s + 1) % sides
            faces.append((a0, a1, a1 + sides, a0 + sides))
    return v.reshape(-1, 3), faces


def uv_sphere(center, r, rows=6, sides=8):
    verts, faces = [], []
    for i in range(1, rows):
        th = math.pi * i / rows
        for s in range(sides):
            ph = TAU * s / sides
            verts.append((center[0] + r * math.sin(th) * math.cos(ph),
                          center[1] + r * math.cos(th),
                          center[2] + r * math.sin(th) * math.sin(ph)))
    top, bot = len(verts), len(verts) + 1
    verts += [(center[0], center[1] + r, center[2]), (center[0], center[1] - r, center[2])]
    for i in range(rows - 2):
        for s in range(sides):
            a, b = i * sides + s, i * sides + (s + 1) % sides
            faces.append((a, b, b + sides, a + sides))
    for s in range(sides):
        faces.append((top, (s + 1) % sides, s))
        last = (rows - 2) * sides
        faces.append((bot, last + s, last + (s + 1) % sides))
    return verts, faces


# ---------------------------------------------------------------------------
# materials: shared, colored per object (Object Info > Color), faded to black
# with distance (Camera Data > View Distance)
# ---------------------------------------------------------------------------

def _fade_factor(nt):
    cam = nt.nodes.new("ShaderNodeCameraData")
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.clamp = True
    mr.inputs["From Min"].default_value = FADE_NEAR
    mr.inputs["From Max"].default_value = FADE_FAR
    mr.inputs["To Min"].default_value = 1.0
    mr.inputs["To Max"].default_value = 0.0
    nt.links.new(cam.outputs["View Distance"], mr.inputs["Value"])
    sq = nt.nodes.new("ShaderNodeMath")          # ease out: stays bright, then drops
    sq.operation = "POWER"
    sq.inputs[1].default_value = 2.0
    nt.links.new(mr.outputs["Result"], sq.inputs[0])
    # and fade out anything brushing past the lens: huge out-of-focus blobs
    # at the frame edges would drown the pattern
    near = nt.nodes.new("ShaderNodeMapRange")
    near.clamp = True
    near.inputs["From Min"].default_value = LENS_FADE[0]
    near.inputs["From Max"].default_value = LENS_FADE[1]
    near.inputs["To Min"].default_value = 0.0
    near.inputs["To Max"].default_value = 1.0
    nt.links.new(cam.outputs["View Distance"], near.inputs["Value"])
    both = nt.nodes.new("ShaderNodeMath")
    both.operation = "MULTIPLY"
    nt.links.new(sq.outputs["Value"], both.inputs[0])
    nt.links.new(near.outputs["Result"], both.inputs[1])
    return both.outputs["Value"]


def _mul(nt, a, b):
    m = nt.nodes.new("ShaderNodeMath")
    m.operation = "MULTIPLY"
    for i, x in enumerate((a, b)):
        if isinstance(x, (int, float)):
            m.inputs[i].default_value = x
        else:
            nt.links.new(x, m.inputs[i])
    return m.outputs["Value"]


def _vmul(nt, color, factor):
    m = nt.nodes.new("ShaderNodeVectorMath")
    m.operation = "SCALE"
    nt.links.new(color, m.inputs[0])
    if isinstance(factor, (int, float)):
        m.inputs["Scale"].default_value = factor
    else:
        nt.links.new(factor, m.inputs["Scale"])
    return m.outputs["Vector"]


def mat_jewel():
    m = bpy.data.materials.new("jewel")
    m.use_nodes = True
    nt = m.node_tree
    bs = nt.nodes["Principled BSDF"]
    info = nt.nodes.new("ShaderNodeObjectInfo")
    fade = _fade_factor(nt)
    nt.links.new(_vmul(nt, info.outputs["Color"], _mul(nt, fade, 0.35)), bs.inputs["Base Color"])
    bs.inputs["Roughness"].default_value = 0.03
    # partly metallic: facets turned away from the lights go dark while the
    # rest flash — the dark/bright contrast is what makes a cut gem read
    bs.inputs["Metallic"].default_value = 0.45
    setp(sock(bs, "IOR"), "default_value", 2.4)                 # diamond-like
    setp(sock(bs, "Specular IOR Level", "Specular"), "default_value", 1.0)
    setp(sock(bs, "Coat Weight", "Clearcoat"), "default_value", 1.0)
    setp(sock(bs, "Coat Roughness", "Clearcoat Roughness"), "default_value", 0.02)
    # inner fire: facets glow faintly in their own color, brighter at grazing
    # angles (Fresnel), so the jewels read even where nothing lights them
    fres = nt.nodes.new("ShaderNodeLayerWeight")
    fres.inputs["Blend"].default_value = 0.35
    glow = _mul(nt, _mul(nt, fres.outputs["Facing"], fade), 1.2)
    ec = sock(bs, "Emission Color", "Emission")
    nt.links.new(info.outputs["Color"], ec)
    nt.links.new(glow, sock(bs, "Emission Strength"))
    return m


def mat_glow(name, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    info = nt.nodes.new("ShaderNodeObjectInfo")
    fade = _fade_factor(nt)
    nt.links.new(info.outputs["Color"], em.inputs["Color"])
    nt.links.new(_mul(nt, fade, strength), em.inputs["Strength"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


# ---------------------------------------------------------------------------
# rings
# ---------------------------------------------------------------------------

class Ring:
    """One kaleidoscopic ring: a wedge of content, copied 2N times around the
    tunnel axis (every other copy mirrored)."""

    def __init__(self, world, k):
        self.k = k
        seed = world.seed
        rng = rng_for(seed, 700001, k)
        y = k * SEG
        colors, n = world.journey.at(y)
        self.n = n
        self.objects, self.meshes, self.spinners = [], [], []
        self.dir = 1.0 if k % 2 == 0 else -1.0
        self.phase = float(rng.uniform(0, TAU))
        self.turn_rate = float(rng.uniform(0.6, 1.0)) * TAU / (n * 22.0)  # radians/s
        wedge = math.pi / n

        root = bpy.data.objects.new(f"ring{k}", None)
        root.location = (0.0, y, 0.0)
        world.coll.objects.link(root)
        self.root = root
        self.objects.append(root)

        # --- wedge content (in the wedge's local frame: XZ is the ring plane,
        # angle measured from +X towards +Z, inside [0, pi/n]) ---
        pieces = []                       # (mesh, material, color, location, spin)
        n_jewels = int(rng.integers(2, 6))
        for j in range(n_jewels):
            kind = int(rng.integers(0, 3))
            me = gem_mesh(f"gem{k}_{j}", kind, rng)
            self.meshes.append(me)
            th = rng.uniform(0.12, 0.88) * wedge
            r = rng.uniform(1.25, RADIUS - 0.3)
            dy = rng.uniform(-0.45, 0.45) * SEG
            size = rng.uniform(0.12, 0.5) ** 1.3 * 1.6 * (0.6 + 0.4 * r / RADIUS)
            col = colors[int(rng.choice(3, p=[0.45, 0.4, 0.15]))] * rng.uniform(0.85, 1.25)
            spin_axis = rng.normal(0, 1, 3)
            spin_axis /= np.linalg.norm(spin_axis)
            spin_rate = rng.uniform(0.25, 0.7) * rng.choice([-1, 1])
            pieces.append((me, world.mats["jewel"], col, (r * math.cos(th), dy, r * math.sin(th)),
                           size, (spin_axis, spin_rate, rng.uniform(0, TAU))))

        # glowing filament arcing through the wedge, strung with light beads
        verts_f, faces_f = [], []
        verts_b, faces_b = [], []
        for f in range(int(rng.integers(1, 3))):
            t = np.linspace(0.0, 1.0, 24)
            r0, r1 = rng.uniform(1.35, 2.0), rng.uniform(RADIUS - 0.6, RADIUS - 0.05)
            th0, th1 = rng.uniform(0.0, 1.0) * wedge, rng.uniform(0.0, 1.0) * wedge
            rr = r0 + (r1 - r0) * t
            th = th0 + (th1 - th0) * t + 0.25 * wedge * np.sin(t * math.pi * rng.uniform(1, 2.5))
            yy = rng.uniform(-0.4, 0.4) * SEG + 0.35 * np.sin(t * math.pi * 2 + rng.uniform(0, TAU))
            pts = np.stack([rr * np.cos(th), yy, rr * np.sin(th)], 1)
            v, fc = tube(pts, 0.008 + 0.006 * np.sin(t * math.pi), 6)
            base = len(verts_f)
            verts_f += [tuple(x) for x in v]
            faces_f += [tuple(i + base for i in q) for q in fc]
            for tb in np.sort(rng.uniform(0.1, 0.95, int(rng.integers(3, 7)))):
                c = pts[int(tb * (len(pts) - 1))]
                v, fc = uv_sphere(c, rng.uniform(0.022, 0.045))
                base = len(verts_b)
                verts_b += v
                faces_b += [tuple(i + base for i in q) for q in fc]
        fil_col = colors[int(rng.integers(0, 3))] * 1.0
        bead_col = colors[2] * 1.2
        if verts_f:
            me = make_mesh(f"fil{k}", verts_f, faces_f, smooth=True)
            self.meshes.append(me)
            pieces.append((me, world.mats["filament"], fil_col, (0, 0, 0), 1.0, None))
        if verts_b:
            me = make_mesh(f"bead{k}", verts_b, faces_b, smooth=True)
            self.meshes.append(me)
            pieces.append((me, world.mats["bead"], bead_col, (0, 0, 0), 1.0, None))

        # --- replicate the wedge 2n times: rotate, and mirror every other copy
        for c in range(2 * n):
            w = bpy.data.objects.new(f"w{k}_{c}", None)
            w.parent = root
            w.rotation_euler = (0.0, TAU * (c // 2) / n, 0.0)
            if c % 2:
                w.scale = (1.0, 1.0, -1.0)     # the mirror
            world.coll.objects.link(w)
            self.objects.append(w)
            for pi, (me, mat, col, loc, size, spin) in enumerate(pieces):
                ob = bpy.data.objects.new(f"p{k}_{c}_{pi}", me)   # linked duplicate
                if not me.materials:
                    me.materials.append(mat)
                ob.color = (float(col[0]), float(col[1]), float(col[2]), 1.0)
                ob.location = loc
                ob.scale = (size, size, size)
                ob.parent = w
                world.coll.objects.link(ob)
                self.objects.append(ob)
                if spin is not None:
                    self.spinners.append((ob, spin))

        # a thin glowing hoop marks every third ring: rhythm as you fly
        if k % 3 == 0:
            ang = np.linspace(0, TAU, 97)
            pts = np.stack([RADIUS * 1.02 * np.cos(ang), np.zeros_like(ang),
                            RADIUS * 1.02 * np.sin(ang)], 1)
            v, fc = tube(pts, 0.012, 5)
            me = make_mesh(f"hoop{k}", v, fc, smooth=True)
            me.materials.append(world.mats["filament"])
            self.meshes.append(me)
            ob = bpy.data.objects.new(f"hoop{k}", me)
            ob.color = tuple(float(x) for x in colors[1] * 0.8) + (1.0,)
            ob.parent = root
            world.coll.objects.link(ob)
            self.objects.append(ob)

    def update(self, t):
        self.root.rotation_euler = (0.0, self.phase + self.dir * self.turn_rate * t, 0.0)
        for ob, (axis, rate, ph) in self.spinners:
            a = ph + rate * t
            ob.rotation_mode = "AXIS_ANGLE"
            ob.rotation_axis_angle = (a, float(axis[0]), float(axis[1]), float(axis[2]))

    def remove(self):
        for ob in self.objects:
            bpy.data.objects.remove(ob, do_unlink=True)
        for me in self.meshes:
            bpy.data.meshes.remove(me)


# ---------------------------------------------------------------------------
# scene
# ---------------------------------------------------------------------------

class World:
    def __init__(self, args):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = scene = bpy.context.scene
        self.seed = args.seed
        self.speed = SPEED * args.speed
        self.journey = Journey(self.seed)
        self.coll = scene.collection
        self.rings = {}

        self.engine = set_eevee(scene)
        r = scene.render
        r.resolution_x, r.resolution_y = args.width, args.height
        r.resolution_percentage = 100
        r.fps = int(args.fps)
        setp(r, "use_motion_blur", False)
        vs = scene.view_settings
        setp(vs, "view_transform", "Standard")     # saturated neon, true blacks
        setp(vs, "look", "None")
        setp(vs, "exposure", 0.0)
        setp(vs, "gamma", 1.0)
        ee = scene.eevee
        setp(ee, "taa_render_samples", args.samples)
        setp(ee, "use_raytracing", True)            # EEVEE 4.2+: real reflections
        setp(ee, "use_ssr", True)                   # EEVEE 4.0/4.1 reflections
        setp(ee, "use_ssr_refraction", True)
        setp(ee, "use_gtao", False)
        setp(ee, "use_bloom", False)                # glow is added in post (all versions)
        rt = getattr(ee, "ray_tracing_options", None)
        setp(rt, "resolution_scale", "2")
        setp(rt, "use_denoise", True)
        setp(ee, "fast_gi_method", "GLOBAL_ILLUMINATION")

        w = bpy.data.worlds.new("black")
        scene.world = w
        w.use_nodes = True
        bg = w.node_tree.nodes.get("Background")
        bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        bg.inputs["Strength"].default_value = 0.0

        self.mats = {"jewel": mat_jewel(),
                     "filament": mat_glow("filament", 7.0),
                     "bead": mat_glow("bead", 14.0)}

        # A ring of small, bright lights travelling with the camera. In a black
        # world the jewels can only reflect lights, and small bright ones give
        # the sharp white glints that make a cut gem flash as it turns.
        self.lights = []
        for i in range(6):
            a = TAU * (i + 0.5) / 6
            ld = bpy.data.lights.new(f"key{i}", "POINT")
            ld.energy = 140.0
            setp(ld, "shadow_soft_size", 0.12)
            setp(ld, "use_shadow", False)
            # stronger glints without flattening the facets with more fill light
            setp(ld, "specular_factor", 2.5)
            setp(ld, "diffuse_factor", 0.8)
            ob = bpy.data.objects.new(f"key{i}", ld)
            self.coll.objects.link(ob)
            self.lights.append((ob, 1.7 * math.cos(a), 1.7 * math.sin(a)))

        cd = bpy.data.cameras.new("cam")
        cd.lens = 18.0                       # wide: the tunnel wraps around you
        cd.clip_start = 0.05
        cd.clip_end = VIEW + 10.0
        cd.dof.use_dof = True
        cd.dof.focus_distance = 5.5
        cd.dof.aperture_fstop = 2.8
        self.cam = bpy.data.objects.new("cam", cd)
        self.coll.objects.link(self.cam)
        scene.camera = self.cam

    def update(self, t):
        y = self.speed * t
        self.cam.location = (0.0, y, 0.0)
        self.cam.rotation_euler = (math.pi / 2, 0.0, 0.0)    # look down the tunnel (+Y)
        colors, _ = self.journey.at(y + 8.0)
        for i, (ob, dx, dz) in enumerate(self.lights):
            ob.location = (dx, y + (1.2 if i % 2 else 3.2), dz)
            # alternate near-white and palette-tinted glints
            tint = colors[i % 3] * 0.45 + 0.55 if i % 2 else colors[i % 3] * 0.85 + 0.15
            ob.data.color = tuple(float(c) for c in np.clip(tint, 0, 1))

        want = set(range(int(math.floor((y - 3.0) / SEG)), int(math.floor((y + VIEW) / SEG)) + 1))
        for k in [k for k in self.rings if k not in want]:
            self.rings.pop(k).remove()
        for k in sorted(want - set(self.rings)):
            self.rings[k] = Ring(self, k)
        for ring in self.rings.values():
            ring.update(t)

    def render_to(self, path):
        tmp = path + (".part.jpg" if path.endswith(".jpg") else ".part.png")
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
    ap.add_argument("--still", type=float, default=None)
    ap.add_argument("--out", default="still.png")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=float, default=24.0)
    ap.add_argument("--samples", type=int, default=24)
    ap.add_argument("--speed", type=float, default=1.0)
    args = ap.parse_args(argv)

    world = World(args)
    print(f"BLENDER {bpy.app.version_string} ENGINE {world.engine}", flush=True)
    img = world.scene.render.image_settings

    if args.still is not None:
        img.file_format = "PNG"
        world.update(args.still)
        world.render_to(os.path.abspath(args.out))
        print("STILL", os.path.abspath(args.out), flush=True)
        return

    img.file_format = "JPEG"
    setp(img, "quality", 95)
    os.makedirs(args.outdir, exist_ok=True)
    for f in range(args.start, args.end):
        path = os.path.abspath(os.path.join(args.outdir, f"f_{f:07d}.jpg"))
        if os.path.exists(path) and os.path.getsize(path) > 0:
            continue
        t0 = time.time()
        world.update(f / args.fps)
        world.render_to(path)
        print(f"FRAME {f} {time.time() - t0:.2f}", flush=True)


if __name__ == "__main__":
    main()
