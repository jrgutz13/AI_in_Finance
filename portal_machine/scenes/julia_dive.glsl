// Slow dive into a morphing Julia fractal, colored by orbit traps.
// u_p1: shape c.x   u_p2: shape c.y
// u_p3: zoom rate   u_p4: trap color mix

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;

    // same overflow-safe zoom scheme as fractal_zoom
    float zoom;
    if (u_continuous > 0.5) {
        zoom = 0.8 * exp(2.2 * (0.5 - 0.5 * cos(t * u_p3 * 0.05)));
    } else {
        zoom = 0.8 * exp(t * u_p3 * 0.2);
    }
    vec2 z = rot(t * 0.05) * uv * 1.4 / zoom;

    // the Julia constant drifts slowly around the interesting rim
    vec2 c = vec2(u_p1 + 0.035 * sin(t * 0.17),
                  u_p2 + 0.035 * cos(t * 0.13));

    float trapCirc = 100.0;   // distance to a circle |z|=0.35
    float trapLine = 100.0;   // distance to the x-axis
    float steps = 0.0;
    for (int i = 0; i < 60; i++) {
        z = vec2(z.x * z.x - z.y * z.y, 2.0 * z.x * z.y) + c;
        float l2 = dot(z, z);
        trapCirc = min(trapCirc, abs(length(z) - 0.35));
        trapLine = min(trapLine, abs(z.y));
        if (l2 > 64.0) break;
        steps += 1.0;
    }
    // smooth escape count
    float nu = steps - log2(max(1.0, log2(max(dot(z, z), 1.0001))));

    vec3 col = pal(nu * 0.045 + t * 0.025);
    col = mix(col, pal(trapCirc * 2.2 + 0.35), u_p4 * exp(-trapCirc * 5.0));
    col += pal(0.6 + nu * 0.03) * exp(-trapLine * 9.0) * 0.55;
    // keep the far-outside region near-black so the fractal glows against it
    col *= 0.06 + 0.94 * smoothstep(0.0, 12.0, nu);

    fragColor = vec4(tonemap(col * 1.5), 1.0);
}
