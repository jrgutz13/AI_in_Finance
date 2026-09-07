// Hypnotic Zeno nest: crisp concentric polygons spiral out of the center
// forever, each turned slightly against the last. Hard geometric edges.
// u_p1: sides (3..6)     u_p2: twist per layer
// u_p3: zoom speed       u_p4: color cycle spread

float sdPoly(vec2 p, float n, float rad) {
    float a = atan(p.x, p.y);
    float seg = TAU / n;
    a = mod(a, seg) - seg * 0.5;
    return length(p) * cos(a) - rad;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    float n = floor(u_p1 + 0.5);

    uv = rot(t * 0.03) * uv;                   // slow global spin

    vec3 col = vec3(0.0);
    float coverage = 0.0;
    const int LAYERS = 22;
    for (int i = 0; i < LAYERS; i++) {
        float fi = float(i);
        float z = fract(fi / float(LAYERS) + t * u_p3 * 0.08);
        float scale = exp(mix(-3.4, 0.6, z));

        vec2 p = rot(u_p2 * fi + t * 0.1 * (mod(fi, 2.0) * 2.0 - 1.0)) * uv;
        float d = sdPoly(p / scale, n, 1.0);

        // crisp band: filled between this polygon edge and 78% of it
        float band = smoothstep(0.012, 0.0, d) * smoothstep(-0.3, -0.28, d);
        float fade = smoothstep(0.0, 0.18, z) * smoothstep(1.0, 0.9, z);

        vec3 bcol = pal(fi * u_p4 * 0.13 + z * 0.4 + t * 0.05);
        // paint on top (nearer layers cover farther ones)
        col = mix(col, bcol, band * fade * (1.0 - coverage) );
        coverage = min(1.0, coverage + band * fade * 0.0);   // keep additive feel

        // razor edge light
        col += bcol * (0.008 / (abs(d) + 0.008)) * fade * 0.25;
    }

    // breathing center glow
    float r = length(uv);
    col += pal(t * 0.07) * (0.5 + 0.5 * sin(t * 0.9)) * 0.03 / (r + 0.05);

    col *= 1.0 - 0.4 * smoothstep(0.7, 1.25, r);
    fragColor = vec4(tonemap(col * 1.6), 1.0);
}
