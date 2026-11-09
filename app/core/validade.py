from datetime import date


def dias_para_vencer(validade: date, hoje: date) -> int:
    return (validade - hoje).days


def situacao_validade(validade: date, hoje: date) -> str:
    """'vencido' | '30' | '60' | '90' | 'ok' (faixa de alerta de validade)."""
    d = dias_para_vencer(validade, hoje)
    if d < 0:
        return "vencido"
    if d <= 30:
        return "30"
    if d <= 60:
        return "60"
    if d <= 90:
        return "90"
    return "ok"

