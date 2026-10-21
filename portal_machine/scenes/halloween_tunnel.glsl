// Halloween Tunnel: a spooky flight down an endless winding tunnel of glowing
// neon jack-o'-lanterns in psychedelic colors: every ring is a pumpkin
// outline carved with a scary face (angry eyes, jagged fanged grin). More
// lanterns with flickering candle-lit faces line the walls, embers drift
// past, and a pale moon glows through the fog. Pumpkins grow and sweep out
// past the frame as you fly through them.
// u_p1: how much the tunnel winds   u_p2: how much the pumpkins wobble
// u_p3: fly speed (locked)          u_p4: color spread along the tunnel

const int   NR  = 70;          // rings drawn ahead of the camera
const float S   = 0.8;         // ring spacing (world units)
const float R   = 1.0;         // pumpkin half-width
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

// ---- shapes (signed distances; Inigo Quilez's ellipse/box/triangle) --------

float sdEll(vec2 p, vec2 r) {              // ellipse, good approximation
    float k0 = length(p / r), k1 = length(p / (r * r));
    return k0 * (k0 - 1.0) / k1;
}
float sdBox(vec2 p, vec2 b) {
    vec2 d = abs(p) - b;
    return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0);
}
float sdTri(vec2 p, float r) {             // equilateral triangle, point up
    const float k = 1.7320508;
    p.x = abs(p.x) - r;
    p.y = p.y + r / k;
    if (p.x + k * p.y > 0.0) p = vec2(p.x - k * p.y, -k * p.x - p.y) / 2.0;
    p.x -= clamp(p.x, -2.0 * r, 0.0);
    return -length(p) * sign(p.y);
}

// pumpkin silhouette, about 2 units wide: a center lobe, two side lobes and
// a slanted stem (its outline lies 0.66..1.0 from the center)
float pumpkin(vec2 p) {
    vec2 q = vec2(abs(p.x), p.y);
    float c = sdEll(p - vec2(0.0, -0.05), vec2(0.52, 0.78));
    float s = sdEll(q - vec2(0.42, -0.08), vec2(0.55, 0.70));
    float st = sdBox(rot(-0.25) * (p - vec2(0.05, 0.82)), vec2(0.06, 0.13)) - 0.02;
    return min(min(c, s), st);
}

// scary jack-o'-lantern face: slanted angry eyes, a nose, and a wide grin
// with a jagged row of fangs hanging down and teeth pointing up
float scaryFace(vec2 p) {
    vec2 q = vec2(abs(p.x), p.y);
    float eye = sdTri(rot(0.38) * (q - vec2(0.30, 0.20)), 0.16);
    float nose = sdTri(vec2(p.x, -p.y), 0.07);
    float grin = max(sdEll(p - vec2(0.0, -0.33), vec2(0.58, 0.29)),
                     -sdEll(p - vec2(0.0, -0.15), vec2(0.66, 0.22)));
    // fangs: every 0.2 across, hanging from the grin's upper edge
    float fx = p.x - 0.1;
    float fc = (floor(fx / 0.2) + 0.5) * 0.2 + 0.1;       // this fang's center x
    float yTop = -0.15 - 0.22 * sqrt(max(0.0, 1.0 - (fc / 0.66) * (fc / 0.66)));
    float fang = abs(fc) < 0.45 ? sdTri(vec2(p.x - fc, -(p.y - (yTop - 0.035))), 0.075) : 1.0;
    // teeth: offset half a step, pointing up from the lower edge
    float tc = (floor(p.x / 0.2) + 0.5) * 0.2;
    float yBot = -0.33 - 0.29 * sqrt(max(0.0, 1.0 - (tc / 0.58) * (tc / 0.58)));
    float tooth = abs(tc) < 0.36 ? sdTri(vec2(p.x - tc, p.y - (yBot + 0.035)), 0.065) : 1.0;
    grin = max(grin, -min(fang, tooth));
    return min(min(eye, nose), grin);
}

// ---- scene ------------------------------------------------------------------

