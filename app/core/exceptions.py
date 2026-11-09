class RegraDeNegocioError(Exception):
    """Violação de regra de negócio (vira HTTP 422/400 com mensagem em pt-BR)."""

    status_code = 422

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


class EstoqueInsuficienteError(RegraDeNegocioError):
    pass


class NaoEncontradoError(RegraDeNegocioError):
    status_code = 404

