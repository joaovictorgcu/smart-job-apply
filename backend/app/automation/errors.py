"""Erros da automação.

A hierarquia distingue o que é recuperável (tenta de novo) do que exige parar
imediatamente — `SecurityCheckpointError` é a mais importante: nunca tentamos
contornar uma verificação de segurança.
"""

from __future__ import annotations


class AutomationError(RuntimeError):
    """Base de todas as falhas de automação."""

    recoverable = False


class BrowserNotReadyError(AutomationError):
    """O navegador não está aberto (ou morreu)."""

    recoverable = True


class NotLoggedInError(AutomationError):
    """Sessão do LinkedIn ausente ou expirada; exige login manual do usuário."""


class SecurityCheckpointError(AutomationError):
    """CAPTCHA / verificação de segurança detectada.

    Sinaliza parada total. Nunca tentar resolver ou burlar.
    """

    def __init__(self, reason: str = "Verificação de segurança detectada.") -> None:
        super().__init__(reason)
        self.reason = reason


class UnexpectedPageError(AutomationError):
    """A página não é a esperada (mudança de UI, redirecionamento, erro)."""

    recoverable = True

    def __init__(self, message: str, *, url: str | None = None) -> None:
        super().__init__(message)
        self.url = url


class ElementNotFoundError(UnexpectedPageError):
    """Seletor não encontrado — provável mudança de interface do LinkedIn."""


class EasyApplyUnavailableError(AutomationError):
    """A vaga não oferece Candidatura Simplificada (ou já foi respondida)."""


class AlreadyAppliedError(AutomationError):
    """O LinkedIn indica que já existe candidatura para esta vaga."""


class ThrottleLimitError(AutomationError):
    """Um guarda-corpo bloqueou a ação (limite diário ou fora do horário)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class StopRequestedError(AutomationError):
    """Kill switch acionado pelo usuário."""


class ManualInputRequiredError(AutomationError):
    """O formulário tem um campo que não podemos preencher com confiança."""

    def __init__(self, message: str, *, questions: list[str] | None = None) -> None:
        super().__init__(message)
        self.questions = questions or []
