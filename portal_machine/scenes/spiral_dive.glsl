// True infinite zoom down a logarithmic spiral: the pattern is periodic in
// log-radius, so the dive literally never ends and never loses precision.
// u_p1: spiral arms (2..6)   u_p2: twist tightness
// u_p3: dive speed           u_p4: detail amount

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    uv += 0.06 * vec2(sin(t * 0.33), cos(t * 0.27));

    float r = length(uv) + 1e-5;
    float a = atan(uv.y, uv.x);
    float rho = log(r);
    float arms = floor(u_p1 + 0.5);

    // phase kept in [0, TAU): everything below is TAU-periodic in zc,
    // so the zoom runs forever with no float blow-up
    float phase = mod(t * u_p3 * 0.6, TAU);
    float zc = rho * 3.0 - phase;              // log-depth coordinate
    float s = a * arms + zc * u_p2;            // spiral coordinate

    // broad glowing arms + razor edge lines
    float band = sin(s);
    float armGlow = pow(abs(band), 3.0);
    float edge = pow(1.0 - abs(band), 24.0);

    // periodic organic detail (sampled on a circle so it tiles in depth)
    vec2 circ = vec2(cos(zc), sin(zc));
    float det = fbm(circ * 1.4 + vec2(cos(a * arms), sin(a * arms)) * 0.9);

    // rings pulsing along the dive
    float ring = pow(abs(sin(zc * 2.0 + det * 2.5)), 12.0);

    // cos(a) not raw a, and sin(s) not raw s: raw angles seam at +-pi
    vec3 col = pal(sin(zc * 0.5) * 0.4 + 0.1 * cos(a) + det * u_p4 + t * 0.02)
               * (0.25 + 0.75 * armGlow);
    col += pal(det + 0.45) * edge * 1.3;
    col += pal(sin(zc) * 0.3 + 0.6) * ring * 0.5;

    // sparkling particles caught in the spiral
    float sp = noise(vec2(sin(s) * 2.5, zc * 3.0));
    col += vec3(1.0) * pow(sp, 14.0) * 1.1;

    // the center is infinitely far away: fade it to darkness
    col *= smoothstep(0.0, 0.3, r);
    col *= 1.0 - 0.35 * smoothstep(0.75, 1.25, r);

    fragColor = vec4(tonemap(col * 1.4), 1.0);
}
