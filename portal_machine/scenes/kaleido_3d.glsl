// TRUE 3D: a kaleidoscope built in real space — mirrored 3D geometry
// folded around the view axis, receding with genuine depth and lighting,
// so the symmetry has volume instead of being a flat pattern.
// u_p1: mirror wedges (5..10)   u_p2: fold tightness
// u_p3: fly speed               u_p4: glow amount

#define REPEAT 5.0            // jewel rings every 5 units
// The flight offset wraps at WRAP (a whole number of jewel rings). Every
// depth-derived quantity below repeats on exactly that cycle, or the wrap
// would be visible as a snap.
#define WRAP   (REPEAT * 5.0)
#define K      (TAU / WRAP)

float depthHue(float z) {
    return 0.50 * sin(z * K) + 0.20 * sin(z * K * 3.0);
}

// mat: 0 = jewel, 1 = the surrounding corridor wall (kept dark, as backdrop)
float kaleidoDE(vec3 p, float wedges, float fold, out float trap, out float mat) {
    // fold space into a wedge around the z axis, then mirror it
    float a = atan(p.y, p.x);
    float r = length(p.xy);
    float seg = TAU / wedges;
    a = mod(a, seg);
    a = abs(a - seg * 0.5);          // the mirror
    p.xy = vec2(cos(a), sin(a)) * r;

    trap = 1e10;
    float d = 1e10;
    // a small cluster of jewels, folded by the mirror into a full ring
    for (int i = 0; i < 3; i++) {
        float fi = float(i);
        vec3 q = p;
        q.xy -= vec2(0.85 + 0.25 * fi, 0.0);
        q = rotZ(fold * 0.6 * fi) * rotX(fold * 0.9) * q;
        float shape = min(sdOctahedron(q, 0.26 - 0.05 * fi),
                          sdBox(q, vec3(0.13)));
        trap = min(trap, length(q));
        d = min(d, shape);
    }
    // the mirrored corridor walls holding it all together
    mat = 0.0;
    float wall = 1.55 - r;
    if (wall < d) { d = wall; mat = 1.0; }
    return d;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    float wedges = floor(u_p1 + 0.5);

    float zoff = mod(t * u_p3 * 1.3, WRAP);

    vec3 ro = vec3(0.0, 0.0, 0.0);
    vec3 rd = normalize(vec3(rot(t * 0.08) * uv, 1.3));

    float dist = 0.0, trap = 0.0, tr;
    float mat = 0.0, mt;
    bool hit = false;
    vec3 glow = vec3(0.0);

    for (int i = 0; i < 110; i++) {
        vec3 p = ro + rd * dist;
        vec3 q = p;
        q.z += zoff;
        q.z = mod(q.z, REPEAT) - REPEAT * 0.5;
        // sine twist, not a linear ramp: a ramp resets at every wrap
        q = rotZ(u_p2 * 0.9 * sin((p.z + zoff) * K)) * q;

        float d = kaleidoDE(q, wedges, u_p2, tr, mt);
        float ds = clamp(d * 0.7, 0.005, 0.8);
        // step-weighted so the halo is a real volumetric integral rather
        // than something that grows with the iteration count
        glow += pal(tr * 1.1 + depthHue(p.z + zoff) + t * 0.03)
              * (0.055 * u_p4 / (abs(d) + 0.10)) * ds * exp(-dist * 0.32);

        if (d < 0.0012 * dist + 0.0008) { hit = true; trap = tr; mat = mt; break; }
        dist += ds;
        if (dist > 24.0) break;
    }

    vec3 fogCol = pal(0.45 + t * 0.02) * 0.018;
    vec3 col = fogCol;

    if (hit) {
        vec3 p = ro + rd * dist;
        vec2 e = vec2(0.0015, 0.0);
        vec3 q0 = p;
        q0.z += zoff;
        q0.z = mod(q0.z, REPEAT) - REPEAT * 0.5;
        q0 = rotZ(u_p2 * 0.9 * sin((p.z + zoff) * K)) * q0;
        float c = kaleidoDE(q0, wedges, u_p2, tr, mt);
        vec3 n = normalize(vec3(kaleidoDE(q0 + e.xyy, wedges, u_p2, tr, mt) - c,
                                kaleidoDE(q0 + e.yxy, wedges, u_p2, tr, mt) - c,
                                kaleidoDE(q0 + e.yyx, wedges, u_p2, tr, mt) - c));

        vec3 ld = normalize(vec3(0.3, 0.5, -1.0));
        float diff = max(dot(n, ld), 0.0);
        float spec = pow(max(dot(reflect(-ld, n), -rd), 0.0), 32.0);
        float fres = pow(1.0 - max(dot(n, -rd), 0.0), 3.0);

        // panelled texture, so the mirrored corridor walls read as surfaces
        // instead of a smooth rainbow gradient
        float qz = p.z + zoff;
        float ang = atan(p.y, p.x);
        // 0.6 gives a tile period that divides WRAP exactly; 0.7 would not,
        // so the panels would jump each time the flight offset wrapped
        float tile = smoothstep(0.05, 0.13, abs(fract(ang * wedges / TAU) - 0.5))
                   * smoothstep(0.05, 0.13, abs(fract(qz * 0.6) - 0.5));
        float etch = pow(abs(sin(ang * wedges * 2.0 + qz * K * 6.0)), 24.0);

        // the wall is only a backdrop: keep it dim so the jewels carry the eye
        float wallDim = mix(1.0, 0.22, mat);

        vec3 base = pal(trap * 1.3 + depthHue(qz) + t * 0.02) * (0.45 + 0.70 * tile);
        col = base * (0.30 + 1.5 * diff) * wallDim + vec3(1.0) * spec * 0.9 * wallDim;
        col += pal(trap * 1.3 + 0.4) * fres * 1.1 * wallDim;   // jewel edges
        col += pal(trap + 0.65) * etch * 0.7 * wallDim;        // etched lines
        float fog = exp(-dist * 0.22);
        col = col * fog + fogCol * (1.0 - fog);
    }

    col += glow;
    col = pow(col, vec3(1.12)) * 1.45;     // deep darks, bright jewels
    fragColor = vec4(tonemap(col), 1.0);
}
