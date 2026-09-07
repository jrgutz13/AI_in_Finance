// Refik Anadol ocean-data style: rolling waves of luminous particles,
// stacked with parallax, crests breaking into sparkling foam.
// u_p1: wave scale   u_p2: turbulence
// u_p3: drift speed  u_p4: swell amount

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    float drift = t * u_p3;

    vec3 col = vec3(0.0);

    // five wave layers, back to front
    for (int i = 0; i < 5; i++) {
        float fi = float(i);
        float depth = fi / 4.0;                       // 0 = far, 1 = near
        float spd = drift * (0.4 + 0.5 * depth);
        float x = uv.x * u_p1 * (1.6 - 0.7 * depth);

        // the wave surface: big swell + turbulent detail
        float h = -0.42 + 0.75 * depth
                + u_p4 * 0.16 * sin(x * 1.3 + spd + fi * 2.1)
                + u_p4 * 0.09 * sin(x * 2.7 - spd * 1.4 + fi)
                + u_p2 * 0.10 * (fbm(vec2(x * 1.5 - spd, fi * 7.3)) - 0.5);

        float d = uv.y - h;                            // above/below surface
        // luminous particle body below the surface: organic swirl + fine grain
        float body = smoothstep(0.02, -0.35, d);
        float g = fbm(vec2(x * 1.8 - spd * 0.7, (uv.y + fi * 3.1) * 3.5));
        float fine = noise(vec2(x * 60.0 - spd * 9.0, uv.y * 130.0 + fi * 17.0))
                   * noise(vec2(x * 113.0 - spd * 14.0, uv.y * 240.0 - fi * 9.0));
        vec3 wcol = pal(depth * 0.55 + g * 0.5 + t * 0.02);
        col = mix(col, wcol * (0.3 + 1.0 * g) * (0.5 + 0.9 * fine)
                        * (0.45 + 0.55 * depth), body);

        // glowing crest line with breaking foam sparkle
        float crest = pow(smoothstep(0.05, 0.0, abs(d)), 3.0);
        float foam = pow(fine, 2.0) * smoothstep(0.07, 0.0, abs(d - 0.01));
        col += wcol * crest * (0.6 + 0.6 * depth);
        col += vec3(1.0) * foam * depth * 2.2;
    }

    // spray motes drifting above the waves
    vec2 cell = vec2(uv.x * 40.0 - drift * 2.0, uv.y * 40.0);
    float ch = hash21(floor(cell));
    float mote = smoothstep(0.1, 0.0, length(fract(cell) - 0.5)) * step(0.72, ch);
    col += pal(ch) * mote * 0.6;

    col *= 1.0 - 0.35 * smoothstep(0.4, 0.9, abs(uv.x));   // side falloff

    fragColor = vec4(tonemap(col * 1.5), 1.0);
}
