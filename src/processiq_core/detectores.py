"""Detectores de inconsistência em títulos a pagar.

Cada detector é uma função pura: recebe a lista de títulos (e a data de hoje,
para ser testável) e devolve alertas. `analisar` roda todos.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from rapidfuzz import fuzz

from .canonico import sugerir_canonico
from .modelo import Alerta, Severidade, TipoAlerta, Titulo
from .normalizacao import raiz_cnpj

# --------------------------------------------------------------------------- #
# Fornecedor duplicado
# --------------------------------------------------------------------------- #

def _sufixo_sugestao(sug) -> str:
    if sug is None:
        return ""
    if not sug.nome:
        return " → nomes sem relação: confira o CNPJ antes de unificar"
    return f" → sugestão: manter '{sug.nome}'"


def detectar_fornecedores_duplicados(titulos: list[Titulo], similaridade_minima: int = 80) -> list[Alerta]:
    """Mesmo fornecedor cadastrado com grafias diferentes.

    Dois critérios, em ordem de confiança:
    1. mesma raiz de CNPJ (8 primeiros dígitos) com nomes normalizados diferentes → ALTA;
    2. sem documento em comum, mas nomes normalizados muito parecidos (WRatio, que
       tolera abreviações como 'Distrib.' ↔ 'Distribuidora') → MEDIA.
    Nomes parecidos com CNPJs de raízes diferentes nunca alertam: são empresas distintas.
    """
    alertas: list[Alerta] = []

    # 1) por raiz de CNPJ
    por_raiz: dict[str, dict[str, list[Titulo]]] = defaultdict(lambda: defaultdict(list))
    for t in titulos:
        r = raiz_cnpj(t.documento)
        if r:
            por_raiz[r][t.fornecedor_normalizado].append(t)
    for raiz, grupos in por_raiz.items():
        if len(grupos) < 2:
            continue
        nomes = sorted(grupos)
        envolvidos = [t for g in grupos.values() for t in g]
        sug = sugerir_canonico(envolvidos)
        alertas.append(Alerta(
            tipo=TipoAlerta.FORNECEDOR_DUPLICADO,
            severidade=Severidade.ALTA,
            mensagem=f"CNPJ raiz {raiz} aparece com {len(nomes)} nomes diferentes: " + " | ".join(nomes)
                     + _sufixo_sugestao(sug),
            titulos=tuple(t.id for t in envolvidos),
            linhas=tuple(t.linha for t in envolvidos),
            detalhes={"raiz_cnpj": raiz, "nomes": nomes, "criterio": "cnpj",
                      "canonico": sug.to_dict() if sug else None},
        ))

    # 2) por similaridade de nome (só entre fornecedores que não compartilham raiz)
    por_nome: dict[str, list[Titulo]] = defaultdict(list)
    for t in titulos:
        if t.fornecedor_normalizado:
            por_nome[t.fornecedor_normalizado].append(t)
    nomes = sorted(por_nome)
    ja_pareados: set[tuple[str, str]] = set()
    for i, a in enumerate(nomes):
        for b in nomes[i + 1:]:
            if (a, b) in ja_pareados:
                continue
            raizes_a = {raiz_cnpj(t.documento) for t in por_nome[a]} - {""}
            raizes_b = {raiz_cnpj(t.documento) for t in por_nome[b]} - {""}
            if raizes_a and raizes_b:
                if raizes_a & raizes_b:
                    continue                     # já coberto pelo critério 1
                else:
                    continue                     # CNPJs diferentes: são empresas diferentes mesmo
            score = int(fuzz.WRatio(a, b))
            if score >= similaridade_minima:
                envolvidos = por_nome[a] + por_nome[b]
                sug = sugerir_canonico(envolvidos)
                alertas.append(Alerta(
                    tipo=TipoAlerta.FORNECEDOR_DUPLICADO,
                    severidade=Severidade.MEDIA,
                    mensagem=f"Nomes muito parecidos ({score}%): '{a}' e '{b}' — confira se é o mesmo fornecedor"
                             + _sufixo_sugestao(sug),
                    titulos=tuple(t.id for t in envolvidos),
                    linhas=tuple(t.linha for t in envolvidos),
                    detalhes={"nomes": [a, b], "similaridade": score, "criterio": "nome",
                              "canonico": sug.to_dict() if sug else None},
                ))
                ja_pareados.add((a, b))
    return alertas


# --------------------------------------------------------------------------- #
# Título duplicado (mesma NF lançada duas vezes)
# --------------------------------------------------------------------------- #

def detectar_titulos_duplicados(titulos: list[Titulo]) -> list[Alerta]:
    """Mesmo fornecedor + mesmo valor + mesmo vencimento (ou mesmo id de NF) em mais de uma linha."""
    alertas: list[Alerta] = []
    chave: dict[tuple, list[Titulo]] = defaultdict(list)
    for t in titulos:
        if t.valor is None or t.vencimento is None:
            continue
        ident = t.fornecedor_normalizado or t.documento
        chave[(ident, t.valor, t.vencimento)].append(t)
    for (ident, valor, venc), grupo in chave.items():
        if len(grupo) < 2:
            continue
        alertas.append(Alerta(
            tipo=TipoAlerta.TITULO_DUPLICADO,
            severidade=Severidade.CRITICA,
            mensagem=(f"{len(grupo)} lançamentos iguais para '{grupo[0].fornecedor}': "
                      f"R$ {valor:,.2f} vencendo em {venc:%d/%m/%Y} (linhas {', '.join(str(t.linha) for t in grupo)})"),
            titulos=tuple(t.id for t in grupo),
            linhas=tuple(t.linha for t in grupo),
            detalhes={"valor": str(valor), "vencimento": venc.isoformat()},
        ))
    return alertas


# --------------------------------------------------------------------------- #
# Vencimentos
# --------------------------------------------------------------------------- #

_STATUS_PAGO = ("PAGO", "PAGA", "LIQUIDADO", "LIQUIDADA", "QUITADO", "BAIXADO")


def _esta_pago(t: Titulo) -> bool:
    return t.status.strip().upper() in _STATUS_PAGO


def detectar_vencidos(titulos: list[Titulo], hoje: date | None = None, dias_aviso: int = 7) -> list[Alerta]:
    """Vencido (data < hoje e não pago) → ALTA; vence em até `dias_aviso` dias → BAIXA."""
    hoje = hoje or date.today()
    limite = hoje + timedelta(days=dias_aviso)
    alertas: list[Alerta] = []
    for t in titulos:
        if t.vencimento is None or _esta_pago(t):
            continue
        if t.vencimento < hoje:
            atraso = (hoje - t.vencimento).days
            alertas.append(Alerta(
                tipo=TipoAlerta.VENCIDO,
                severidade=Severidade.CRITICA if atraso > 30 else Severidade.ALTA,
                mensagem=f"'{t.fornecedor}' venceu há {atraso} dia(s) ({t.vencimento:%d/%m/%Y}) e não consta como pago",
                titulos=(t.id,), linhas=(t.linha,),
                detalhes={"dias_atraso": atraso, "valor": str(t.valor) if t.valor is not None else None},
            ))
        elif t.vencimento <= limite:
            faltam = (t.vencimento - hoje).days
            alertas.append(Alerta(
                tipo=TipoAlerta.VENCE_EM_BREVE,
                severidade=Severidade.BAIXA,
                mensagem=f"'{t.fornecedor}' vence em {faltam} dia(s) ({t.vencimento:%d/%m/%Y})",
                titulos=(t.id,), linhas=(t.linha,),
                detalhes={"dias_para_vencer": faltam, "valor": str(t.valor) if t.valor is not None else None},
            ))
    return alertas


# --------------------------------------------------------------------------- #
# Valor suspeito
# --------------------------------------------------------------------------- #

def detectar_valores_suspeitos(titulos: list[Titulo], fator: Decimal = Decimal("4"), minimo_historico: int = 3) -> list[Alerta]:
    """Valor muito acima da mediana do mesmo fornecedor (precisa de histórico mínimo),
    ou valor zero/negativo."""
    alertas: list[Alerta] = []
    por_forn: dict[str, list[Titulo]] = defaultdict(list)
    for t in titulos:
        if t.valor is None:
            continue
        if t.valor <= 0:
            alertas.append(Alerta(
                tipo=TipoAlerta.VALOR_SUSPEITO, severidade=Severidade.MEDIA,
                mensagem=f"'{t.fornecedor}' com valor {t.valor} (zero ou negativo) na linha {t.linha}",
                titulos=(t.id,), linhas=(t.linha,), detalhes={"valor": str(t.valor), "motivo": "nao_positivo"},
            ))
            continue
        por_forn[t.fornecedor_normalizado or t.documento].append(t)
    for grupo in por_forn.values():
        if len(grupo) < minimo_historico:
            continue
        med = Decimal(str(median(float(t.valor) for t in grupo)))
        if med <= 0:
            continue
        for t in grupo:
            if t.valor > med * fator:
                alertas.append(Alerta(
                    tipo=TipoAlerta.VALOR_SUSPEITO, severidade=Severidade.ALTA,
                    mensagem=(f"'{t.fornecedor}': R$ {t.valor:,.2f} é {float(t.valor / med):.1f}x a mediana "
                              f"do fornecedor (R$ {med:,.2f}) — confira"),
                    titulos=(t.id,), linhas=(t.linha,),
                    detalhes={"valor": str(t.valor), "mediana": str(med.quantize(Decimal('0.01'))), "motivo": "outlier"},
                ))
    return alertas


# --------------------------------------------------------------------------- #
# Campos incompletos / documento inválido
# --------------------------------------------------------------------------- #

def detectar_campos_incompletos(titulos: list[Titulo]) -> list[Alerta]:
    alertas: list[Alerta] = []
    for t in titulos:
        faltando = [c for c, v in (("fornecedor", t.fornecedor), ("valor", t.valor), ("vencimento", t.vencimento)) if v in (None, "")]
        if faltando:
            alertas.append(Alerta(
                tipo=TipoAlerta.CAMPO_INCOMPLETO, severidade=Severidade.MEDIA,
                mensagem=f"Linha {t.linha} sem {', '.join(faltando)}",
                titulos=(t.id,), linhas=(t.linha,), detalhes={"faltando": faltando},
            ))
        if t.documento_bruto and not t.documento:
            alertas.append(Alerta(
                tipo=TipoAlerta.DOCUMENTO_INVALIDO, severidade=Severidade.MEDIA,
                mensagem=f"CNPJ/CPF inválido na linha {t.linha} ('{t.documento_bruto}') para '{t.fornecedor}'",
                titulos=(t.id,), linhas=(t.linha,), detalhes={"documento": t.documento_bruto},
            ))
    return alertas


# --------------------------------------------------------------------------- #
# Orquestração
# --------------------------------------------------------------------------- #

_ORDEM_SEV = {Severidade.CRITICA: 0, Severidade.ALTA: 1, Severidade.MEDIA: 2, Severidade.BAIXA: 3}


def analisar(titulos: list[Titulo], hoje: date | None = None) -> list[Alerta]:
    """Roda todos os detectores e devolve os alertas ordenados por severidade."""
    alertas: list[Alerta] = []
    alertas += detectar_titulos_duplicados(titulos)
    alertas += detectar_fornecedores_duplicados(titulos)
    alertas += detectar_vencidos(titulos, hoje=hoje)
    alertas += detectar_valores_suspeitos(titulos)
    alertas += detectar_campos_incompletos(titulos)
    return sorted(alertas, key=lambda a: (_ORDEM_SEV[a.severidade], a.linhas[0] if a.linhas else 0))


def resumo(titulos: list[Titulo], alertas: list[Alerta], hoje: date | None = None) -> dict:
    """Indicadores para o painel: totais, vencidos, próximos, contagem por tipo/severidade."""
    hoje = hoje or date.today()
    total = sum((t.valor for t in titulos if t.valor is not None), Decimal("0"))
    abertos = [t for t in titulos if not _esta_pago(t) and t.valor is not None]
    vencido = sum((t.valor for t in abertos if t.vencimento and t.vencimento < hoje), Decimal("0"))
    proximo = sum((t.valor for t in abertos if t.vencimento and hoje <= t.vencimento <= hoje + timedelta(days=7)), Decimal("0"))
    por_tipo: dict[str, int] = defaultdict(int)
    por_sev: dict[str, int] = defaultdict(int)
    for a in alertas:
        por_tipo[a.tipo.value] += 1
        por_sev[a.severidade.value] += 1
    # saúde: 100 menos penalidade por severidade, limitado a 0
    pen = por_sev.get("critica", 0) * 15 + por_sev.get("alta", 0) * 7 + por_sev.get("media", 0) * 3 + por_sev.get("baixa", 0) * 1
    return {
        "titulos": len(titulos),
        "valor_total": str(total),
        "valor_vencido": str(vencido),
        "valor_proximos_7_dias": str(proximo),
        "alertas": len(alertas),
        "por_tipo": dict(por_tipo),
        "por_severidade": dict(por_sev),
        "saude_operacional": max(0, 100 - pen),
    }
