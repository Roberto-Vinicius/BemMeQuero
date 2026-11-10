import threading
import time


class LimitadorTentativas:
    """Limita tentativas de login falhas por chave (ex.: IP + e-mail), em memória."""

    def __init__(self, maximo: int = 5, janela_segundos: int = 300):
        self.maximo = maximo
        self.janela = janela_segundos
        self._falhas: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _podar(self, chave: str, agora: float) -> list[float]:
        recentes = [t for t in self._falhas.get(chave, []) if agora - t < self.janela]
        if recentes:
            self._falhas[chave] = recentes
        else:
            self._falhas.pop(chave, None)
        return recentes

    def bloqueado(self, chave: str, agora: float | None = None) -> bool:
        with self._lock:
            return len(self._podar(chave, agora if agora is not None else time.monotonic())) >= self.maximo

    def registrar_falha(self, chave: str, agora: float | None = None) -> None:
        agora = agora if agora is not None else time.monotonic()
        with self._lock:
            self._podar(chave, agora)
            self._falhas.setdefault(chave, []).append(agora)

    def limpar(self, chave: str) -> None:
        with self._lock:
            self._falhas.pop(chave, None)


from app.core.config import get_settings as _get_settings

_s = _get_settings()
limitador_login = LimitadorTentativas(maximo=_s.login_max_tentativas, janela_segundos=_s.login_janela_segundos)


