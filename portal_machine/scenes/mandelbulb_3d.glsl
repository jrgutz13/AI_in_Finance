// TRUE 3D: orbiting a living Mandelbulb — the classic 3D fractal — whose
// power slowly morphs so the surface is forever growing new structure.
// Raymarched with a distance estimator, lit, with orbit-trap coloring.
// u_p1: fractal power (6..9)   u_p2: orbit tilt
// u_p3: orbit speed            u_p4: glow amount

// distance estimator for the Mandelbulb; also reports an orbit trap for color
float bulbDE(vec3 pos, float power, out float trap) {
    vec3 z = pos;
    float dr = 1.0;
    float r = 0.0;
    trap = 1e10;
    for (int i = 0; i < 9; i++) {
        r = length(z);
        if (r > 2.2) break;
        trap = min(trap, r);
        // convert to polar, raise to the power, convert back
        float theta = acos(clamp(z.z / r, -1.0, 1.0));
        float phi = atan(z.y, z.x);
        dr = pow(r, power - 1.0) * power * dr + 1.0;
        float zr = pow(r, power);
        theta *= power;
        phi *= power;
        z = zr * vec3(sin(theta) * cos(phi), sin(phi) * sin(theta), cos(theta));
        z += pos;
    }
    return 0.5 * log(max(r, 1e-6)) * r / dr;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;

    // the power breathes between whole numbers: the surface reorganises
    // continuously, which is what makes it feel alive rather than static
    float power = u_p1 + 1.2 * sin(t * 0.05);

    // camera orbits the fractal, slowly rising and falling
    float orbit = t * u_p3 * 0.12;
    float dist0 = 2.5 + 0.55 * sin(t * 0.07);
    vec3 ro = vec3(sin(orbit), u_p2 * sin(orbit * 0.6), cos(orbit)) * dist0;
    // look at the origin
    vec3 fw = normalize(-ro);
    vec3 rt = normalize(cross(vec3(0.0, 1.0, 0.0), fw));
    vec3 up = cross(fw, rt);
    vec3 rd = normalize(uv.x * rt + uv.y * up + 1.5 * fw);

    float d, trap, tr = 0.0;
    float dist = 0.0;
    bool hit = false;
    vec3 glow = vec3(0.0);

    for (int i = 0; i < 96; i++) {
        vec3 p = ro + rd * dist;
        d = bulbDE(p, power, trap);
        // halo: energy shed near the surface, brighter in the deep folds
        glow += pal(trap * 1.6 + t * 0.03) * (0.0022 * u_p4 / (d + 0.03));
        if (d < 0.0007) { hit = true; tr = trap; break; }
        dist += d * 0.85;
        if (dist > 7.0) break;
    }

    vec3 fogCol = pal(0.6 + t * 0.02) * 0.03;
    vec3 col = fogCol;

    if (hit) {
        vec3 p = ro + rd * dist;
        // normal by central differences on the distance estimator
        vec2 e = vec2(0.0012, 0.0);
        float tt;
        vec3 n = normalize(vec3(
            bulbDE(p + e.xyy, power, tt) - bulbDE(p - e.xyy, power, tt),
            bulbDE(p + e.yxy, power, tt) - bulbDE(p - e.yxy, power, tt),
            bulbDE(p + e.yyx, power, tt) - bulbDE(p - e.yyx, power, tt)));

        vec3 ld = normalize(vec3(0.7, 0.8, -0.5) * rotY(t * 0.1));
        float diff = max(dot(n, ld), 0.0);
        float spec = pow(max(dot(reflect(-ld, n), -rd), 0.0), 30.0);
        float fres = pow(1.0 - max(dot(n, -rd), 0.0), 3.0);
        // crude ambient occlusion from how early the ray converged
        float ao = clamp(1.0 - float(dist) * 0.12, 0.25, 1.0);

        vec3 base = pal(tr * 2.4 + t * 0.02);
        col = base * (0.12 + 0.9 * diff) * ao;
        col += vec3(1.0) * spec * 0.55;
        col += pal(tr * 2.4 + 0.4) * fres * 0.8;
        float fog = exp(-max(dist - 1.5, 0.0) * 0.35);
        col = col * fog + fogCol * (1.0 - fog);
    }

    col += glow;
    fragColor = vec4(tonemap(col * 1.5), 1.0);
}
