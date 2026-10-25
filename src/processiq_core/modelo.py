"""Estruturas de dados do motor: um título a pagar e um alerta gerado sobre ele."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum


class Severidade(str, Enum):
    BAIXA = "baixa"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "critica"


class TipoAlerta(str, Enum):
    FORNECEDOR_DUPLICADO = "fornecedor_duplicado"
    TITULO_DUPLICADO = "titulo_duplicado"
    VENCIDO = "vencido"
    VENCE_EM_BREVE = "vence_em_breve"
    VALOR_SUSPEITO = "valor_suspeito"
    CAMPO_INCOMPLETO = "campo_incompleto"
    DOCUMENTO_INVALIDO = "documento_invalido"


@dataclass(frozen=True)
class Titulo:
    """Uma linha da planilha de contas a pagar, já normalizada."""

    id: str                      # identificador da linha (nº da NF, id interno ou 'L<linha>')
    fornecedor: str              # razão social como veio na planilha
    documento: str               # CNPJ/CPF só dígitos ('' se ausente ou inválido)
    valor: Decimal | None
    vencimento: date | None
    linha: int                   # linha de origem na planilha (1-based), para o usuário achar
    categoria: str = ""
    status: str = ""
    documento_bruto: str = ""    # como veio, para mostrar no alerta de inválido

    @property
    def fornecedor_normalizado(self) -> str:
        from .normalizacao import normalizar_nome
        return normalizar_nome(self.fornecedor)


@dataclass(frozen=True)
class Alerta:
    tipo: TipoAlerta
    severidade: Severidade
    mensagem: str
    titulos: tuple[str, ...]     # ids dos títulos envolvidos
    linhas: tuple[int, ...]      # linhas da planilha envolvidas
    detalhes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tipo": self.tipo.value,
            "severidade": self.severidade.value,
            "mensagem": self.mensagem,
            "titulos": list(self.titulos),
            "linhas": list(self.linhas),
            "detalhes": self.detalhes,
        }
