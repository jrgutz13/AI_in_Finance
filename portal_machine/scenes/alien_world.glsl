// POV flight over a surreal alien landscape. Raymarched procedural terrain
// with a low sun, atmospheric haze, drifting cloud layer and a sky that
// scatters light the way a real atmosphere does — so the imagery reads as
// photographic even though the world is invented.
// The terrain is built from PERIODIC noise and the world offset wraps at
// WORLD_PER, so the flight is endless and never breaks.
// u_p1: terrain roughness   u_p2: hill height
// u_p3: fly speed           u_p4: alien color shift

#define LATTICE   32.0                  // world units per noise cell
#define NOISE_PER 64.0                  // noise repeats every 64 cells
#define WORLD_PER (LATTICE * NOISE_PER) // ... so the world repeats every 2048

// --- terrain ---------------------------------------------------------
// Large-scale relief: swells the hills in some regions and flattens them to
// plains in others, so the world has provinces instead of uniform spikes.
// Sampled at 1/4 the base frequency with 1/4 the period, which keeps the
// same 2048-unit world repeat.
float reliefAt(vec2 q) {
    return 0.18 + 1.45 * pnoise(q / (LATTICE * 4.0), NOISE_PER * 0.25);
}

// low detail: cheap, used while marching. high detail: only at the hit.
// Both must agree on the large-scale shape or the normals won't match the
// surface the ray actually hit.
float terrainLow(vec2 q, float rough, float height) {
    float h = pfbm(q / LATTICE, NOISE_PER, 4);
    h = pow(max(h, 0.0), 1.0 + rough);       // sharpen the valleys
    return h * height * reliefAt(q);
}

float terrainHigh(vec2 q, float rough, float height) {
    float h = pfbm(q / LATTICE, NOISE_PER, 7);
    h = pow(max(h, 0.0), 1.0 + rough);
    return h * height * reliefAt(q);
}

// --- sky -------------------------------------------------------------
vec3 skyColor(vec3 rd, vec3 sunDir, float shift, float t) {
    float up = clamp(rd.y, 0.0, 1.0);
    // horizon-to-zenith gradient: the core of why a sky looks real
    vec3 zenith  = pal(0.15 + shift) * 0.55;
    vec3 horizon = pal(0.55 + shift) * 0.95;
    vec3 col = mix(horizon, zenith, pow(up, 0.55));

    // sun disc plus the wide forward-scattered glow around it
    float sd = max(dot(rd, sunDir), 0.0);
    col += pal(0.05 + shift) * pow(sd, 220.0) * 9.0;        // disc
    col += pal(0.12 + shift) * pow(sd, 5.0) * 0.55;         // glow
    col += pal(0.30 + shift) * pow(sd, 1.6) * 0.16;         // wide haze

    // a high cloud deck, projected onto the sky dome and drifting
    if (rd.y > 0.005) {
        vec2 cp = rd.xz / rd.y * 0.25 + vec2(t * 0.01, 0.0);
        float c = pfbm(cp * 1.2, NOISE_PER, 5);
        c = smoothstep(0.45, 0.85, c) * smoothstep(0.0, 0.25, rd.y);
        // clouds lit from the sun side
        vec3 cc = mix(pal(0.62 + shift) * 0.8, pal(0.08 + shift) * 1.5,
                      pow(sd, 2.0));
        col = mix(col, cc, c * 0.75);
    }
    return col;
}

