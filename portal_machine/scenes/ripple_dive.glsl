// The most meditative dive: soft luminous ripples emerge from infinite
// depth and glide outward forever, gently warped like water.
// u_p1: ripple frequency   u_p2: wobble amount
// u_p3: dive speed         u_p4: color spread

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;
    uv += 0.07 * vec2(sin(t * 0.21), cos(t * 0.17));

    float r = length(uv) + 1e-5;
    float a = atan(uv.y, uv.x);
    float rho = log(r);

    // organic wobble of the depth coordinate (seam-free: circle sampling)
    float wob = fbm(vec2(cos(a * 3.0), sin(a * 3.0)) * 1.1 + t * 0.05);
    float phase = mod(t * u_p3 * 0.5, TAU * 4.0);
    float zc = rho * u_p1 - phase + u_p2 * (wob - 0.5) * 2.0;

    // layered rings: a soft body, a bright rim, and a whisper-thin echo
    float wave = sin(zc);
    float body = 0.5 + 0.5 * wave;
    float rim  = pow(1.0 - abs(wave), 10.0);
    float echo = pow(abs(sin(zc * 2.0 + 1.3)), 30.0);

    // each ring keeps its own hue as it travels outward
    // sin(zc), not sin(zc*0.5): a half-multiple flips sign at every phase
    // wrap, which would snap every ring's color at once
    float ringId = sin(zc - 0.7);
    // cos(a) not raw a: raw angle has a seam where atan wraps at +-pi
    vec3 col = pal(ringId * u_p4 + 0.06 * cos(a + t * 0.1) + t * 0.015) * (0.18 + 0.5 * body);
    col += pal(ringId * u_p4 + 0.35) * rim * 0.9;
    col += pal(0.6 + ringId * 0.2) * echo * 0.3;

    // slow caustic shimmer across everything
    float shim = fbm(uv * 3.0 + vec2(t * 0.06, -t * 0.045));
    col *= 0.75 + 0.5 * shim;
    col += pal(shim + 0.5) * pow(shim, 6.0) * 0.4;

    // deep dark center, soft outer fade
    col *= smoothstep(0.0, 0.32, r);
    col *= 1.0 - 0.4 * smoothstep(0.7, 1.2, r);

    fragColor = vec4(tonemap(col * 1.5), 1.0);
}
