// TRUE 3D: a raymarched portal tunnel with real geometry, perspective,
// surface lighting, reflections off the walls and volumetric glow. The
// camera physically flies forward through space that repeats every 16
// units, so the flight is infinite and never loses precision.
// u_p1: tunnel radius   u_p2: path wobble
// u_p3: fly speed       u_p4: glow amount

// The world repeats every PERIOD units and the flight offset wraps there.
// For the wrap to be invisible EVERYTHING derived from depth must repeat on
// exactly that cycle: frequencies must be whole-number multiples of K, and
// mod() periods must divide PERIOD. A long PERIOD keeps the repeat subtle.
#define PERIOD 48.0    // world repeats every 48 units of depth
#define RINGS   4.0    // a portal ring every 4 units (48/4 = 12, exact)
#define K      (TAU / PERIOD)

// the tunnel's centerline weaves through space (periodic, so it tiles)
vec2 path(float z) {
    return u_p2 * vec2(sin(z * K), cos(z * K * 2.0) * 0.7);
}

// depth-driven color, built from the repeat cycle so it never snaps
float depthHue(float z) {
    return 0.55 * sin(z * K) + 0.25 * sin(z * K * 3.0);
}

// distance field: negative inside the wall. Also reports ring proximity.
float map(vec3 p, float zoff, out float ringDist) {
    float qz = p.z + zoff;
    vec2 c = path(qz);
    float r = length(p.xy - c);

    // corrugated tunnel wall (shallow: deep corrugation makes the distance
    // field overestimate, which lets rays punch through the surface)
    float wall = u_p1 - r
               + 0.05 * sin(qz * K * 17.0) * sin(atan(p.y - c.y, p.x - c.x) * 6.0);

    // glowing portal rings repeated along the tunnel
    float zi = mod(qz, RINGS) - RINGS * 0.5;
    ringDist = length(vec2(r - u_p1 * 0.86, zi)) - 0.10;

    return min(wall, ringDist);
}

vec3 normalAt(vec3 p, float zoff) {
    float d;
    vec2 e = vec2(0.002, 0.0);
    float c = map(p, zoff, d);
    return normalize(vec3(map(p + e.xyy, zoff, d) - c,
                          map(p + e.yxy, zoff, d) - c,
                          map(p + e.yyx, zoff, d) - c));
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;

    // keep the world offset bounded: infinite flight, zero precision loss
    float zoff = mod(t * u_p3 * 2.0, PERIOD);

    // camera sits at the origin looking down +z, with a slow roll
    vec3 ro = vec3(path(zoff) * 0.6, 0.0);
    vec3 rd = normalize(vec3(rot(t * 0.06) * uv, 1.25));

    vec3 col = vec3(0.0);
    vec3 glow = vec3(0.0);
    float dist = 0.0;
    float ringDist;
    bool hit = false;

    for (int i = 0; i < 120; i++) {
        vec3 p = ro + rd * dist;
        float d = map(p, zoff, ringDist);

        // volumetric bloom shed by the rings as the ray passes them
        float depthFade = exp(-dist * 0.20);
        glow += pal(depthHue(p.z + zoff) + t * 0.03)
              * (0.014 * u_p4 / (abs(ringDist) + 0.055)) * depthFade;

        if (d < 0.0015 * dist + 0.001) { hit = true; break; }
        // the corrugated wall makes the field non-Lipschitz, so step
        // conservatively or rays overshoot and leave black streaks
        dist += clamp(d * 0.55, 0.008, 1.2);
        if (dist > 32.0) break;
    }

    // everything far away converges to this, so rays that hit late and rays
    // that never hit end up the same color — no streaks at the vanishing point
    vec3 fogCol = pal(0.55 + t * 0.02) * 0.05;

    if (hit) {
        vec3 p = ro + rd * dist;
        vec3 n = normalAt(p, zoff);
        float qz = p.z + zoff;

        // a lamp travelling with the camera, plus ambient bounce
        vec3 lp = ro + vec3(0.0, 0.0, 2.0);
        vec3 ld = normalize(lp - p);
        float diff = max(dot(n, ld), 0.0);
        float spec = pow(max(dot(reflect(-ld, n), -rd), 0.0), 28.0);
        float fres = pow(1.0 - max(dot(n, -rd), 0.0), 3.0);

        // tiled panel texture on the tunnel wall, for scale and grip
        float ang = atan(p.y - path(qz).y, p.x - path(qz).x);
        float panel = smoothstep(0.06, 0.14, abs(fract(ang * 8.0 / TAU) - 0.5))
                    * smoothstep(0.06, 0.14, abs(fract(qz * 0.5) - 0.5));
        float seam = 1.0 - panel;

        vec3 base = pal(depthHue(qz) + t * 0.02) * (0.35 + 0.65 * panel);
        col = base * (0.06 + 0.95 * diff) + vec3(1.0) * spec * 0.5;
        col += pal(depthHue(qz) + 0.4) * fres * 0.9;   // rim / reflection
        col += pal(depthHue(qz) + 0.7) * seam * 0.25;  // lit seams between panels
        float fog = exp(-dist * 0.16);                  // depth fog
        col = col * fog + fogCol * (1.0 - fog);
    } else {
        col = fogCol;
    }

    col += glow;

    // lift contrast: deep darks, bright rings
    col = pow(col, vec3(1.15)) * 1.5;
    fragColor = vec4(tonemap(col), 1.0);
}