vec2 path(float z) {
    return u_p1 * vec2(3.0 * sin(z * 0.105) + 1.6 * sin(z * 0.046 + 1.3),
                       2.0 * sin(z * 0.081 + 2.1) + 1.0 * sin(z * 0.033 + 0.4));
}

// psychedelic Halloween neon, flowing along the tunnel
vec3 spookyCycle(float x) {
    vec3 c[6] = vec3[6](vec3(1.00, 0.40, 0.02),    // pumpkin orange
                        vec3(0.62, 0.10, 1.00),    // witch purple
                        vec3(0.35, 1.00, 0.06),    // toxic green
                        vec3(1.00, 0.06, 0.55),    // magenta
                        vec3(1.00, 0.70, 0.05),    // candle amber
                        vec3(1.00, 0.05, 0.12));   // blood red
    x = fract(x) * 6.0;
    int i = int(x);
    return mix(c[i], c[(i + 1) % 6], smoothstep(0.0, 1.0, fract(x)));
}

vec3 farSky(vec2 q, float t) {
    float px = 1.0 / u_resolution.y;
    const float CS = 0.04;
    vec2 w = q / CS;
    vec2 cell = floor(w);
    uint ux = uint(int(cell.x) + 100000), uy = uint(int(cell.y) + 100000);
    if (h01(ux, uy, 7U) > 0.4) return vec3(0.0);
    vec2 c = cell + 0.5 + (vec2(h01(ux, uy, 8U), h01(ux, uy, 9U)) - 0.5) * 0.6;
    float d = length(w - c) * CS;
    float r = max(1.1 / 1080.0, px);
    float b = h01(ux, uy, 10U);
    b = 0.08 + 0.9 * b * b * b;
    return vec3(0.85, 0.9, 1.0) * exp(-d * d / (r * r)) * b
           * (0.6 + 0.4 * sin(t * (1.0 + b) + b * 30.0));
}

