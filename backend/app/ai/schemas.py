"""Contrato de saída da IA — provider-agnóstico.

Todo provedor (hoje Claude) deve devolver estas estruturas. Manter o formato aqui
significa que trocar de modelo/provedor não vaza para os serviços nem para a API.

Formato consolidado (`JobAnalysis`):
    {"score": 87, "reasons": [...], "missing_requirements": [...],
     "cover_letter": "...", "screening_answers": [...]}
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import AnswerConfidence

QuestionType = Literal["text", "textarea", "number", "select", "radio", "checkbox", "unknown"]


class JobScore(BaseModel):
    """Aderência entre uma vaga e o perfil do usuário."""

    model_config = ConfigDict(extra="ignore")

    score: int = Field(ge=0, le=100, description="0-100; quanto o perfil atende a vaga.")
    reasons: list[str] = Field(
        default_factory=list, description="Motivos objetivos da nota (pontos fortes)."
    )
    missing_requirements: list[str] = Field(
        default_factory=list, description="Requisitos da vaga que o perfil não cobre."
    )
    recommend_apply: bool = Field(description="Vale a pena candidatar-se?")
    summary: str | None = Field(default=None, description="Uma frase de justificativa.")

    @field_validator("score")
    @classmethod
    def _clamp(cls, value: int) -> int:
        return max(0, min(100, value))


class ScreeningAnswer(BaseModel):
    """Resposta sugerida para uma pergunta de triagem.

    `needs_review` (ou confiança baixa) faz o painel destacar o campo para o
    usuário revisar antes de enviar — nunca chutamos silenciosamente.
    """

    model_config = ConfigDict(extra="ignore")

    question: str
    answer: str
    question_type: QuestionType = "unknown"
    confidence: AnswerConfidence = AnswerConfidence.MEDIUM
    needs_review: bool = False
    reasoning: str | None = None
    # Identificador do campo no formulário, quando conhecido (preenchido pela automação).
    field_id: str | None = None

    # A model validator, not a field validator: field validators are skipped when
    # the field falls back to its default, which is the common case here (the model
    # returns a confidence but no needs_review) and would leave a low-confidence
    # answer unflagged for review.
    @model_validator(mode="after")
    def _low_confidence_needs_review(self) -> ScreeningAnswer:
        if self.confidence == AnswerConfidence.LOW and not self.needs_review:
            self.needs_review = True
        return self


class ScreeningAnswerSet(BaseModel):
    """Wrapper para saída estruturada (a raiz precisa ser um objeto)."""

    model_config = ConfigDict(extra="ignore")

    answers: list[ScreeningAnswer] = Field(default_factory=list)


class CoverLetter(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str
    language: str = Field(default="pt-BR", description="Idioma detectado/usado (ex.: pt-BR, en).")


class JobAnalysis(BaseModel):
    """Resultado consolidado da análise de uma vaga."""

    model_config = ConfigDict(extra="ignore")

    score: int = 0
    reasons: list[str] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    recommend_apply: bool = False
    summary: str | None = None
    cover_letter: str | None = None
    cover_letter_language: str | None = None
    screening_answers: list[ScreeningAnswer] = Field(default_factory=list)
    # A IA pode recusar (stop_reason="refusal"): sinaliza fallback manual.
    refused: bool = False
    refusal_reason: str | None = None


class AIUsage(BaseModel):
    """Tokens/latência de uma chamada, para auditoria e custo."""

    model_config = ConfigDict(extra="ignore")

    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    refused: bool = False
    refusal_category: str | None = None
