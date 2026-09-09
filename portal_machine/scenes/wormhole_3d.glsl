// TRUE 3D: flying down a living wormhole — an organic tube whose walls
// ripple with real displaced geometry, lit from within, with volumetric
// energy streaming past the camera.
// u_p1: tube radius     u_p2: wall ripple
// u_p3: fly speed       u_p4: energy glow

#define PERIOD 12.0

// the tube's centre snakes through space (periodic so it tiles forever)
vec2 tubePath(float z) {
    return vec2(0.42 * sin(TAU * z / PERIOD),
                0.34 * cos(TAU * z / (PERIOD * 0.5)));
}

float tubeDE(vec3 p, float zoff, float radius, float ripple, out float band) {
    float qz = p.z + zoff;
    vec2 c = tubePath(qz);
    vec2 rel = p.xy - c;
    float r = length(rel);
    float a = atan(rel.y, rel.x);

    // organic ripple: pronounced flesh-like ridges running along and around
    // the tube. These need real depth or the wall shades as a flat gradient.
    float ridge = ripple * (0.130 * sin(a * 7.0 + qz * 1.6)
                          + 0.090 * sin(a * 3.0 - qz * 2.3)
                          + 0.060 * sin(qz * 4.1)
                          + 0.045 * sin(a * 13.0 + qz * 3.7));
    band = 0.5 + 0.5 * sin(qz * 1.2 + a * 2.0);
    return radius + ridge - r;      // negative outside the tube wall
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;

    float zoff = mod(t * u_p3 * 2.2, PERIOD);

    vec3 ro = vec3(tubePath(zoff) * 0.75, 0.0);
    vec3 rd = normalize(vec3(rot(t * 0.07) * uv, 1.2));

    float dist = 0.0, band = 0.0, bd;
    bool hit = false;
    vec3 glow = vec3(0.0);

    for (int i = 0; i < 110; i++) {
        vec3 p = ro + rd * dist;
        float d = tubeDE(p, zoff, u_p1, u_p2, bd);

        // energy streaming along the tube, brightest near the walls.
        // Step-weighted, so the halo is a volumetric integral instead of
        // something that grows with the iteration count and washes out.
        float pulse = pow(abs(sin((p.z + zoff) * 0.8 - t * 2.0)), 6.0);
        float ds = clamp(d * 0.55, 0.006, 1.0);
        glow += pal(bd * 0.8 + (p.z + zoff) * 0.05 + t * 0.03)
              * (0.020 * u_p4 * (0.4 + pulse) / (abs(d) + 0.14))
              * ds * exp(-dist * 0.26);

        if (d < 0.0015 * dist + 0.001) { hit = true; band = bd; break; }
        dist += ds;
        if (dist > 34.0) break;
    }

    vec3 fogCol = pal(0.58 + t * 0.02) * 0.018;
    vec3 col = fogCol;

    if (hit) {
        vec3 p = ro + rd * dist;
        vec2 e = vec2(0.002, 0.0);
        float b;
        float c = tubeDE(p, zoff, u_p1, u_p2, b);
        vec3 n = normalize(vec3(tubeDE(p + e.xyy, zoff, u_p1, u_p2, b) - c,
                                tubeDE(p + e.yxy, zoff, u_p1, u_p2, b) - c,
                                tubeDE(p + e.yyx, zoff, u_p1, u_p2, b) - c));

        // lamp riding just ahead of the camera
        vec3 ld = normalize(vec3(0.0, 0.0, 2.5) + vec3(0.4, 0.3, 0.0) - p);
        float diff = max(dot(n, ld), 0.0);
        float spec = pow(max(dot(reflect(-ld, n), -rd), 0.0), 20.0);
        float fres = pow(1.0 - max(dot(n, -rd), 0.0), 2.5);

        // dark tissue walls threaded with bright bioluminescent veins:
        // reads far better than a smoothly shaded surface
        float qz = p.z + zoff;
        vec2 rel = p.xy - tubePath(qz);
        float ang = atan(rel.y, rel.x);
        float veins = pow(abs(sin(ang * 5.0 + qz * 1.1 + 2.0 * band)), 22.0)
                    + pow(abs(sin(ang * 9.0 - qz * 0.7)), 30.0);
        float grain = fbm(vec2(ang * 3.0, qz * 1.5));

        vec3 base = pal(band * 0.9 + qz * 0.04 + t * 0.02) * (0.35 + 0.65 * grain);
        col = base * (0.05 + 0.55 * diff) + vec3(1.0) * spec * 0.30;
        col += pal(band * 0.9 + 0.4) * fres * 0.35;
        col += pal(band + 0.55) * veins * 1.5;          // the glowing veins
        col += pal(grain + 0.3) * pow(grain, 5.0) * 0.4; // wet highlights
        float fog = exp(-dist * 0.22);
        col = col * fog + fogCol * (1.0 - fog);
    }

    col += glow;
    // gamma above 1 with only a small gain deepens the darks; multiplying
    // by a big number afterwards would just wash it out again
    col = pow(col, vec3(1.45)) * 1.15;
    fragColor = vec4(tonemap(col), 1.0);
}
