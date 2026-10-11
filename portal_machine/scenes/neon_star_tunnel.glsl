// Neon Star Tunnel: flying down an endless winding tunnel of glowing neon
// star outlines. The path bends and the camera banks into the turns, so the
// rings ahead snake away into the distance; sparkles drift past along the
// walls. Colors flow through a psychedelic neon cycle along the tunnel.
// u_p1: how much the tunnel winds   u_p2: twist (rings turn along the tunnel)
// u_p3: fly speed (locked)          u_p4: color spread along the tunnel

const int   NR  = 70;          // rings drawn ahead of the camera
const float S   = 0.8;         // ring spacing (world units)
const float R   = 1.0;         // star outer radius
const float FAR = 56.0;        // NR * S

uint hashu(uint x) {           // PCG-style integer hash
    x ^= x >> 16; x *= 0x7feb352dU;
    x ^= x >> 15; x *= 0x846ca68bU;
    x ^= x >> 16;
    return x;
}
float h01(uint a, uint b, uint k) {
    return float(hashu(a * 0x9e3779b9U ^ hashu(b + 0x632be5abU) ^ (k * 0x85ebca6bU)))
           / 4294967295.0;
}

// Inigo Quilez: signed distance to a 5-point star
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

// the tunnel's center line: a sum of slow, unrelated sines, so it winds
// forever without repeating
vec2 path(float z) {
    return u_p1 * vec2(3.0 * sin(z * 0.105) + 1.6 * sin(z * 0.046 + 1.3),
                       2.0 * sin(z * 0.081 + 2.1) + 1.0 * sin(z * 0.033 + 0.4));
}

// smooth loop through a psychedelic neon set
vec3 neonCycle(float x) {
    vec3 c[6] = vec3[6](vec3(1.00, 0.10, 0.80),    // magenta
                        vec3(0.55, 0.15, 1.00),    // violet
                        vec3(0.15, 0.40, 1.00),    // electric blue
                        vec3(0.08, 0.92, 1.00),    // cyan
                        vec3(0.45, 1.00, 0.15),    // acid green
                        vec3(1.00, 0.20, 0.50));   // hot pink
    x = fract(x) * 6.0;
    int i = int(x);
    return mix(c[i], c[(i + 1) % 6], smoothstep(0.0, 1.0, fract(x)));
}

// faint far-off stars behind the tunnel
vec3 farSky(vec2 q, float t) {
    float px = 1.0 / u_resolution.y;
    const float CS = 0.035;
    vec2 w = q / CS;
    vec2 cell = floor(w);
    uint ux = uint(int(cell.x) + 100000), uy = uint(int(cell.y) + 100000);
    if (h01(ux, uy, 7U) > 0.5) return vec3(0.0);
    vec2 c = cell + 0.5 + (vec2(h01(ux, uy, 8U), h01(ux, uy, 9U)) - 0.5) * 0.6;
    float d = length(w - c) * CS;
    float r = max(1.1 / 1080.0, px);
    float b = h01(ux, uy, 10U);
    b = 0.1 + 1.2 * b * b * b;
    return vec3(0.9, 0.85, 1.0) * exp(-d * d / (r * r)) * b
           * (0.7 + 0.3 * sin(t * (1.0 + b) + b * 30.0));
}

