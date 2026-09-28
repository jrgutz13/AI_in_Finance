// Neon Stars: gliding forward through a field of glowing neon outline stars
// and glitter. Depth is shown like a real camera: a focus distance just in
// front of you, so far stars and dust melt into soft blurred shapes and
// bokeh discs while the nearest ones are crisp.
// u_p1: star density (locked)   u_p2: glitter brightness
// u_p3: glide speed (locked)    u_p4: palette variation (0 = pure neon set)
//
// How it flies: NL depth planes of stars approach the camera at constant
// speed; when a plane passes the camera it is recycled to the far end with
// brand-new content (the cycle count feeds the hash), so the flight never
// repeats. Integer hashes keep that exact for hours of video.

const int   NL      = 12;      // star planes
const int   NG      = 10;      // glitter planes
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

// the neon set from warm to cool, weighted towards golds like a party sky
vec3 neon(float h) {
    if (h < 0.26) return vec3(1.00, 0.78, 0.08);   // yellow
    if (h < 0.42) return vec3(1.00, 0.50, 0.08);   // gold / orange
    if (h < 0.55) return vec3(1.00, 0.30, 0.20);   // coral
    if (h < 0.68) return vec3(1.00, 0.22, 0.45);   // pink
    if (h < 0.85) return vec3(0.20, 0.70, 1.00);   // cyan
    return vec3(0.85, 1.00, 0.45);                 // pale lime
}

vec3 starColor(float h, float h2) {
    return mix(neon(h), pal(h2), u_p4);
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

    vec3 col = vec3(0.012, 0.007, 0.004);        // warm near-black

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
            float far = mix(1.0, 0.45, smoothstep(2.0, D_FAR, D));
            col += fade * far * twinkle * energy * (sc * (tube * 2.2 + halo)
                                                    + vec3(1.0, 0.97, 0.9) * core * 0.6);
        }
    }

    // ---- glitter and bokeh ----------------------------------------------
    for (int i = 0; i < NG; i++) {
        float s = float(i) / float(NG) + glide * 1.0 + 0.037;
        float z = fract(s);
        uint cyc = uint(int(floor(s)) * NG + i) + 0x10000U;
        float D = mix(D_FAR, D_NEAR, z);
        float fade = smoothstep(0.0, 0.2, z) * smoothstep(1.0, 0.8, z);
        if (fade <= 0.0) continue;
        float blur = blurAt(D);

        const float CELL = 0.16;                  // world spacing of glitter
        vec2 w = (uv * D + cam + vec2(float(i) * 5.13, float(i) * 1.91)) / CELL;
        vec2 cell = floor(w);
        uint ux = uint(int(cell.x) + 1000000), uy = uint(int(cell.y) + 1000000);
        if (h01(ux, uy, cyc, 1U) > 0.65) continue;
        vec2 c = cell + 0.5 + (vec2(h01(ux, uy, cyc, 2U), h01(ux, uy, cyc, 3U)) - 0.5) * 0.5;
        float dist = length(w - c) * CELL / D;    // screen units
        float rs = (0.0025 + 0.004 * h01(ux, uy, cyc, 4U)) / D * 0.6;   // sharp dot radius
        // defocus: the dot becomes a disc of the blur radius, same light
        // spread over a larger area (capped inside its cell)
        float rad = min(rs + blur, 0.24 * CELL / D);
        float disc = smoothstep(rad + px, rad - max(px, rad * 0.35), dist);
        float energy = (rs + px) * (rs + px) / ((rad + px) * (rad + px));
        float hc = h01(ux, uy, cyc, 5U);
        vec3 gc = mix(starColor(hc, h01(ux, uy, cyc, 6U)), vec3(1.0, 0.78, 0.35), 0.55);
        float twinkle = 0.55 + 0.45 * sin(t * (1.5 + 3.0 * hc) + hc * 60.0);
        float far = mix(1.0, 0.35, smoothstep(2.5, D_FAR, D));
        col += gc * disc * energy * fade * far * twinkle * u_p2 * 5.0;
    }

    // soft vignette like a lens
    col *= 1.0 - 0.35 * smoothstep(0.35, 1.0, length(uv * vec2(0.85, 1.0)));
    fragColor = vec4(tonemap(col * 1.25), 1.0);
}
