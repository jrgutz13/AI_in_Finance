"""Vibrant cosine color palettes: col(t) = A + B*cos(2pi*(C*t + D)).

The (C, D) pairs below are curated to stay saturated and avoid muddy browns;
each draw jitters them slightly so no two videos share exact colors."""


# (C, D) families: frequency and phase per RGB channel
_FAMILIES = [
    # full rainbow
    ((1.0, 1.0, 1.0), (0.00, 0.33, 0.67)),
    # cyan / magenta neon
    ((1.0, 1.0, 1.0), (0.30, 0.20, 0.20)),
    # electric blue-purple
    ((1.0, 1.0, 1.0), (0.80, 0.90, 0.30)),
    # sunset orange-pink
    ((1.0, 0.7, 0.4), (0.00, 0.15, 0.20)),
    # acid green-violet
    ((2.0, 1.0, 0.0), (0.50, 0.20, 0.25)),
    # deep ocean teal
    ((1.0, 1.0, 0.5), (0.80, 0.90, 0.30)),
    # gold and indigo
    ((0.8, 0.8, 0.5), (0.00, 0.20, 0.50)),
    # hot pink / cyan vapor
    ((1.0, 0.5, 1.0), (0.85, 0.40, 0.10)),
]


def random_palette(rng):
    """Returns (A, B, C, D), each a 3-tuple of floats."""
    c, d = rng.choice(_FAMILIES)
    jitter = lambda v, amt: tuple(x + rng.uniform(-amt, amt) for x in v)
    a = jitter((0.50, 0.50, 0.50), 0.06)
    b = jitter((0.50, 0.50, 0.50), 0.06)
    c = jitter(c, 0.08)
    d = jitter(d, 0.05)
    return a, b, c, d
