"""Deterministic backend policy gates independent of agent output."""

import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, model_validator

CATEGORIES = {
    "password_reset": "inquiry",
    "unknown": "inquiry",
    "network_wifi": "network",
    "app_access": "software",
    "critical_incident": "software",
    "applications_issues": "software",
    "printer_label": "hardware",
}


def priority(category: str, impact: int, urgency: int) -> str:
    if category == "critical_incident" or (impact == 1 and urgency == 1):
        return "P1"
    if impact == 1 or urgency == 1:
        return "P2"
    if impact == 2 or urgency == 2:
        return "P3"
    return "P4"


class TriageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    internal_category: str
    servicenow_category: str
    impact: int = Field(ge=1, le=3)
    urgency: int = Field(ge=1, le=3)
    resulting_priority: str
    confidence: float = Field(ge=0, le=1)
    risk_flags: list[str] = Field(default_factory=list)
    missing_required_fields: list[str] = Field(default_factory=list)
    initial_action: str

    @model_validator(mode="after")
    def check_mapping(self) -> "TriageResult":
        if self.internal_category not in CATEGORIES:
            raise ValueError("Unknown category")
        if self.servicenow_category != CATEGORIES[self.internal_category]:
            raise ValueError("Category mapping mismatch")
        if self.resulting_priority != priority(
            self.internal_category, self.impact, self.urgency
        ):
            raise ValueError("Priority mismatch")
        if self.initial_action not in (
            "respond",
            "ask_clarification",
            "open_ticket",
            "blocked",
        ):
            raise ValueError("Unknown action")
        return self


_SECRET = re.compile(
    r"(?i)\b(?:password|senha|access[_ -]?token|token|api[_ -]?key|"
    r"client[_ -]?secret|secret)\b\"?\s*[:=]\s*"
    r"(?:\"[^\"\n]*\"|'[^'\n]*'|[^\s,;]+)"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+={0,2}")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")


def redact(text: str) -> str:
    text = _SECRET.sub("[REDACTED]", text)
    text = _BEARER.sub("[REDACTED]", text)
    text = _EMAIL.sub("[REDACTED]", text)
    return _CPF.sub("[REDACTED]", text)


def requests_third_party_secret(text: str) -> bool:
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKD", text.casefold())
        if not unicodedata.combining(character)
    )
    for sentence in re.split(r"[.!?\n]+", normalized):
        if (
            re.search(
                r"\b(?:envie|enviar|manda|mande|mandar|mostre|mostrar|revele|"
                r"revelar|diga|informe|informar|forneca|fornecer|passe|passar|"
                r"compartilhe|compartilhar|qual (?:e|seria))\b",
                sentence,
            )
            and re.search(
                r"\b(?:senha|password|token|credencia(?:l|is)|dados pessoais|"
                r"informacoes pessoais|cpf|rg|documento|endereco|telefone|"
                r"e-?mail)\b",
                sentence,
            )
            and re.search(
                r"\b(?:colega|outr[oa] (?:pessoa|colaborador[ao]?|funcionari[oa])|"
                r"terceir[oa]|dele|dela)\b",
                sentence,
            )
        ):
            return True
    return False


def requests_ticket(text: str) -> bool:
    normalized = text.casefold()
    latest = normalized.rsplit("resposta do usuario:", 1)[-1]
    if re.search(
        r"\b(?:nao|não)\s+(?:quero|preciso|gostaria|abra|abre|abrir)\b"
        r"[^.!?\n]{0,30}\b(?:ticket|chamado|incidente)\b",
        latest,
    ):
        return False
    return bool(
        re.search(
            r"\b(?:quero|gostaria de|preciso de|pode|poderia|por favor)\b"
            r"[^.!?\n]{0,100}\b(?:abrir|criar|registrar)\b"
            r"[^.!?\n]{0,30}\b(?:ticket|chamado|incidente)\b",
            normalized,
        )
        or re.search(
            r"\b(?:quero|gostaria de|preciso de|pode|poderia|por favor)\b"
            r"[^.!?\n]{0,30}\b(?:ticket|chamado|incidente)\b",
            normalized,
        )
        or re.search(
            r"\b(?:solicito|peço|peco)\b[^.!?\n]{0,30}"
            r"\b(?:ticket|chamado|incidente)\b",
            normalized,
        )
        or re.search(
            r"\b(?:abra|abre)\b[^.!?\n]{0,30}"
            r"\b(?:ticket|chamado|incidente)\b",
            normalized,
        )
    )
