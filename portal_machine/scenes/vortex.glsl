// A whirlpool of glowing filaments spiraling outward forever, with sparks
// riding the arms. Log-periodic, so the flow never ends.
// u_p1: filament arms (3..7)   u_p2: twist tightness
// u_p3: flow speed             u_p4: spark amount

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    uv += 0.05 * vec2(sin(t * 0.37), cos(t * 0.29));

    float r = length(uv) + 1e-5;
    float a = atan(uv.y, uv.x);
    float rho = log(r);
    float arms = floor(u_p1 + 0.5);

    float phase = mod(t * u_p3 * 0.7, TAU);
    float zc = rho * 2.5 - phase;

    vec3 col = vec3(0.0);
    // three harmonics of filaments, progressively finer and dimmer
    for (int h = 1; h <= 3; h++) {
        float fh = float(h);
        float s = a * arms * fh + zc * u_p2 * (0.8 + 0.4 * fh)
                + 0.35 * sin(zc * fh + a * 2.0);       // organic wobble
        float fil = pow(1.0 - abs(sin(s)), 14.0 + 6.0 * fh);
        col += pal(fh * 0.16 + sin(zc * 0.7) * 0.3 + t * 0.02)
               * fil * (1.1 / fh);
    }

    // sparks swept along the filaments
    float sp = noise(vec2(a * arms * 2.0 + zc * u_p2, zc * 4.0));
    col += vec3(1.0) * pow(sp, 12.0) * u_p4 * 1.3;

    // periodic mist between the arms for depth
    vec2 circ = vec2(cos(zc), sin(zc));
    float mist = fbm(circ + vec2(cos(a * 2.0), sin(a * 2.0)) * 0.8);
    col += pal(mist + 0.55) * mist * 0.16;

    // luminous eye of the vortex
    col += pal(t * 0.06) * 0.035 / (r + 0.06) * smoothstep(0.6, 0.0, r);

    col *= smoothstep(0.0, 0.2, r);
    col *= 1.0 - 0.35 * smoothstep(0.75, 1.25, r);
    fragColor = vec4(tonemap(col * 1.5), 1.0);
}
