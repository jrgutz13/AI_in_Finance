// An endlessly blooming flower: rings of petals are born at the center and
// unfold outward forever, each ring turned by a golden-angle offset.
// u_p1: petals per ring (5..9)   u_p2: petal curl
// u_p3: bloom speed              u_p4: glow amount

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    float n = floor(u_p1 + 0.5);

    float r = length(uv) + 1e-5;
    float a = atan(uv.y, uv.x);

    vec3 col = vec3(0.0);
    const int LAYERS = 10;
    for (int i = 0; i < LAYERS; i++) {
        float fi = float(i);
        float z = fract(fi / float(LAYERS) + t * u_p3 * 0.07);
        float scale = exp(mix(-3.0, 0.5, z));

        // golden-angle rotation per ring keeps petals from ever aligning
        float ringRot = fi * 2.39996 + t * 0.05 * (mod(fi, 2.0) * 2.0 - 1.0);
        float aa = a + ringRot + u_p2 * log(r / scale);   // curled petals

        // petal silhouette: rose curve around this ring's radius
        float petalR = scale * (1.0 + 0.28 * cos(aa * n));
        float d = abs(r - petalR) / scale;

        float fade = smoothstep(0.0, 0.22, z) * smoothstep(1.0, 0.86, z);
        float edge = 0.011 / (d + 0.011);                 // luminous outline
        float fill = smoothstep(0.16, 0.0, d) * 0.35;     // soft petal body

        vec3 pcol = pal(fi * 0.09 + z * 0.4 + cos(aa * n) * 0.12 + t * 0.03);
        col += pcol * (edge * 0.5 * u_p4 + fill) * fade * (0.3 + 0.7 * z);
    }

    // glowing heart of the flower
    col += pal(t * 0.08) * 0.05 / (r + 0.05) * smoothstep(0.35, 0.0, r);
    // drifting pollen motes (round dots, not noise blocks)
    vec2 cell = uv * 26.0 + vec2(t * 0.35, -t * 0.22);
    float ch = hash21(floor(cell));
    float mote = smoothstep(0.1, 0.0, length(fract(cell) - 0.5)) * step(0.86, ch);
    col += pal(ch + 0.4) * mote * (0.4 + 0.3 * sin(ch * 40.0 + t * 2.0));

    col *= 1.0 - 0.35 * smoothstep(0.7, 1.2, r);
    fragColor = vec4(tonemap(col * 1.5), 1.0);
}
