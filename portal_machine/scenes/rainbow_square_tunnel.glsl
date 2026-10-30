// Rainbow Square Tunnel: flying down an endless tunnel of glowing neon
// squares, each turned a little further than the last so the tunnel spirals,
// with the colors running through the rainbow from square to square. The
// tunnel bends gently; squares grow and sweep out past the frame.
// u_p1: how much the tunnel bends   u_p2: twist per square (locked)
// u_p3: fly speed (locked)          u_p4: rainbow spread per square (locked)
//
// Flash safety: anything multiplied by the square number (which grows all
// video long) is locked for the whole video, and squares pass any point on
// screen at most ~1.4 times a second.

const int   NR  = 70;          // squares drawn ahead of the camera
const float S   = 0.8;         // spacing (world units)
const float R   = 1.0;         // square half-width
const float FAR = 56.0;        // NR * S

vec2 path(float z) {
    return u_p1 * vec2(1.8 * sin(z * 0.071) + 1.0 * sin(z * 0.033 + 1.3),
                       1.2 * sin(z * 0.057 + 2.1) + 0.7 * sin(z * 0.025 + 0.4));
}

// full-saturation rainbow (smooth hue wheel)
vec3 rainbow(float h) {
    vec3 c = clamp(abs(mod(h * 6.0 + vec3(0.0, 4.0, 2.0), 6.0) - 3.0) - 1.0, 0.0, 1.0);
    return c * c * (3.0 - 2.0 * c);
}

void main() {
    float px = 1.0 / u_resolution.y;
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    float zc = t * 1.1 * u_p3;                      // camera position along the tunnel

    vec2 pc = path(zc);
    vec2 look = (path(zc + 3.0) - pc) / 3.0;        // aim a little ahead along the path
    vec2 acc = path(zc + 3.0) - 2.0 * pc + path(zc - 3.0);
    uv = rot(clamp(-0.5 * acc.x, -0.25, 0.25)) * uv;   // bank gently into the bends

    vec3 col = vec3(0.004, 0.003, 0.008);

    float k0 = floor(zc / S) + 1.0;
    for (int i = NR - 1; i >= 0; i--) {             // far to near
        float k = k0 + float(i);
        float zk = k * S;
        float d = zk - zc;
        // no fade as a square arrives: it grows out past the frame edges
        float fade = smoothstep(0.03, 0.1, d) * (1.0 - smoothstep(FAR * 0.6, FAR, d));
        if (fade <= 0.0) continue;
        float atten = 0.25 + 0.75 * exp(-d / 13.0);
        // twist and hue per square, kept small with fract() for precision
        float ang = TAU * fract(k * u_p2 / TAU);
        vec3 rc = rainbow(fract(k * u_p4 + t * 0.01));

        vec2 c = (path(zk) - pc) / d - look;        // square center on screen
        // the outline lies between R (edge middles) and 1.42 R (corners):
        // pixels well away from that band skip the exact shape
        float lw = length(uv - c) * d;
        float m = 3.5 * (0.03 * d + 0.07);          // where the glow becomes negligible
        float dist = max(max(lw - 1.42 * R, R - lw), 0.0) / d;
        if (lw < 1.42 * R + m && lw > R - m) {
            vec2 p = rot(ang) * (uv - c) * d;
            vec2 q = abs(p) - vec2(R);
            dist = abs(length(max(q, 0.0)) + min(max(q.x, q.y), 0.0)) / d;
        }
        float th = 0.025 / d;                       // tube half-width on screen
        float blur = 0.005 * smoothstep(8.0, FAR, d);
        float w = max(th, 0.6 * px) + blur;
        float energy = th / w;
        float tube = 1.0 - smoothstep(w - px, w + px, dist);
        float core = 1.0 - smoothstep(0.0, 0.45 * w + px, dist);
        // the neon bloom: a bright tight glow plus a wide soft one that
        // spills the square's color out into the dark
        // (it hugs each square: deep black stays between them)
        float halo = exp(-dist / (0.006 + 0.9 * th)) * 1.25
                   + exp(-dist / (0.03 + 2.6 * th)) * 0.5 * exp(-d / 10.0);
        col += fade * atten * (rc * (tube * 1.5 * energy + halo * min(1.0, 4.0 * th / 0.025))
                               + vec3(1.0) * core * energy * 0.9);
    }

    col *= 1.0 - 0.3 * smoothstep(0.45, 1.0, length(uv * vec2(0.85, 1.0)));
    fragColor = vec4(tonemap(col * 1.1), 1.0);
}
