// Mirrored-wedge kaleidoscope, cut sharp: crisp interference bands, thin
// luminous edge lines, a fine lattice layer, and crisp rings.
// u_p1: wedge count (5..12)    u_p2: breathe amount
// u_p3: pattern scale          u_p4: radial color drift

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    float n = floor(u_p1 + 0.5);

    float a = atan(uv.y, uv.x);
    float r = length(uv);
    float seg = TAU / n;
    a = mod(a + t * 0.05, seg);
    a = abs(a - seg * 0.5);            // mirror fold
    vec2 p = vec2(cos(a), sin(a)) * r;

    p *= 1.0 + u_p2 * sin(t * 0.4);    // breathing zoom
    p = rot(t * 0.13) * p;

    // base interference structure
    vec2 q = p * u_p3;
    float v = 0.0;
    for (int i = 0; i < 6; i++) {
        float fi = float(i);
        q = rot(0.7) * q;
        q += 0.32 * sin(q.yx * 1.7 + t * vec2(0.9, 1.1) + fi);
        v += sin(q.x * 3.0 + t) * cos(q.y * 3.0 - t * 0.8) / (1.0 + fi * 0.35);
    }

    // hard-edged color terracing instead of soft gradients: quantize the
    // field, then color by the level — reads as cut glass
    float lv = v * 1.6;
    float level = floor(lv);
    float f = lv - level;
    float edgeSharp = smoothstep(0.0, 0.06, f) * smoothstep(1.0, 0.94, f);
    vec3 col = pal(level * 0.14 + r * u_p4 + t * 0.06) * (0.55 + 0.45 * edgeSharp);

    // thin luminous lines exactly on the terrace edges
    float edgeLine = pow(1.0 - abs(f - 0.5) * 2.0, 30.0);
    col += pal(level * 0.14 + 0.4) * edgeLine * 1.1;

    // fine lattice detail layer, counter-rotating
    vec2 g = rot(-t * 0.07) * p * (u_p3 * 5.0);
    float lat = abs(fract(g.x) - 0.5) + abs(fract(g.y) - 0.5);
    col += pal(v * 0.3 + 0.25) * pow(max(0.0, 1.0 - lat), 14.0) * 0.5;

    // crisp concentric rings sweeping outward
    float ring = pow(abs(sin(r * 16.0 - t * 1.1)), 40.0);
    col += pal(r * 2.0 + 0.5) * ring * 0.4;

    // deepen darks for punch, gentle vignette
    col = pow(col, vec3(1.25)) * 1.05;
    col *= 1.0 - 0.45 * smoothstep(0.45, 1.1, r);

    fragColor = vec4(col, 1.0);
}
