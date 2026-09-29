// Neon Stars: floating through deep space past glowing neon outline stars.
// Depth is shown like a real camera: mid-distance stars are crisp, far ones
// melt into soft blurred shapes, and behind them all lies a far-off sky of
// soft distant stars, faint nebula clouds and the occasional spiral galaxy.
// u_p1: star density (locked)   u_p2: nebula / galaxy brightness
// u_p3: glide speed (locked)    u_p4: palette variation (0 = pure neon set)
//
// How it flies: NL depth planes of stars approach the camera at constant
// speed; when a plane passes the camera it is recycled to the far end with
// brand-new content (the cycle count feeds the hash), so the flight never
// repeats. Integer hashes keep that exact for hours of video.

const int   NL      = 16;      // star planes
const float D_FAR   = 7.0;     // plane distances (world units)
const float D_NEAR  = 0.32;
const float D_FOCUS = 2.4;     // focus distance: mid-distance stars are crisp
const float BLUR_FAR  = 0.030; // blur radius (screen units) at infinity
const float BLUR_NEAR = 0.0012;// slight softness on stars rushing past

uint hashu(uint x) {           // PCG-style integer hash
    x ^= x >> 16; x *= 0x7feb352dU;
    x ^= x >> 15; x *= 0x846ca68bU;
    x ^= x >> 16;
    return x;
}
float h01(uint a, uint b, uint c, uint k) {
    return float(hashu(a * 0x9e3779b9U ^ hashu(b + 0x632be5abU * c) ^ (k * 0x85ebca6bU)))
           / 4294967295.0;
}

// Inigo Quilez: signed distance to a 5-point star (r = outer radius,
// rf = inner/outer ratio)
float sdStar5(vec2 p, float r, float rf) {
    const vec2 k1 = vec2(0.809016994375, -0.587785252292);
    const vec2 k2 = vec2(-k1.x, k1.y);
    p.x = abs(p.x);
    p -= 2.0 * max(dot(k1, p), 0.0) * k1;
    p -= 2.0 * max(dot(k2, p), 0.0) * k2;
    p.x = abs(p.x);
    p.y -= r;
    vec2 ba = rf * vec2(-k1.y, k1.x) - vec2(0.0, 1.0);
    float h = clamp(dot(p, ba) / dot(ba, ba), 0.0, r);
    return length(p - ba * h) * sign(p.y * ba.x - p.x * ba.y);
}

// psychedelic neon set: electric and saturated, evenly spread
vec3 neon(float h) {
    if (h < 0.17) return vec3(1.00, 0.10, 0.80);   // electric magenta
    if (h < 0.32) return vec3(0.62, 0.18, 1.00);   // violet
    if (h < 0.46) return vec3(0.18, 0.38, 1.00);   // electric blue
    if (h < 0.61) return vec3(0.08, 0.92, 1.00);   // cyan
    if (h < 0.75) return vec3(0.45, 1.00, 0.12);   // acid green
    if (h < 0.90) return vec3(1.00, 0.18, 0.45);   // hot pink
    return vec3(1.00, 0.50, 0.05);                 // orange
}

vec3 starColor(float h, float h2) {
    return mix(neon(h), pal(h2), u_p4);
}

// ---- the far-off sky ------------------------------------------------------
// Everything here is so far away it barely moves: the whole sky pans very
// slowly (new clouds and galaxies drift in over the hours) with a hint of
// parallax from the camera drift.