void main() {
    float px = 1.0 / u_resolution.y;
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    float zc = t * 1.6 * u_p3;                      // camera position along the tunnel

    vec2 pc = path(zc);
    vec2 look = (path(zc + 3.0) - pc) / 3.0;        // aim a little ahead along the path
    vec2 acc = path(zc + 3.0) - 2.0 * pc + path(zc - 3.0);
    uv = rot(clamp(-0.6 * acc.x, -0.35, 0.35)) * uv;   // bank into the turns

    // ---- background: night sky, a pale moon, drifting fog ----
    vec3 col = vec3(0.008, 0.004, 0.012);
    col += farSky(uv + look * 0.3, t) * 0.6;
    float fog = fbm(uv * 1.5 + vec2(t * 0.012, -t * 0.006));
    float fog2 = fbm(uv * 3.1 - vec2(t * 0.02, 0.0) + 7.0);
    float fogAmt = smoothstep(0.3, 0.8, fog);
    vec3 fogCol = mix(vec3(0.42, 0.08, 0.60), vec3(0.12, 0.50, 0.22), smoothstep(0.4, 0.7, fog2));
    vec2 mc = vec2(0.62, 0.30) - 0.25 * look;
    float md = length(uv - mc);
    float mr = 0.085;
    float disc = 1.0 - smoothstep(mr - px, mr + px, md);
    vec2 mp = (uv - mc) / mr;
    float maria = smoothstep(0.45, 0.75, fbm(mp * 2.2 + 3.0));          // darker "seas"
    float crater = smoothstep(0.55, 0.8, fbm(mp * 7.0 + 11.0));
    float limb = sqrt(max(0.0, 1.0 - dot(mp, mp)));                      // rounder edge
    vec3 moon = vec3(1.0, 0.96, 0.82) * (0.55 + 0.45 * limb) * (1.0 - 0.35 * maria - 0.15 * crater);
    float veil = 1.0 - 0.55 * fogAmt;                                    // fog drifts over it
    col += moon * disc * 1.25 * veil;
    col += vec3(0.75, 0.95, 0.70) * (exp(-max(md - mr, 0.0) / 0.06) * 0.30
                                     + exp(-max(md - mr, 0.0) / 0.25) * 0.08) * veil;  // eerie halo
    col += fogCol * fogAmt * 0.16;

    // ---- rings and their wall objects, far to near (near ones draw on top) ----
    float k0 = floor(zc / S) + 1.0;
    for (int i = NR - 1; i >= 0; i--) {
        float k = k0 + float(i);
        float zk = k * S;
        float d = zk - zc;                          // distance ahead
        // no fade as a pumpkin arrives: it grows out past the frame edges
        float fade = smoothstep(0.03, 0.1, d) * (1.0 - smoothstep(FAR * 0.6, FAR, d));
        if (fade <= 0.0) continue;
        float atten = 0.22 + 0.78 * exp(-d / 13.0);
        vec3 rc = spookyCycle(k * 0.03 * u_p4 + t * 0.01);
        vec2 q = path(zk) - pc;
        vec2 c = q / d - look;                      // ring center on screen
        uint kk = uint(int(k));

        // --- the neon pumpkin ring ---
        float lw = length(uv - c) * d;              // world units from the center
        float m = 3.5 * (0.04 * d + 0.10);          // where the glow becomes negligible
        // the carved face sits within 0.72 of the center; faces fade out far
        // away so the end of the tunnel stays clean
        // every 4th pumpkin is carved; faces fade only far away. Up close they
        // keep growing and sweep out past the frame (their line width is
        // capped below so they stay crisp lines instead of swelling into bands)
        float faceFade = (mod(k, 4.0) < 0.5 ? 1.0 : 0.0) * (1.0 - smoothstep(8.0, 13.0, d));
        float dist = max(max(lw - R, 0.66 * R - lw), 0.0) / d;
        float fdist = 1e3, fin = 0.0;
        bool needSil = lw < R + m && lw > 0.66 * R - m;
        bool needFace = faceFade > 0.0 && lw < 0.72 * R + m;
        if (needSil || needFace) {
            float ang = 0.14 * u_p2 * sin(0.35 * k + 0.25 * t);   // gentle wobble
            vec2 p = rot(ang) * (uv - c) * d;       // world units in the ring's plane
            if (needSil) dist = abs(pumpkin(p)) / d;
            if (needFace) {
                float f = scaryFace(p);
                fdist = abs(f) / d;
                fin = 1.0 - smoothstep(-px * d, px * d, f);     // inside the carving
            }
        }
        float th = 0.03 / d;                        // tube half-width on screen
        float blur = 0.005 * smoothstep(8.0, FAR, d);
        float w = max(th, 0.6 * px) + blur;
        float energy = th / w;
        float tube = 1.0 - smoothstep(w - px, w + px, dist);
        float core = 1.0 - smoothstep(0.0, 0.45 * w + px, dist);
        float halo = exp(-dist / (0.006 + 0.7 * th)) * 1.0
                   + exp(-dist / (0.04 + 3.3 * th)) * 0.45;
        float haze = exp(-abs(lw - 0.85 * R) / d / (0.07 + min(4.0 * th, 0.35))) * 0.09;
        col += fade * atten * rc * haze;
        col += fade * atten * (rc * (tube * 1.6 * energy + halo * min(1.0, 4.0 * th / 0.03))
                               + vec3(1.0, 0.95, 0.9) * core * energy * 1.0);
        if (faceFade > 0.0 && fdist < 1e2) {        // the carved face, same neon tube
            float fth = min(th, 0.02);                 // capped line thickness
            float fw = max(0.8 * fth, 0.6 * px) + blur;
            float fe = 0.8 * fth / fw;
            vec3 fc = mix(rc, vec3(1.0, 0.75, 0.2), 0.25);
            col += fade * atten * faceFade
                 * (fc * ((1.0 - smoothstep(fw - px, fw + px, fdist)) * 1.3 * fe
                          + exp(-fdist / (0.006 + 0.6 * fth)) * 0.8
                          + exp(-fdist / (0.03 + 2.5 * fth)) * 0.3)
                    + vec3(1.0, 0.95, 0.9) * (1.0 - smoothstep(0.0, 0.45 * fw + px, fdist)) * fe * 0.7
                    + vec3(1.0, 0.55, 0.08) * fin * 0.16    // candle glow inside, fading
                      * smoothstep(0.5, 1.5, d));             // up close (no yellow tint)
        }

        // --- embers drifting past ---
        float dzmin = max(d - 0.5 * S, 0.15);
        float reach = length(q) * (1.0 / dzmin - 1.0 / d) + 1.65 * R / dzmin
                    + 5.0 * (min(0.008 / dzmin, 0.03) + px);
        if (length(uv - c) < reach) {
            for (int j = 0; j < 3; j++) {
                uint jj = uint(j);
                float a  = h01(kk, jj, 1U) * TAU;
                float rr = R * (0.35 + 1.3 * h01(kk, jj, 2U));
                float zz = zk + (h01(kk, jj, 3U) - 0.5) * S;
                float dz = zz - zc;
                if (dz < 0.15) continue;
                vec2 sp = (q + rr * vec2(cos(a), sin(a))) / dz - look;
                float dd = length(uv - sp);
                float sz = min(0.008 / dz, 0.03) + px;
                float hs = h01(kk, jj, 4U);
                float flick = 0.55 + 0.45 * sin(t * (5.0 + 6.0 * hs) + hs * 40.0);
                float fp = smoothstep(0.04, 0.15, dz) * (1.0 - smoothstep(FAR * 0.6, FAR, dz))
                         * (0.25 + 0.75 * exp(-dz / 10.0));
                vec3 ec = mix(vec3(1.0, 0.35, 0.03), vec3(1.0, 0.75, 0.2), hs);
                col += ec * (exp(-dd * dd / (sz * sz)) * 1.4
                             + exp(-dd / (3.0 * sz)) * 0.2) * flick * fp;
            }
        }

        // --- a jack-o'-lantern on the wall ---
        if (h01(kk, 7U, 1U) < 0.35) {
            float ho = h01(kk, 7U, 3U);
            float a = ho * TAU;
            float rr = R * (1.2 + 0.35 * h01(kk, 7U, 4U));
            float s = 0.24 + 0.10 * h01(kk, 7U, 5U);
            float zo = zk + (h01(kk, 7U, 6U) - 0.5) * S * 0.8;
            float dz = zo - zc;
            if (dz > 0.12) {
                vec2 op = (q + rr * vec2(cos(a), sin(a))) / dz - look;
                vec2 pl = (uv - op) * dz / s;       // lantern's own units (about +-1)
                if (length(pl) < 2.2) {
                    float pxu = px * dz / s;
                    float fo = smoothstep(0.12, 0.3, dz) * (1.0 - smoothstep(FAR * 0.45, FAR * 0.75, dz))
                             * (0.3 + 0.7 * exp(-dz / 10.0));
                    float sil = pumpkin(pl);
                    float body = 1.0 - smoothstep(-pxu, pxu, sil);
                    col *= 1.0 - 0.8 * body * fo;           // solid: hides what's behind
                    float face = scaryFace(pl);
                    float faceIn = (1.0 - smoothstep(-pxu, pxu, face)) * body;
                    float fl = 0.75 + 0.25 * sin(t * 13.0 + ho * 50.0) * sin(t * 7.3 + ho * 20.0);
                    col += fo * (vec3(1.0, 0.36, 0.03) * (body * 0.10 + exp(-abs(sil) / (0.06 + pxu)) * 0.7)
                                 + vec3(1.0, 0.72, 0.18) * faceIn * 2.2 * fl
                                 + vec3(1.0, 0.45, 0.06) * exp(-max(face, 0.0) / 0.12) * body * 0.45 * fl
                                 + vec3(1.0, 0.35, 0.04) * exp(-max(sil, 0.0) / 0.5) * 0.2 * fl);
                }
            }
        }
    }

    // fog in front of the tunnel catches its light
    col += fogCol * fogAmt * 0.08 + col * fogAmt * 0.15;
    col *= 1.0 - 0.45 * smoothstep(0.35, 1.0, length(uv * vec2(0.85, 1.0)));
    fragColor = vec4(tonemap(col * 1.2), 1.0);
}
