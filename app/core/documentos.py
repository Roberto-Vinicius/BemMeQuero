import re


def somente_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def _digito(base: str, pesos: list[int]) -> str:
    soma = sum(int(d) * p for d, p in zip(base, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def cpf_valido(valor: str) -> bool:
    d = somente_digitos(valor)
    if len(d) != 11 or d == d[0] * 11:
        return False
    d1 = _digito(d[:9], list(range(10, 1, -1)))
    d2 = _digito(d[:9] + d1, list(range(11, 1, -1)))
    return d[9:] == d1 + d2


def cnpj_valido(valor: str) -> bool:
    d = somente_digitos(valor)
    if len(d) != 14 or d == d[0] * 14:
        return False
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = _digito(d[:12], p1)
    d2 = _digito(d[:12] + d1, [6] + p1)
    return d[12:] == d1 + d2


def completar_cnpj(base12: str) -> str:
    """Acrescenta os dígitos verificadores a 12 dígitos (usado no seed)."""
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = _digito(base12, p1)
    d2 = _digito(base12 + d1, [6] + p1)
    return base12 + d1 + d2


def formatar_documento(valor: str | None) -> str:
    d = somente_digitos(valor or "")
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return valor or ""