vec3 farStars(vec2 q, float t, float cellSize, float prob, float radPx, float gain, uint layer) {
    float px = 1.0 / u_resolution.y;
    vec2 w = q / cellSize;
    vec2 cell = floor(w);
    uint ux = uint(int(cell.x) + 1000000), uy = uint(int(cell.y) + 1000000);
    if (h01(ux, uy, layer, 1U) > prob) return vec3(0.0);
    vec2 c = cell + 0.5 + (vec2(h01(ux, uy, layer, 2U), h01(ux, uy, layer, 3U)) - 0.5) * 0.6;
    float d = length(w - c) * cellSize;                     // screen units
    float b = h01(ux, uy, layer, 4U);
    b = 0.15 + 2.2 * b * b * b * b;                          // a few bright ones
    // sized as a fraction of the frame (radPx = pixels at 1080p), so 4K shows
    // the same sky, only sharper
    float r = max(radPx / 1080.0, px) * (0.8 + 0.6 * h01(ux, uy, layer, 5U));
    // soft, out of focus; the faint outer glow fades out inside the cell so
    // no cell edge ever shows
    float glow = exp(-d * d / (r * r))
               + 0.12 * exp(-d / (r * 2.5)) * smoothstep(0.45 * cellSize, 0.2 * cellSize, d);
    float ht = h01(ux, uy, layer, 6U);                       // star temperature
    vec3 sc = ht < 0.35 ? vec3(0.70, 0.80, 1.00) : ht < 0.70 ? vec3(1.00, 0.97, 0.92)
            : ht < 0.92 ? vec3(1.00, 0.84, 0.60) : vec3(1.00, 0.60, 0.38);
    float tw = 0.8 + 0.2 * sin(t * (0.7 + 2.0 * ht) + ht * 50.0);
    return sc * glow * b * tw * gain;
}

vec3 galaxy(vec2 q, float t) {
    const float G = 0.9;                                     // one galaxy per cell, at most
    vec2 w = q / G;
    vec2 cell = floor(w);
    uint ux = uint(int(cell.x) + 1000000), uy = uint(int(cell.y) + 1000000);
    if (h01(ux, uy, 91U, 1U) > 0.6) return vec3(0.0);
    float R = mix(0.09, 0.2, h01(ux, uy, 91U, 2U));          // screen units
    vec2 c = cell + 0.5 + (vec2(h01(ux, uy, 91U, 3U), h01(ux, uy, 91U, 4U)) - 0.5) * 0.3;
    vec2 p = (w - c) * G;
    p = rot(h01(ux, uy, 91U, 5U) * TAU) * p;
    p.y /= mix(0.3, 1.0, h01(ux, uy, 91U, 6U));              // tilt: seen at an angle
    float r = length(p) + 1e-4;
    float a = atan(p.y, p.x);
    float wind = mix(2.2, 4.0, h01(ux, uy, 91U, 7U));
    float arms = 0.5 + 0.5 * cos(2.0 * (a - wind * log(r / R)) + t * 0.01);
    arms = pow(arms, 2.5);
    float disk = exp(-r / (0.28 * R));
    float core = exp(-r / (0.05 * R));
    vec3 armCol = mix(vec3(0.55, 0.65, 1.0), vec3(1.0, 0.55, 0.75), h01(ux, uy, 91U, 8U) * 0.6);
    // fade the outskirts to zero well inside the cell
    float edge = smoothstep(0.42 * G, 0.3 * G, length(w - c) * G);
    return (armCol * disk * (0.3 + 1.0 * arms) + vec3(1.0, 0.86, 0.62) * core * 1.3) * 0.6 * edge;
}

vec3 space(vec2 uv, float t, vec2 cam) {
    vec2 sky = uv + vec2(t * 0.0035, t * 0.0012);            // the slow pan
    vec3 col = vec3(0.004, 0.005, 0.012);                    // deep space

    // nebula: soft glowing clouds with darker dust lanes through them
    vec2 q = sky + cam * 0.015;
    float n = fbm(q * 1.1 + vec2(3.1, 7.7));
    float m = fbm(q * 2.3 + 5.0);
    float cloud = smoothstep(0.36, 0.80, n) * (0.5 + 0.8 * m);
    cloud *= 1.0 - 0.65 * smoothstep(0.52, 0.72, fbm(q * 3.4 + 9.0));
    vec3 nebCol = mix(vec3(0.38, 0.10, 0.62), vec3(0.85, 0.18, 0.50), m);
    nebCol = mix(nebCol, vec3(0.08, 0.42, 0.62), smoothstep(0.45, 0.7, fbm(q * 0.7 + 21.0)));
    nebCol = mix(nebCol, pal(n + m), u_p4);
    col += nebCol * cloud * 0.32 * u_p2;

    col += galaxy(sky + cam * 0.02, t) * u_p2;

    // three depths of far-off stars, softer and bigger as they come nearer
    col += farStars(sky + cam * 0.01, t, 0.030, 0.55, 1.3, 0.55, 101U);
    col += farStars(sky + cam * 0.02 + 3.7, t, 0.055, 0.45, 2.2, 0.75, 102U);
    col += farStars(sky + cam * 0.035 + 8.1, t, 0.10, 0.30, 3.6, 0.9, 103U);
    return col;
}

