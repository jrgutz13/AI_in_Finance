// Slow liquid-marble flow: domain-warped noise, optionally kaleido-folded.
// u_p1: pattern scale     u_p2: warp strength
// u_p3: flow speed        u_p4: wedge count (0 = no fold)

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;

    if (u_p4 > 0.5) {
        float n = floor(u_p4 + 0.5);
        float a = atan(uv.y, uv.x);
        float r = length(uv);
        float seg = TAU / n;
        a = mod(a, seg);
        a = abs(a - seg * 0.5);
        uv = vec2(cos(a), sin(a)) * r;
    }

    vec2 p = uv * u_p1;
    float ft = t * u_p3;

    vec2 q = vec2(fbm(p + ft * 0.30),
                  fbm(p + vec2(5.2, 1.3) - ft * 0.21));
    vec2 w = vec2(fbm(p + u_p2 * q + vec2(1.7, 9.2) + ft * 0.45),
                  fbm(p + u_p2 * q + vec2(8.3, 2.8) - ft * 0.26));
    float v = fbm(p + u_p2 * w);

    vec3 col = pal(v * 1.6 + q.x * 0.6 + t * 0.04);
    // pearly sheen on the flow lines
    col += 0.3 * pal(v + 0.45) * pow(abs(sin(v * 9.0 + ft)), 16.0);
    col *= 0.65 + 0.5 * v;

    fragColor = vec4(col, 1.0);
}
