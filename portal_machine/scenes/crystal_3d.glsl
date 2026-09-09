// TRUE 3D: drifting through a cave of glowing crystal shards. Sharp facets,
// strong fresnel edges and an inner light that bleeds through the stone.
// u_p1: crystal size     u_p2: cluster spread
// u_p3: drift speed      u_p4: inner glow

#define CELL 3.2

// one crystal cluster per lattice cell, each rotated by its own hash
float crystalDE(vec3 p, float size, float spread, out float trap) {
    vec3 id = floor(p / CELL);
    vec3 q = mod(p, CELL) - CELL * 0.5;

    float h = hash21(id.xy + id.z * 37.0);
    float h2 = hash11(h * 91.7);
    // push the cluster off-centre so the lattice never looks like a grid
    q -= (vec3(h, h2, fract(h * 7.3)) - 0.5) * spread;
    q = rotY(h * TAU) * rotX(h2 * TAU) * q;

    trap = h;
    // intersecting octahedra and a slab make a faceted shard
    float d = sdOctahedron(q, size * (0.55 + 0.5 * h));
    d = max(d, -sdOctahedron(rotZ(1.1) * q, size * 0.42));   // hollow it out
    d = max(d, sdBox(rotZ(h * 3.1) * q, vec3(size * 1.1, size * 0.42, size * 1.1)));

    // a second, smaller shard offset the other way — without this the cells
    // line up along the view axis and leave a visible dark cross ahead
    vec3 q2 = mod(p + CELL * 0.5, CELL) - CELL * 0.5;
    float h3 = hash21(floor((p + CELL * 0.5) / CELL).xy * 1.7
                      + floor((p.z + CELL * 0.5) / CELL) * 53.0);
    q2 -= (vec3(h3, fract(h3 * 5.1), fract(h3 * 11.3)) - 0.5) * spread * 0.8;
    q2 = rotZ(h3 * TAU) * rotY(fract(h3 * 3.7) * TAU) * q2;
    d = min(d, sdOctahedron(q2, size * (0.30 + 0.25 * h3)));
    return d;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;

    float zoff = mod(t * u_p3 * 1.0, CELL);

    vec3 ro = vec3(0.5 * sin(t * 0.09), 0.4 * cos(t * 0.07), 0.0);
    vec3 rd = normalize(vec3(rot(t * 0.04) * uv, 1.4));

    float dist = 0.0, trap = 0.0, tr;
    bool hit = false;
    vec3 glow = vec3(0.0);

    for (int i = 0; i < 100; i++) {
        vec3 p = ro + rd * dist;
        vec3 q = p;
        q.z += zoff;

        float d = crystalDE(q, u_p1, u_p2, tr);
        // light trapped inside the crystals leaks out through the facets
        glow += pal(tr * 1.5 + t * 0.03)
              * (0.013 * u_p4 / (abs(d) + 0.07)) * exp(-dist * 0.19);

        if (d < 0.0012 * dist + 0.001) { hit = true; trap = tr; break; }
        dist += max(d * 0.7, 0.006);
        if (dist > 28.0) break;
    }

    vec3 fogCol = pal(0.62 + t * 0.02) * 0.04;
    vec3 col = fogCol;

    if (hit) {
        vec3 p = ro + rd * dist;
        vec2 e = vec2(0.0014, 0.0);
        vec3 q0 = p; q0.z += zoff;
        float c = crystalDE(q0, u_p1, u_p2, tr);
        vec3 n = normalize(vec3(crystalDE(q0 + e.xyy, u_p1, u_p2, tr) - c,
                                crystalDE(q0 + e.yxy, u_p1, u_p2, tr) - c,
                                crystalDE(q0 + e.yyx, u_p1, u_p2, tr) - c));

        vec3 ld = normalize(vec3(0.5, 0.7, -0.6));
        float diff = max(dot(n, ld), 0.0);
        float spec = pow(max(dot(reflect(-ld, n), -rd), 0.0), 48.0);
        // strong fresnel is what sells glass: edges glow, faces stay clear
        float fres = pow(1.0 - max(dot(n, -rd), 0.0), 2.2);

        vec3 body = pal(trap * 1.5 + 0.1 + t * 0.02);
        col = body * (0.10 + 0.55 * diff);
        col += vec3(1.0) * spec * 0.9;
        col += pal(trap * 1.5 + 0.45) * fres * 1.4;
        // internal light: the shard glows from inside as well as reflecting
        col += body * u_p4 * 0.35 * (0.5 + 0.5 * sin(trap * 30.0 + t));
        float fog = exp(-dist * 0.17);
        col = col * fog + fogCol * (1.0 - fog);
    }

    col += glow;
    fragColor = vec4(tonemap(col * 1.5), 1.0);
}
