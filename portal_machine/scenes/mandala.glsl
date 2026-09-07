// Crisp geometric mandala: petals, pulsing concentric rings, counter-rotation.
// u_p1: petal count (6..16)    u_p2: ring frequency
// u_p3: petal sharpness        u_p4: pulse amount

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    float n = floor(u_p1 + 0.5);

    float r = length(uv);
    float a = atan(uv.y, uv.x);

    // two counter-rotating petal layers
    float pet1 = cos(a * n + t * 0.7 + sin(r * 6.0 - t) * 0.8);
    float pet2 = cos(a * n * 0.5 - t * 0.45 + cos(r * 4.0 + t * 0.6));
    float petals = pow(abs(pet1), u_p3) + 0.7 * pow(abs(pet2), u_p3 * 0.7);

    // breathing concentric rings
    float rr = r * (1.0 + u_p4 * 0.25 * sin(t * 0.8));
    float rings = sin(rr * u_p2 * 10.0 - t * 1.5);
    float ringGlow = pow(abs(rings), 8.0);

    float v = petals * 0.5 + rings * 0.3;
    vec3 col = pal(v + r * 0.7 + t * 0.05) * (0.35 + 0.65 * petals);
    col += pal(r * 0.5 + 0.4) * ringGlow * 0.6;

    // bright center heart
    col += pal(t * 0.1) * 0.05 / (r + 0.07);

    col *= 1.0 - 0.5 * smoothstep(0.5, 1.1, r);
    fragColor = vec4(tonemap(col * 1.4), 1.0);
}
