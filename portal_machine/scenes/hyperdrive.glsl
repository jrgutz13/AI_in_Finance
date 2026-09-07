// Warp-speed flight: light streaks accelerate OUTWARD past the camera
// (forward motion, like the neon tunnel), over a drifting nebula, with
// star dust and a chromatic core.
// u_p1: streak density   u_p2: fly speed
// u_p3: streak length    u_p4: color spread across angle

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;

    // slow camera roll and drift
    uv = rot(t * 0.04) * uv;
    uv += 0.05 * vec2(sin(t * 0.5), cos(t * 0.37));

    float r = length(uv) + 1e-4;
    float a = atan(uv.y, uv.x);

    // --- nebula backdrop: dim slow-churning clouds ---------------------
    vec2 np = rot(t * 0.02) * uv;
    float neb = fbm(np * 2.2 + vec2(t * 0.03, -t * 0.02));
    neb = neb * fbm(np * 4.5 - t * 0.015);
    vec3 col = pal(neb * 1.5 + 0.55) * neb * 0.28;

    // --- light streaks flying outward ----------------------------------
    // Each angular sector owns a streak that repeatedly flies from the
    // center out past the edge. z is its life phase; the head position
    // accelerates outward (pow) so it reads as true 3D approach.
    for (int layer = 0; layer < 4; layer++) {
        float fl = float(layer);
        float sectors = u_p1 * (50.0 + fl * 45.0);
        float aa = a + fl * 1.618;
        float id = floor(aa / TAU * sectors);
        float h = hash11(id + fl * 113.7);
        float frac = fract(aa / TAU * sectors);

        float z = fract(h * 9.7 + t * u_p2 * (0.35 + 0.55 * h));
        float head = pow(z, 1.7) * 1.45;               // accelerates outward
        float len = u_p3 * (0.15 + 0.85 * z) * (0.4 + 0.6 * h);

        // bright head, tapering tail behind it (closer to the center)
        float body = smoothstep(head - len, head, r) * step(r, head);
        float tip  = smoothstep(head - 0.03, head, r) * step(r, head + 0.01);
        // keep streaks needle-thin at every radius: the angular window
        // shrinks as 1/r so the on-screen width stays constant
        float halfw = clamp(0.010 * sectors / (TAU * r), 0.02, 0.45);
        float thin = smoothstep(halfw, halfw * 0.25, abs(frac - 0.5));

        float bright = (body * body * 0.75 + tip * 1.6) * thin
                       * smoothstep(0.0, 0.15, z)       // born dim at center
                       * (0.95 - fl * 0.16);
        col += pal(h * u_p4 + fl * 0.11 + t * 0.05) * bright;
    }

    // --- star dust: tiny particles streaming past ----------------------
    for (int layer = 0; layer < 2; layer++) {
        float fl = float(layer);
        float sectors = 260.0 + fl * 140.0;
        float aa = a + fl * 0.83;
        float id = floor(aa / TAU * sectors);
        float h = hash11(id + fl * 77.3 + 31.0);
        float frac = fract(aa / TAU * sectors);

        float z = fract(h * 13.1 + t * u_p2 * (0.6 + 0.5 * h));
        float head = pow(z, 1.6) * 1.4;
        float halfw = clamp(0.006 * sectors / (TAU * r), 0.03, 0.45);
        float dot_ = smoothstep(0.02, 0.0, abs(r - head))
                     * smoothstep(halfw, halfw * 0.2, abs(frac - 0.5));
        col += pal(h * 0.8 + 0.3) * dot_ * z * 0.7 * (1.0 - fl * 0.3);
    }

    // --- chromatic core with soft rotating rays ------------------------
    float core = 0.028 / r * smoothstep(0.7, 0.0, r);
    vec3 coreCol = vec3(
        core * (1.0 + 0.25 * sin(t * 0.9)),
        0.030 / (r + 0.01) * smoothstep(0.7, 0.0, r),
        0.033 / (r + 0.02) * smoothstep(0.75, 0.0, r));
    col += coreCol * pal(t * 0.07) * 1.4;
    float rays = pow(abs(sin(a * 5.0 + t * 0.25)), 6.0)
               + pow(abs(sin(a * 3.0 - t * 0.18)), 8.0);
    col += pal(0.6 + t * 0.03) * rays * 0.12 * smoothstep(0.9, 0.05, r);

    fragColor = vec4(tonemap(col * 1.5), 1.0);
}
