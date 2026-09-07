// Kaliset fractal with a continuous zoom-in. Endless self-similar detail.
// u_p1: fractal shape c.x      u_p2: fractal shape c.y
// u_p3: zoom rate              u_p4: mirror symmetry (0/1)

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;

    if (u_p4 > 0.5) uv = abs(uv);          // optional 4-way mirror

    // Clip mode: a short monotonic dive (looks like zooming in for ~8s).
    // Continuous mode: a slow endless breathing dive instead, because a
    // monotonic exp() would overflow float precision over a multi-hour video
    // and collapse to a flat color. The bounded cosine keeps zoom in a safe
    // range forever while the drifting fractal shape (c) below means you are
    // always passing through new structure, never the same loop.
    float zoom;
    if (u_continuous > 0.5) {
        zoom = 0.7 * exp(2.6 * (0.5 - 0.5 * cos(t * u_p3 * 0.05)));
    } else {
        // keep the exponent modest — float32 dies past ~exp(6)
        zoom = 0.7 * exp(t * u_p3 * 0.22);
    }
    vec2 p = uv / zoom;
    p = rot(t * 0.07) * p;
    p += vec2(0.354, 0.221);               // drift into a detailed region

    vec2 c = vec2(u_p1 + 0.04 * sin(t * 0.21),
                  u_p2 + 0.04 * cos(t * 0.17));

    float acc = 0.0;
    float m = 100.0;
    for (int i = 0; i < 16; i++) {
        p = abs(p) / dot(p, p) - c;
        float l = length(p);
        acc += exp(-2.5 * abs(l - 0.5));
        m = min(m, l);
    }

    vec3 col = pal(acc * 0.15 + m * 1.2 + t * 0.05) * (acc * 0.13);
    col += pal(m + 0.3) * smoothstep(0.25, 0.0, m) * 0.6;   // glow in the veins

    fragColor = vec4(tonemap(col), 1.0);
}
