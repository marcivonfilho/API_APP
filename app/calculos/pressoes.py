def calcular_q(vk: float) -> float:
    return 0.613 * vk ** 2


def calcular_delta_p(cpe: float, cpi: float, q: float) -> float:
    return (cpe - cpi) * q


def calcular_pressao_externa(cpe: float, q: float) -> float:
    return cpe * q


def calcular_pressao_interna(cpi: float, q: float) -> float:
    return cpi * q