void main() {
    vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution) / u_resolution.y;
    float t = u_time * u_speed;

    float rough  = u_p1;
    float height = u_p2;
    float shift  = u_p4;

    // bounded world offset: endless flight, no precision drift
    float zoff = mod(t * u_p3 * 9.0, WORLD_PER);

    // Camera rides above the terrain. It also checks the ground AHEAD, or it
    // would fly straight into the face of the next ridge.
    vec2 camXZ = vec2(14.0 * sin(t * 0.05), zoff);
    float g = terrainLow(camXZ, rough, height);
    g = max(g, terrainLow(camXZ + vec2(0.0,  70.0), rough, height));
    g = max(g, terrainLow(camXZ + vec2(0.0, 140.0), rough, height));
    vec3 ro = vec3(camXZ.x, g + 0.42 * height + 20.0 + 4.0 * sin(t * 0.21), 0.0);

    // look ahead, banking gently
    float yaw = 0.12 * sin(t * 0.037);
    vec3 fw = normalize(vec3(sin(yaw), -0.105 + 0.03 * sin(t * 0.09), cos(yaw)));
    vec3 rt = normalize(cross(vec3(0.0, 1.0, 0.0), fw));
    vec3 up = cross(fw, rt);
    vec3 rd = normalize(uv.x * rt + uv.y * up + 1.35 * fw);
    rd = normalize(rd + rt * 0.02 * sin(t * 0.13));        // slow roll drift

    vec3 sunDir = normalize(vec3(0.45, 0.16, 0.88));

    // --- march the terrain ------------------------------------------
    float dist = 0.0;
    bool hit = false;
    const float MAXD = 900.0;
    for (int i = 0; i < 150; i++) {
        vec3 p = ro + rd * dist;
        // sample in world space: p.z is relative to the camera, so add zoff
        float h = terrainLow(vec2(p.x, p.z + zoff), rough, height);
        float dy = p.y - h;
        if (dy < 0.0015 * dist) { hit = true; break; }
        // step proportional to both the height gap and the distance: fine
        // detail close up, coarse far away
        dist += max(0.42 * dy, 0.004 * dist + 0.05);
        if (dist > MAXD) break;
    }

    vec3 col;
    vec3 sky = skyColor(rd, sunDir, shift, t);

    if (hit) {
        vec3 p = ro + rd * dist;
        vec2 wq = vec2(p.x, p.z + zoff);

        // normal from the detailed height field
        float e = max(0.35, dist * 0.0016);
        float h0 = terrainHigh(wq, rough, height);
        float hx = terrainHigh(wq + vec2(e, 0.0), rough, height);
        float hz = terrainHigh(wq + vec2(0.0, e), rough, height);
        vec3 n = normalize(vec3(h0 - hx, e, h0 - hz));

        float slope = clamp(n.y, 0.0, 1.0);
        float band  = clamp(h0 / max(height, 0.001), 0.0, 1.0);

        // surface: alien mineral colors, banded by altitude, with rock
        // showing through on the steep faces
        // vivid mineral colors — this is an alien world, so the ground is
        // allowed to be saturated in a way Earth rock never is
        vec3 lowland = pal(0.72 + shift) * 1.5;
        vec3 upland  = pal(0.40 + shift) * 1.5;
        vec3 crest   = pal(0.02 + shift) * 1.7;
        vec3 albedo = mix(lowland, upland, smoothstep(0.15, 0.55, band));
        albedo = mix(albedo, crest, smoothstep(0.62, 0.95, band));
        vec3 rock = pal(0.50 + shift) * 0.85;
        albedo = mix(rock, albedo, smoothstep(0.35, 0.8, slope));

        // fine mineral speckle, only near the camera where it would be seen
        float grain = pnoise(wq * 2.2, NOISE_PER * 64.0);
        albedo *= 0.82 + 0.36 * grain * exp(-dist * 0.012);

        // --- lighting -----------------------------------------------
        float sun = max(dot(n, sunDir), 0.0);
        // soft shadow: march toward the sun and see if a ridge blocks it
        float sh = 1.0;
        float sd2 = 6.0;
        for (int j = 0; j < 18; j++) {
            vec3 sp = p + sunDir * sd2;
            float sh_h = terrainLow(vec2(sp.x, sp.z + zoff), rough, height);
            sh = min(sh, clamp(12.0 * (sp.y - sh_h) / sd2, 0.0, 1.0));
            sd2 += 7.0;
            if (sh < 0.02 || sd2 > 160.0) break;
        }

        vec3 sunCol = pal(0.06 + shift) * 4.6;
        vec3 skyAmb = pal(0.58 + shift) * 0.85;
        float bounce = clamp(0.35 - 0.35 * n.y, 0.0, 1.0);   // light off the ground

        col  = albedo * sunCol * sun * sh;
        col += albedo * skyAmb * (0.35 + 0.65 * slope);
        col += albedo * pal(0.68 + shift) * bounce * 0.30;

        // bioluminescent glow pooling in the low ground — reads as alien
        float pools = smoothstep(0.22, 0.02, band) * smoothstep(0.5, 0.9, slope);
        col += pal(0.85 + shift) * pools * 0.55;

        // wet/glassy sheen on the flatter ground
        vec3 h2 = normalize(sunDir - rd);
        float spec = pow(max(dot(n, h2), 0.0), 42.0) * smoothstep(0.55, 0.95, slope);
        col += sunCol * spec * 0.35 * sh;

        // --- atmosphere ---------------------------------------------
        // exponential haze toward the sky color, plus extra glow when
        // looking into the sun. This is what sells distance as real.
        float fog = 1.0 - exp(-dist * 0.0032);
        vec3 fogCol = mix(sky, pal(0.10 + shift) * 1.5,
                          pow(max(dot(rd, sunDir), 0.0), 6.0) * 0.5);
        col = mix(col, fogCol, fog);
    } else {
        col = sky;
    }

    // filmic-ish response: gentle shoulder, slight contrast, no hard clip
    col = tonemap(col * 1.05);
    col = pow(col, vec3(0.92));
    col *= 1.0 - 0.22 * dot(uv, uv);          // lens vignette

    fragColor = vec4(col, 1.0);
}
