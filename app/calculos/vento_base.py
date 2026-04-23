import math


def calcular_s1_terreno_plano() -> float:
    return 1.0


def calcular_s1_vale_profundo() -> float:
    return 0.9


def calcular_s1_talude_morro(z: float, theta_t: float, d_t: float) -> float:
    if d_t == 0:
        raise ValueError("d_t nao pode ser zero.")
    if theta_t <= 3:
        return 1.0
    if 6 <= theta_t <= 17:
        return max(1.0, 1.0 + (2.5 - z / d_t) * math.tan(math.radians(theta_t - 3)))
    if theta_t >= 45:
        return max(1.0, 1.0 + (2.5 - z / d_t) * 0.31)
    if 3 < theta_t < 6:
        s3 = 1.0
        s6 = max(1.0, 1.0 + (2.5 - z / d_t) * math.tan(math.radians(6 - 3)))
        return s3 + ((theta_t - 3) / (6 - 3)) * (s6 - s3)

    s17 = max(1.0, 1.0 + (2.5 - z / d_t) * math.tan(math.radians(17 - 3)))
    s45 = max(1.0, 1.0 + (2.5 - z / d_t) * 0.31)
    return s17 + ((theta_t - 17) / (45 - 17)) * (s45 - s17)


def calcular_vk(v0: float, s1: float, s2: float, s3: float) -> float:
    return v0 * s1 * s2 * s3
