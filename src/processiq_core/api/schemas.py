"""Contratos da API (Pydantic). O motor em `processiq_core` não conhece estes modelos:
a API converte os dataclasses do motor para cá na borda, e só aqui.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..modelo import Alerta, Severidade, TipoAlerta, Titulo


class ColunasReconhecidas(BaseModel):
    """Índice (0-based) da coluna reconhecida para cada campo lógico."""

    id: int | None = None
    fornecedor: int | None = None
    documento: int | None = None
    valor: int | None = None
    vencimento: int | None = None
    categoria: int | None = None
    status: int | None = None


class AlertaOut(BaseModel):
    tipo: TipoAlerta
    severidade: Severidade
    mensagem: str
    titulos: list[str] = Field(description="ids dos títulos envolvidos")
    linhas: list[int] = Field(description="linhas da planilha (1-based), para o usuário localizar")
    detalhes: dict = Field(default_factory=dict)

    @classmethod
    def de_alerta(cls, a: Alerta) -> "AlertaOut":
        return cls(**a.to_dict())


class TituloOut(BaseModel):
    id: str
    fornecedor: str
    documento: str
    valor: str | None
    vencimento: str | None
    linha: int
    categoria: str = ""
    status: str = ""

    @classmethod
    def de_titulo(cls, t: Titulo) -> "TituloOut":
        return cls(
            id=t.id, fornecedor=t.fornecedor, documento=t.documento,
            valor=str(t.valor) if t.valor is not None else None,
            vencimento=t.vencimento.isoformat() if t.vencimento else None,
            linha=t.linha, categoria=t.categoria, status=t.status,
        )


class Resumo(BaseModel):
    titulos: int
    valor_total: str
    valor_vencido: str
    valor_proximos_7_dias: str
    alertas: int
    por_tipo: dict[str, int]
    por_severidade: dict[str, int]
    saude_operacional: int = Field(ge=0, le=100)


class AnaliseOut(BaseModel):
    arquivo: str
    hoje: str = Field(description="data de referência usada para vencidos/próximos (ISO)")
    colunas: ColunasReconhecidas
    resumo: Resumo
    alertas: list[AlertaOut]
    titulos: list[TituloOut] | None = Field(
        default=None, description="presente só quando ?incluir_titulos=true"
    )


class Erro(BaseModel):
    erro: str
