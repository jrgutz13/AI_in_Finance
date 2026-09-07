// Glowing polygon portals receding into the distance.
// u_p1: polygon sides (3..8)   u_p2: twist per depth
// u_p3: spin speed             u_p4: center glow amount

float sdPoly(vec2 p, float n, float r) {
    float a = atan(p.x, p.y);
    float seg = TAU / n;
    a = mod(a, seg) - seg * 0.5;
    return length(p) * cos(a) - r;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    float n = floor(u_p1 + 0.5);

    // slow camera drift so the tunnel is not perfectly centered
    uv += 0.08 * vec2(sin(t * 0.31), cos(t * 0.23));

    vec3 col = vec3(0.0);
    const int RINGS = 36;
    for (int i = 0; i < RINGS; i++) {
        float fi = float(i);
        // each ring flies toward the camera, looping forever
        float z = fract(fi / float(RINGS) + t * 0.18);
        float dist = exp(mix(2.6, -1.2, z));   // far -> near
        vec2 p = uv * dist;
        p = rot(u_p2 * dist + t * u_p3 + fi * 0.05) * p;
        float d = abs(sdPoly(p, n, 1.0)) / dist + 0.002;
        float glow = 0.006 / d;
        // fade in at the far end, fade out as it passes the camera
        glow *= smoothstep(0.0, 0.25, z) * smoothstep(1.0, 0.92, z);
        col += pal(fi * 0.045 + t * 0.15) * glow * (0.25 + 0.75 * z);
    }

    // hot core at the end of the tunnel
    col += pal(t * 0.1) * 0.02 * u_p4 / (length(uv) + 0.06);

    // subtle haze
    col += pal(0.5 + t * 0.02) * 0.02;

    fragColor = vec4(tonemap(col), 1.0);
}
