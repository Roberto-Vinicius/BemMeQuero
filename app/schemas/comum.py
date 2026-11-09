from typing import Any

from pydantic import ValidationError

_MENSAGENS = {
    "missing": "Campo obrigatório.",
    "string_type": "Campo obrigatório.",
    "int_type": "Campo obrigatório.",
    "decimal_type": "Campo obrigatório.",
    "string_too_short": "Texto muito curto.",
    "string_too_long": "Texto muito longo.",
    "greater_than_equal": "O valor não pode ser negativo.",
    "int_parsing": "Informe um número inteiro.",
    "decimal_parsing": "Informe um valor numérico válido (ex.: 59,90).",
    "decimal_max_places": "Use no máximo 2 casas decimais.",
    "decimal_max_digits": "Valor muito grande.",
    "greater_than": "O valor deve ser maior que zero.",
    "date_parsing": "Informe uma data válida.",
    "date_from_datetime_parsing": "Informe uma data válida.",
    "date_type": "Campo obrigatório.",
    "literal_error": "Opção inválida.",
    "value_error": "Valor inválido.",
}


def normalizar_form(dados: dict[str, Any], campos_decimais: set[str] = frozenset()) -> dict[str, Any]:
    """Vazio vira None; decimais aceitam vírgula (1.299,90 -> 1299.90)."""
    saida: dict[str, Any] = {}
    for k, v in dados.items():
        if isinstance(v, str):
            v = v.strip() or None
            if v is not None and k in campos_decimais:
                if "," in v:
                    v = v.replace(".", "").replace(",", ".")
        saida[k] = v
    return saida


def erros_pydantic(exc: ValidationError) -> dict[str, str]:
    erros: dict[str, str] = {}
    for e in exc.errors():
        campo = str(e["loc"][0]) if e["loc"] else "_geral"
        if e["type"] == "value_error":
            msg = str(e.get("msg", "")).removeprefix("Value error, ")
        else:
            msg = _MENSAGENS.get(e["type"], "Valor inválido.")
        erros.setdefault(campo, msg)
    return erros
