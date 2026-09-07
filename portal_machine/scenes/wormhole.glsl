// Flying down an organic textured tube with a swirl.
// u_p1: angular pattern repeat   u_p2: swirl strength
// u_p3: ring frequency           u_p4: fly speed multiplier

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;

    // wobble the camera off-axis
    uv += 0.1 * vec2(sin(t * 0.4), cos(t * 0.33));

    float r = length(uv) + 1e-4;
    float a = atan(uv.y, uv.x);
    float tube = 0.35 / r;                  // perspective depth along the tube
    a += u_p2 * 0.15 / (r + 0.1);           // swirl increases toward center

    float fly = t * (1.2 * u_p4);
    // sample noise on a circle (integer angular frequency) so there is no
    // seam where atan wraps from +pi to -pi
    float k = floor(u_p1 + 0.5);
    vec2 circ = vec2(cos(a * k), sin(a * k));

    float v = fbm(circ * 1.5 + vec2(0.0, tube + fly));
    v += 0.5 * fbm(circ * 3.0 + vec2(tube * 2.0 + fly * 1.7, -fly * 0.3));

    // luminous rings rushing past — "+ fly" makes them fly OUTWARD toward the
    // camera (forward motion), matching the flowing wall texture above
    float rings = pow(abs(sin(tube * u_p3 + fly * 2.5 + v * 3.0)), 6.0);

    vec3 col = pal(v * 1.2 + tube * 0.05 + t * 0.03);
    col += pal(v + 0.5) * rings * 0.8;

    // depth fog: darken toward the infinitely-far center
    col *= smoothstep(0.0, 0.35, r);
    // soften the outer edge
    col *= 1.0 - 0.3 * smoothstep(0.7, 1.2, r);

    fragColor = vec4(col, 1.0);
}