float blurAt(float D) {
    return BLUR_FAR * max(0.0, (D - D_FOCUS) / D) + BLUR_NEAR * max(0.0, (D_FOCUS - D) / D);
}

void main() {
    float px = 1.0 / u_resolution.y;
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    float glide = t * u_p3 * 0.045;             // planes passed per second / NL

    // camera: a slow drift (parallax: near planes shift more) and a gentle roll
    uv = rot(0.06 * sin(t * 0.031)) * uv;
    vec2 cam = vec2(0.55 * sin(t * 0.043), 0.4 * sin(t * 0.057 + 1.3));

    vec3 col = space(uv, t, cam);

    // ---- stars ----------------------------------------------------------
    for (int i = 0; i < NL; i++) {
        float s = float(i) / float(NL) + glide;
        float z = fract(s);                       // 0 = far, 1 = at the camera
        uint cyc = uint(int(floor(s)) * NL + i);  // fresh content every pass
        float D = mix(D_FAR, D_NEAR, z);
        float fade = smoothstep(0.0, 0.22, z) * smoothstep(1.0, 0.94, z);
        if (fade <= 0.0) continue;
        float blur = blurAt(D);

        vec2 w = uv * D + cam + vec2(float(i) * 7.31, float(i) * 3.17);
        vec2 cell0 = floor(w);
        for (int cy = -1; cy <= 1; cy++)
        for (int cx = -1; cx <= 1; cx++) {
            vec2 cell = cell0 + vec2(cx, cy);
            uint ux = uint(int(cell.x) + 100000), uy = uint(int(cell.y) + 100000);
            if (h01(ux, uy, cyc, 1U) > u_p1) continue;          // empty cell
            float hs = h01(ux, uy, cyc, 2U);
            float r = mix(0.07, 0.34, hs * hs * hs);             // world radius
            vec2 c = cell + 0.5 + (vec2(h01(ux, uy, cyc, 3U), h01(ux, uy, cyc, 4U)) - 0.5)
                                   * (1.0 - 2.0 * r - 0.1);
            float spin = (h01(ux, uy, cyc, 5U) - 0.5) * 0.5;
            vec2 p = rot(h01(ux, uy, cyc, 6U) * TAU + spin * t) * (w - c);

            float thick = r * 0.075;                             // neon tube (world)
            float d = abs(sdStar5(p, r * 0.93, 0.47) - r * 0.02) / D;   // screen units
            float th = thick / D;
            float wide = th + blur;
            float energy = th / wide;                            // blur spreads, dims
            float tube = smoothstep(wide + px, max(th - blur, 0.0) - px * 0.5, d);
            float core = smoothstep(0.55 * th + blur + px, 0.0, d);
            float halo = exp(-d / (0.022 + 2.0 * blur)) * 0.30
                       + exp(-d / (0.007 + blur)) * 0.55;

            vec3 sc = starColor(h01(ux, uy, cyc, 7U), h01(ux, uy, cyc, 8U));
            float twinkle = 0.85 + 0.15 * sin(t * (0.8 + hs) + hs * 40.0);
            // far stars also recede into the dark (aerial perspective)
            float far = mix(1.0, 0.32, smoothstep(2.0, D_FAR, D));
            col += fade * far * twinkle * energy * (sc * (tube * 2.2 + halo)
                                                    + vec3(1.0, 0.97, 0.9) * core * 0.6);
        }
    }

    // soft vignette like a lens
    col *= 1.0 - 0.35 * smoothstep(0.35, 1.0, length(uv * vec2(0.85, 1.0)));
    fragColor = vec4(tonemap(col * 1.25), 1.0);
}
