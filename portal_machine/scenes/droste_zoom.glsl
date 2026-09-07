// Endless Droste zoom: rings of glowing gems grow from the center and fly
// past forever. Layered self-similar scales, like the neon tunnel's trick.
// u_p1: gems per ring (5..9)   u_p2: gem roundness
// u_p3: zoom speed             u_p4: color spread

float sdPoly(vec2 p, float n, float rad) {
    float a = atan(p.x, p.y);
    float seg = TAU / n;
    a = mod(a, seg) - seg * 0.5;
    return length(p) * cos(a) - rad;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    uv += 0.05 * vec2(sin(t * 0.29), cos(t * 0.22));

    float m = floor(u_p1 + 0.5);              // gems per ring
    vec3 col = vec3(0.0);

    const int RINGS = 14;
    for (int i = 0; i < RINGS; i++) {
        float fi = float(i);
        // ring depth: grows from the center outward forever
        float z = fract(fi / float(RINGS) + t * u_p3 * 0.1);
        float scale = exp(mix(-3.2, 0.55, z));
        float ringRot = fi * 0.5 + t * 0.06 * (mod(fi, 2.0) * 2.0 - 1.0);

        // place m gems around this ring
        float a = atan(uv.y, uv.x) + ringRot;
        float sect = TAU / m;
        // wrap the index modulo m so a gem keeps one identity across the
        // atan seam at +-pi (raw floor() would give it two colors there)
        float idx = mod(floor(a / sect), m);
        float ga = (floor(a / sect) + 0.5) * sect - ringRot;
        vec2 center = vec2(cos(ga), sin(ga)) * scale;

        vec2 lp = (uv - center) / scale;      // gem-local coords
        lp = rot(t * 0.3 + fi + idx) * lp;
        // blend polygon->circle for roundness
        float dPoly = sdPoly(lp, 3.0 + mod(idx + fi, 3.0), 0.34);
        float dCirc = length(lp) - 0.34;
        float d = mix(dPoly, dCirc, u_p2);

        float fade = smoothstep(0.0, 0.2, z) * smoothstep(1.0, 0.85, z);
        float body = smoothstep(0.015, -0.015, d);
        float facet = pow(1.0 - clamp(abs(d + 0.12) * 8.0, 0.0, 1.0), 3.0);
        float glowLine = 0.010 / (abs(d) + 0.010);

        vec3 gcol = pal(hash11(idx + fi * 7.0) * u_p4 + z * 0.5 + t * 0.03);
        col += gcol * (body * (0.25 + 0.6 * z) + facet * body * 0.4
                       + glowLine * 0.4) * fade;
    }

    // luminous thread spiraling through the rings
    float r = length(uv) + 1e-5;
    float thread = pow(abs(sin(log(r) * 3.0 - t * u_p3 * 0.3 + atan(uv.y, uv.x))), 30.0);
    col += pal(0.5 + t * 0.02) * thread * 0.4 * smoothstep(0.0, 0.2, r);

    col *= smoothstep(0.0, 0.12, r);          // infinite dark center
    fragColor = vec4(tonemap(col * 1.6), 1.0);
}
