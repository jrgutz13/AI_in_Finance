// TRUE 3D: flying forever through the corridors of an infinite Menger
// sponge — a lattice of nested square holes at four scales, lit from
// within. Space is periodic, so the flight never ends or loses precision.
// u_p1: hole size        u_p2: corridor twist
// u_p3: fly speed        u_p4: glow amount

#define SC     0.42        // fractal units per world unit
#define LATTICE (2.0 / SC) // world-space period of the lattice itself
// The flight offset wraps at WRAP. For that wrap to be invisible, every
// quantity derived from depth must repeat on exactly that cycle, so the
// twist and the colors below are built from sin() of whole-number multiples
// of K. Wrapping after several lattice cells keeps the repeat unobtrusive.
#define WRAP   (LATTICE * 6.0)
#define K      (TAU / WRAP)

float depthHue(float z) {
    return 0.50 * sin(z * K) + 0.22 * sin(z * K * 3.0);
}

// Infinite Menger: start solid, then carve out crosses at four scales.
// (No bounding box — that is what makes it fill space forever.)
float mengerDE(vec3 p, float hole, out float layer) {
    float d = -1e9;
    float s = 1.0;
    layer = 0.0;
    for (int m = 0; m < 4; m++) {
        vec3 a = mod(p * s, 2.0) - 1.0;
        s *= 3.0;
        vec3 r = abs(1.0 - 3.0 * abs(a));
        float da = max(r.x, r.y);
        float db = max(r.y, r.z);
        float dc = max(r.z, r.x);
        float c = (min(da, min(db, dc)) - hole) / s;
        if (c > d) { d = c; layer = float(m); }   // carve (max = subtract)
    }
    return d;
}

float sceneDE(vec3 p, float zoff, float hole, float twist, out float layer) {
    vec3 q = p;
    q.z += zoff;
    // twist as a sine of depth, not a linear ramp: a ramp would snap back
    // to zero every time the flight offset wrapped
    q.xy = rot(twist * 0.55 * sin(q.z * K)) * q.xy;
    return mengerDE(q * SC, hole, layer) / SC;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;

    // bounded world offset: infinite corridor, no precision loss
    float zoff = mod(t * u_p3 * 1.1, WRAP);

    // sit in the middle of a corridor and fly straight down it
    vec3 ro = vec3(0.0, 0.0, 0.0);
    vec3 rd = normalize(vec3(rot(t * 0.05) * uv, 1.5));

    float dist = 0.0;
    float layer = 0.0, lay;
    bool hit = false;
    vec3 glow = vec3(0.0);

    for (int i = 0; i < 110; i++) {
        vec3 p = ro + rd * dist;
        float d = sceneDE(p, zoff, u_p1, u_p2, lay);
        float ds = clamp(d * 0.75, 0.004, 0.9);

        // light bleeding from the lattice gaps. Weighting by the step length
        // makes this a proper volumetric integral instead of something that
        // blows up with the iteration count.
        glow += pal(lay * 0.22 + depthHue(p.z + zoff) + t * 0.03)
              * (0.30 * u_p4 / (abs(d) + 0.12)) * ds * exp(-dist * 0.30);

        if (d < 0.0012 * dist + 0.0008) { hit = true; layer = lay; break; }
        dist += ds;
        if (dist > 22.0) break;
    }

    vec3 fogCol = pal(0.5 + t * 0.02) * 0.02;
    vec3 col = fogCol;

    if (hit) {
        vec3 p = ro + rd * dist;
        vec2 e = vec2(0.0016, 0.0);
        float l;
        float c = sceneDE(p, zoff, u_p1, u_p2, l);
        vec3 n = normalize(vec3(
            sceneDE(p + e.xyy, zoff, u_p1, u_p2, l) - c,
            sceneDE(p + e.yxy, zoff, u_p1, u_p2, l) - c,
            sceneDE(p + e.yyx, zoff, u_p1, u_p2, l) - c));

        vec3 ld = normalize(vec3(0.45, 0.65, -1.0));
        float diff = max(dot(n, ld), 0.0);
        float spec = pow(max(dot(reflect(-ld, n), -rd), 0.0), 26.0);
        float fres = pow(1.0 - max(dot(n, -rd), 0.0), 3.0);
        // deeper carvings sit in shadow: cheap ambient occlusion
        float ao = clamp(0.35 + 0.65 * (1.0 - layer * 0.22), 0.3, 1.0);

        vec3 base = pal(layer * 0.28 + depthHue(p.z + zoff) + t * 0.02);
        col = base * (0.08 + 0.95 * diff) * ao + vec3(1.0) * spec * 0.45;
        col += pal(layer * 0.28 + 0.45) * fres * 0.8;
        float fog = exp(-dist * 0.26);
        col = col * fog + fogCol * (1.0 - fog);
    }

    col += glow;
    col = pow(col, vec3(1.1)) * 1.4;      // keep the darks deep
    fragColor = vec4(tonemap(col), 1.0);
}
