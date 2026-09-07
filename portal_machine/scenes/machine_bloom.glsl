// Refik Anadol "Unsupervised" style: a living bloom of particle pigment
// that surges, swells and folds into itself, floating in a dark space.
// u_p1: structure scale   u_p2: churn strength
// u_p3: surge speed       u_p4: bloom size

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    float ft = t * u_p3;

    // rotational surge: the whole mass slowly kneads around its center
    float r0 = length(uv);
    vec2 p = rot(0.25 * sin(ft * 0.11) + r0 * 0.9 * sin(ft * 0.07)) * uv;

    // billowing fluid with an upward surge bias (waves crashing in slow motion)
    vec2 s = p * u_p1;
    vec2 q = vec2(fbm(s + vec2(0.0, -ft * 0.22)),
                  fbm(s + vec2(3.7, 8.1) + ft * 0.13));
    vec2 w = vec2(fbm(s + u_p2 * q + vec2(9.2, 1.4) - ft * 0.17),
                  fbm(s + u_p2 * q + vec2(2.6, 6.3) + vec2(0.0, -ft * 0.26)));
    float v = fbm(s + u_p2 * w);

    // bloom mask: a rounded mass whose rim billows with the fluid
    float edge = r0 / u_p4 - 0.68 - 0.42 * (fbm(p * 1.4 + ft * 0.06) - 0.5)
                 - 0.3 * (v - 0.5);
    float mass = smoothstep(0.16, -0.2, edge);

    // saturated pigment: three palette pulls churned together
    vec3 col = pal(v * 2.2 + q.x + t * 0.03);
    col = mix(col, pal(w.y * 1.6 + 0.45), smoothstep(0.25, 0.75, q.y));
    col = mix(col, pal(v + w.x + 0.8), smoothstep(0.55, 0.95, v) * 0.7);
    col *= 0.4 + 1.3 * v;

    // dense particle grain
    float g1 = noise(uv * 260.0 + w * 11.0 + ft * 1.3);
    float g2 = noise(uv * 520.0 - w * 15.0 - ft * 2.1);
    col *= 0.5 + 1.0 * g1 * g2;
    col += pal(v + 0.5) * pow(g2, 9.0) * 1.6 * smoothstep(0.3, 0.7, v);

    // bright surf where the fluid folds over itself
    float crest = pow(smoothstep(0.55, 0.9, fbm(s + u_p2 * w + vec2(0.0, -ft * 0.3))), 3.0);
    col += pal(0.15 + v) * crest * 1.2;

    col *= mass;
    col += pal(0.6) * 0.014 * (1.0 - mass);   // faint gallery glow

    fragColor = vec4(tonemap(col * 1.7), 1.0);
}
