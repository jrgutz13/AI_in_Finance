// Refik Anadol-style "wind map": thousands of luminous streamlines flowing
// sideways, bending through invisible turbulence, layered for depth.
// u_p1: streamline frequency   u_p2: turbulence
// u_p3: drift speed            u_p4: curl amount

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    float drift = t * u_p3;

    vec3 col = vec3(0.0);

    // three depth layers of streamlines, each with its own speed and scale
    for (int layer = 0; layer < 3; layer++) {
        float fl = float(layer);
        float depth = 1.0 - fl * 0.28;             // nearer layers brighter
        float spd = drift * (0.55 + 0.4 * fl);
        vec2 lp = uv * (1.0 + fl * 0.35) + vec2(0.0, fl * 3.7);

        // the wind field: bends the streamlines, slowly evolving
        float bend = fbm(vec2(lp.x * 1.3 - spd * 0.35, lp.y * 1.6) * (0.6 + 0.25 * u_p2) + fl * 11.0);
        float bend2 = fbm(vec2(lp.x * 0.6 - spd * 0.2, lp.y * 0.8) - fl * 7.0);
        float yw = lp.y * u_p1 * (0.6 + 0.2 * fl)
                 + u_p2 * u_p4 * 1.0 * (bend - 0.5)
                 + u_p4 * 3.5 * (bend2 - 0.5);

        // ribbons: sharp luminous lines with a soft halo
        float band = abs(sin(yw * 3.14159));
        float line = pow(1.0 - band, 24.0) * 1.4 + pow(1.0 - band, 6.0) * 0.22;

        // brightness pulses traveling ALONG each line (visible flow)
        float pulse = 0.55 + 0.45 * sin(lp.x * 9.0 - spd * 4.0
                                        + floor(yw + 0.5) * 2.7);
        // streaky horizontal texture inside the flow
        float tex = fbm(vec2(lp.x * 2.0 - spd * 0.9, yw * 0.35));

        vec3 lcol = pal(floor(yw + 0.5) * 0.11 + tex * 0.7 + fl * 0.13 + t * 0.02);
        col += lcol * line * pulse * depth * (0.7 + 0.7 * tex);
        // soft inter-line haze so the space between lines isn't dead
        col += lcol * tex * tex * 0.16 * depth;
    }

    // drifting dust motes carried on the wind
    vec2 cell = vec2(uv.x * 34.0 - drift * 2.6, uv.y * 34.0);
    vec2 ci = floor(cell);
    float ch = hash21(ci);
    vec2 cf = fract(cell) - 0.5;
    cf.y += (ch - 0.5) * 0.6;
    float mote = smoothstep(0.09 + 0.1 * ch, 0.0, length(cf)) * step(0.55, ch);
    col += pal(ch + t * 0.02) * mote * 0.5;

    // gentle vertical vignette, dark above and below
    col *= 1.0 - 0.4 * smoothstep(0.42, 0.8, abs(uv.y));

    fragColor = vec4(tonemap(col * 1.9), 1.0);
}
