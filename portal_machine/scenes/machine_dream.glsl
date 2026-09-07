// Refik Anadol-style "data sculpture": a churning cloud of millions of
// colored data-particles, billowing like slow fluid inside a dark space.
// u_p1: structure scale   u_p2: churn strength
// u_p3: flow speed        u_p4: sculpture size

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    float ft = t * u_p3;

    // --- the fluid: two levels of domain warp, billowy and slow --------
    vec2 p = uv * u_p1;
    vec2 q = vec2(fbm(p + ft * 0.16),
                  fbm(p + vec2(4.7, 2.3) - ft * 0.11));
    vec2 w = vec2(fbm(p + u_p2 * q + vec2(1.9, 8.4) + ft * 0.23),
                  fbm(p + u_p2 * q + vec2(7.2, 3.1) - ft * 0.14));
    float v = fbm(p + u_p2 * w);

    // --- the sculpture mask: a billowing mass floating in the void -----
    float blob = fbm(uv * 1.25 + vec2(ft * 0.05, -ft * 0.03));
    float edge = length(uv * vec2(1.0, 1.25)) / u_p4
                 - 0.62 - 0.5 * (blob - 0.5) - 0.25 * (v - 0.5);
    float mass = smoothstep(0.18, -0.22, edge);

    // --- pigment: several colors churning into each other --------------
    vec3 col = pal(v * 1.9 + q.y * 0.8 + t * 0.03);
    col = mix(col, pal(q.x * 1.4 + 0.35 - t * 0.02), smoothstep(0.3, 0.8, w.y));
    col *= 0.45 + 1.1 * v;

    // --- particle grain: reads as millions of tiny data points ---------
    float g1 = noise(uv * 240.0 + w * 9.0 + ft * 1.1);
    float g2 = noise(uv * 470.0 - w * 13.0 - ft * 1.7);
    float grain = 0.55 + 0.9 * g1 * g2;
    col *= grain;
    // sparkling specks where the grain peaks
    col += pal(v + 0.5) * pow(g2, 10.0) * 1.4 * smoothstep(0.35, 0.7, v);

    // --- internal glowing seams, like data currents --------------------
    col += pal(v * 1.9 + 0.45) * pow(abs(sin(v * 7.0 - ft * 0.6)), 18.0) * 0.7;

    col *= mass;
    // faint ambient spill so the void is not pure black
    col += pal(0.6) * 0.012 * (1.0 - mass);

    fragColor = vec4(tonemap(col * 1.6), 1.0);
}
