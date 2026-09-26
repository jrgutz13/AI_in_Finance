#version 330

uniform vec2  u_resolution;
uniform float u_time;
uniform vec3  u_colA;
uniform vec3  u_colB;
uniform vec3  u_colC;
uniform vec3  u_colD;
uniform float u_speed;
uniform float u_p1;
uniform float u_p2;
uniform float u_p3;
uniform float u_p4;
uniform float u_continuous;   // 1.0 in single-style continuous mode, else 0.0

out vec4 fragColor;

#define TAU 6.28318530718

mat2 rot(float a) {
    float c = cos(a), s = sin(a);
    return mat2(c, -s, s, c);
}

// Cosine color palette (Inigo Quilez style)
vec3 pal(float t) {
    return u_colA + u_colB * cos(TAU * (u_colC * t + u_colD));
}

float hash11(float p) {
    p = fract(p * 443.8975);
    p *= p + 19.19;
    return fract(p * p);
}

float hash21(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 443.897);
    p3 += dot(p3, p3.yzx + 19.19);
    return fract((p3.x + p3.y) * p3.z);
}

float noise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash21(i),               hash21(i + vec2(1, 0)), f.x),
               mix(hash21(i + vec2(0, 1)),  hash21(i + vec2(1, 1)), f.x), f.y);
}

float fbm(vec2 p) {
    float v = 0.0, a = 0.5;
    for (int i = 0; i < 5; i++) {
        v += a * noise(p);
        p = rot(0.5) * p * 2.03;
        a *= 0.5;
    }
    return v;
}

// Soft tone-map so accumulated glow never clips harshly
vec3 tonemap(vec3 c) {
    return 1.0 - exp(-c);
}

// NOTE: never name a helper noise1/noise2/noise3/noise4 — those are built-in
// GLSL function names. Redeclaring one with a different return type compiles
// on some software renderers but fails on real GPU drivers with
// "overloaded functions must have the same return type".
