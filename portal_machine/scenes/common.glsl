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

// ---------------------------------------------------------------------
// 3D helpers, used by the raymarched scenes
// ---------------------------------------------------------------------

mat3 rotX(float a) {
    float c = cos(a), s = sin(a);
    return mat3(1, 0, 0, 0, c, -s, 0, s, c);
}
mat3 rotY(float a) {
    float c = cos(a), s = sin(a);
    return mat3(c, 0, s, 0, 1, 0, -s, 0, c);
}
mat3 rotZ(float a) {
    float c = cos(a), s = sin(a);
    return mat3(c, -s, 0, s, c, 0, 0, 0, 1);
}

// signed distance functions: negative inside, positive outside
float sdSphere(vec3 p, float r) {
    return length(p) - r;
}
float sdBox(vec3 p, vec3 b) {
    vec3 q = abs(p) - b;
    return length(max(q, 0.0)) + min(max(q.x, max(q.y, q.z)), 0.0);
}
float sdTorus(vec3 p, vec2 t) {
    return length(vec2(length(p.xz) - t.x, p.y)) - t.y;
}
float sdOctahedron(vec3 p, float s) {
    p = abs(p);
    return (p.x + p.y + p.z - s) * 0.57735027;
}
// infinite cross of square tubes — the piece cut out of a Menger sponge
float sdCross(vec3 p, float s) {
    float a = max(abs(p.x), abs(p.y));
    float b = max(abs(p.y), abs(p.z));
    float c = max(abs(p.z), abs(p.x));
    return min(a, min(b, c)) - s;
}

// 3D noise built from the 2D helper, cheap enough for volumetric haze
float noise3(vec3 p) {
    float f = floor(p.z);
    return mix(noise(p.xy + f * 13.7), noise(p.xy + (f + 1.0) * 13.7),
               smoothstep(0.0, 1.0, p.z - f));
}