void main() {
    float px = 1.0 / u_resolution.y;
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    float zc = t * 1.7 * u_p3;                      // camera position along the tunnel

    vec2 pc = path(zc);
    vec2 look = (path(zc + 3.0) - pc) / 3.0;        // aim a little ahead along the path
    vec2 acc = path(zc + 3.0) - 2.0 * pc + path(zc - 3.0);
    uv = rot(clamp(-0.6 * acc.x, -0.35, 0.35)) * uv;   // bank into the turns

    vec3 col = vec3(0.010, 0.004, 0.016);
    col += farSky(uv + look * 0.3, t) * 0.8;

    float k0 = floor(zc / S) + 1.0;
    for (int i = 0; i < NR; i++) {
        float k = k0 + float(i);
        float zk = k * S;
        float d = zk - zc;                          // distance ahead
        // no fade as a star arrives: it keeps growing until it sweeps out past
        // the edges of the frame (by d = 0.3 even its inner corners are off
        // screen; the tiny ramp below only avoids a pop as it reaches the lens)
        float fade = smoothstep(0.03, 0.1, d) * (1.0 - smoothstep(FAR * 0.6, FAR, d));
        if (fade <= 0.0) continue;
        float atten = 0.25 + 0.75 * exp(-d / 14.0);
        vec3 rc = neonCycle(k * 0.03 * u_p4 + t * 0.01);

        // --- the neon star ring ---
        vec2 c = (path(zk) - pc) / d - look;        // ring center on screen
        // the outline lies between 0.5 R and R from the ring center: pixels
        // well outside that band only get the soft glow, so they skip the
        // exact star shape (most of the render cost) and use a lower bound
        float lw = length(uv - c) * d;              // world units from the center
        float m = 4.0 * (0.02 * d + 0.042);         // where the glow becomes negligible
        float dist = max(max(lw - R, 0.5 * R - lw), 0.0) / d;
        if (lw < R + m && lw > 0.5 * R - m) {
            float ang = 0.07 * u_p2 * d + 0.06 * t; // twist along the tunnel
            vec2 p = rot(ang) * (uv - c) * d;       // world units in the ring's plane
            dist = abs(sdStar5(p, R, 0.5)) / d;     // screen units
        }
        float th = 0.028 / d;                       // tube half-width on screen
        float blur = 0.005 * smoothstep(8.0, FAR, d);
        float w = max(th, 0.6 * px) + blur;
        float energy = th / w;                      // thin, soft far rings are dimmer
        float tube = 1.0 - smoothstep(w - px, w + px, dist);
        float core = 1.0 - smoothstep(0.0, 0.45 * w + px, dist);
        float halo = exp(-dist / (0.004 + 0.5 * th)) * 0.55
                   + exp(-dist / (0.02 + 1.5 * th)) * 0.12;
        // dreamy glow filling the tunnel: a wide, faint haze from every ring
        float haze = exp(-abs(lw - 0.75 * R) / d / (0.05 + min(3.0 * th, 0.25))) * 0.06;
        col += fade * atten * rc * haze;
        col += fade * atten * (rc * (tube * 1.6 * energy + halo * min(1.0, 4.0 * th / 0.028))
                               + vec3(1.0, 0.95, 1.0) * core * energy * 0.9);

        // --- sparkles drifting past along the tunnel walls ---
        // this ring's sparkles sit within 1.65 R of its center and +-S/2 in
        // depth: skip them all when the pixel is too far from any of them
        vec2 q = path(zk) - pc;
        float dzmin = max(d - 0.5 * S, 0.15);
        float reach = length(q) * (1.0 / dzmin - 1.0 / d) + 1.65 * R / dzmin
                    + 5.0 * (min(0.009 / dzmin, 0.035) + px);
        if (length(uv - c) > reach) continue;
        uint kk = uint(int(k));
        for (int j = 0; j < 3; j++) {
            uint jj = uint(j);
            float a  = h01(kk, jj, 1U) * TAU;
            float rr = R * (0.35 + 1.3 * h01(kk, jj, 2U));
            float zz = zk + (h01(kk, jj, 3U) - 0.5) * S;
            float dz = zz - zc;
            if (dz < 0.15) continue;
            // the ring's own center stands in for path(zz): zz is within half
            // a ring spacing, where the path barely moves
            vec2 sp = (q + rr * vec2(cos(a), sin(a))) / dz - look;
            float dd = length(uv - sp);
            float sz = min(0.009 / dz, 0.035) + 1.0 * px;
            float hs = h01(kk, jj, 4U);
            float tw = 0.6 + 0.4 * sin(t * (2.0 + 3.0 * hs) + hs * 40.0);
            float fp = smoothstep(0.04, 0.15, dz) * (1.0 - smoothstep(FAR * 0.6, FAR, dz))
                     * (0.25 + 0.75 * exp(-dz / 10.0));
            col += mix(vec3(1.0), rc, 0.35) * (exp(-dd * dd / (sz * sz)) * 1.4
                    + exp(-dd / (2.5 * sz)) * 0.12) * tw * fp;
        }
    }

    col *= 1.0 - 0.3 * smoothstep(0.4, 1.0, length(uv * vec2(0.85, 1.0)));
    fragColor = vec4(tonemap(col * 1.2), 1.0);
}
