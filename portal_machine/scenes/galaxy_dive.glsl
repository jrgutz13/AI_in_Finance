// Diving into the heart of a spiral galaxy: star shells stream past while
// nebular arms wheel slowly around a burning core.
// u_p1: spiral arms (2..4)   u_p2: nebula density
// u_p3: dive speed           u_p4: star density

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    uv = rot(t * 0.02) * uv;

    float r = length(uv) + 1e-5;
    float a = atan(uv.y, uv.x);
    float arms = floor(u_p1 + 0.5);

    // --- spiral nebula arms (log-periodic: they wheel forever) ---------
    // wrap at a whole number of TAU, and only use whole-number multiples of
    // zc below, so the wrap leaves the picture unchanged
    float phase = mod(t * u_p3 * 0.25, TAU * 4.0);
    float zc = log(r) * 2.0 - phase;
    float s = a * arms + zc * 2.0;
    float armBand = 0.5 + 0.5 * sin(s);
    vec2 circ = vec2(cos(zc), sin(zc));
    float cloud = fbm(circ * 1.2 + vec2(cos(a * arms), sin(a * arms)));
    float neb = pow(armBand, 1.6) * (0.35 + 0.9 * cloud) * u_p2;
    vec3 col = pal(cloud * 0.8 + armBand * 0.3 + t * 0.02) * neb * 0.5;
    // dark dust lane hugging each arm
    col *= 1.0 - 0.55 * pow(1.0 - abs(sin(s + 0.7)), 8.0);

    // --- star shells flying past (forward dive) ------------------------
    for (int layer = 0; layer < 3; layer++) {
        float fl = float(layer);
        float sectors = u_p4 * (150.0 + fl * 120.0);
        float aa = a + fl * 1.1;
        float id = floor(aa / TAU * sectors);
        float h = hash11(id + fl * 51.7);
        float frac = fract(aa / TAU * sectors);

        float z = fract(h * 11.3 + t * u_p3 * (0.25 + 0.3 * h));
        float head = pow(z, 1.5) * 1.35;
        float halfw = clamp(0.005 * sectors / (TAU * r), 0.04, 0.45);
        float star = smoothstep(0.014 + 0.01 * h, 0.0, abs(r - head))
                     * smoothstep(halfw, halfw * 0.2, abs(frac - 0.5));
        float tw = 0.6 + 0.4 * sin(h * 50.0 + t * 3.0);
        col += pal(h * 0.6 + 0.25) * star * z * tw * (1.0 - fl * 0.25);
    }

    // --- burning core with halo ----------------------------------------
    col += pal(0.1 + t * 0.04) * 0.05 / (r + 0.04) * smoothstep(0.8, 0.0, r);
    col += pal(0.45) * exp(-r * 3.0) * 0.35;

    col *= 1.0 - 0.3 * smoothstep(0.8, 1.3, r);
    fragColor = vec4(tonemap(col * 1.5), 1.0);
}
