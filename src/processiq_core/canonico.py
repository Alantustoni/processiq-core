"""Sugestão de fornecedor canônico ao unificar cadastros duplicados.

Quando o detector acha o mesmo fornecedor com grafias diferentes, a pergunta seguinte
de quem vai limpar o cadastro é: *qual nome eu mantenho?* Este módulo responde com uma
regra explicável, e não com um palpite:

1. **nome por extenso** vence abreviado ('Distribuidora' > 'Distrib.');
2. depois, a grafia **mais usada** nos títulos (é a que o financeiro já reconhece);
3. depois, **razão social completa**, com LTDA / S/A / ME / EIRELI;
4. depois, o nome com **mais palavras** (mais informativo);
5. por último, a grafia que **aparece primeiro** na planilha.

O CNPJ sugerido é o da **matriz** (0001) quando ela aparece; senão, o mais frequente.

Nomes sem relação entre si no mesmo CNPJ ('Transportes X' e 'Serviços Y') não viram
sugestão: o mais provável é CNPJ digitado errado, e unificar apagaria um fornecedor.
Esses casos saem em `conferir`, para uma pessoa olhar.

Tudo aqui é função pura sobre `Titulo`; nada é alterado na planilha de origem.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, replace

from rapidfuzz import fuzz

from .modelo import Alerta, TipoAlerta, Titulo
from .normalizacao import _sem_acentos, normalizar_documento, normalizar_nome

# abreviações comuns em razão social de fornecedor (já sem acento e em maiúsculas)
ABREVIACOES = frozenset({
    "DISTRIB", "DIST", "COM", "COML", "IND", "INDL", "SERV", "SERVS", "TRANSP", "MERC",
    "EQUIP", "EQUIPS", "ADM", "ADMIN", "ASSOC", "CONST", "CONSTR", "PROD", "PRODS", "MAT",
    "MATS", "MANUT", "TEC", "TECN", "ENG", "REPRES", "IMP", "EXP", "INST", "LOC", "SIST",
    "SOL", "MEC", "MET", "ELET", "AUT", "AGRIC", "ALIM", "EMP", "EMPR", "PART", "NAC", "INTL",
})
_SUFIXO_SOCIETARIO = re.compile(r"\b(LTDA|LIMITADA|S[./ ]?A|ME|EPP|EIRELI)\.?\s*$", re.IGNORECASE)
SIMILARIDADE_MINIMA = 80


@dataclass(frozen=True)
class Variante:
    """Uma grafia do fornecedor como aparece na planilha."""

    nome: str                    # exatamente como veio (sem espaços nas pontas)
    ocorrencias: int
    titulos: tuple[str, ...]
    linhas: tuple[int, ...]


@dataclass(frozen=True)
class Sugestao:
    nome: str                    # grafia a manter
    documento: str               # CNPJ/CPF sugerido, só dígitos ('' se nenhum válido)
    motivo: str                  # por que esta grafia venceu, em uma frase
    variantes: tuple[Variante, ...]      # todas as grafias que viram o nome sugerido (inclui a mantida)
    conferir: tuple[Variante, ...] = ()  # grafias sem relação com a sugerida: não unificar sem olhar

    def to_dict(self) -> dict:
        v = lambda x: {"nome": x.nome, "ocorrencias": x.ocorrencias,
                       "titulos": list(x.titulos), "linhas": list(x.linhas)}
        return {"nome": self.nome, "documento": self.documento, "motivo": self.motivo,
                "variantes": [v(x) for x in self.variantes], "conferir": [v(x) for x in self.conferir]}


# --------------------------------------------------------------------------- #
# critérios
# --------------------------------------------------------------------------- #

def _tokens_brutos(nome: str) -> list[str]:
    return re.findall(r"[A-Z0-9]+\.?", _sem_acentos(nome).upper())


def abreviacoes(nome: str) -> int:
    """Quantas palavras do nome parecem abreviadas ('Distrib.', 'Com', 'Ind.')."""
    n = 0
    for tok in _tokens_brutos(nome):
        base = tok.rstrip(".")
        if base in {"LTDA", "S", "A", "SA", "ME", "EPP", "EIRELI", "CIA"}:
            continue
        if base in ABREVIACOES or (tok.endswith(".") and len(base) <= 6):
            n += 1
    return n


def razao_completa(nome: str) -> bool:
    return bool(_SUFIXO_SOCIETARIO.search(nome.strip()))


def nomes_compativeis(a: str, b: str, similaridade_minima: int = SIMILARIDADE_MINIMA) -> bool:
    """Duas grafias podem ser o mesmo fornecedor?

    Sim se forem muito parecidas (WRatio), ou se cada palavra do nome mais curto
    casar, em ordem, com uma palavra do outro sendo uma prefixo da outra:
    'MERC CENTRAL' ↔ 'MERCADO CENTRAL ALIMENTOS'. Palavras de 1–2 letras não contam,
    e um nome de uma palavra só precisa ser idêntico ao outro.
    """
    na, nb = normalizar_nome(a), normalizar_nome(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    ta, tb = [t for t in na.split() if len(t) >= 3], [t for t in nb.split() if len(t) >= 3]
    curto, longo = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(curto) < 2:
        return False                      # uma palavra só ('CENTRAL') casa com qualquer coisa
    if fuzz.WRatio(na, nb) >= similaridade_minima:
        return True
    i = 0
    for tok in curto:
        while i < len(longo) and not (longo[i].startswith(tok) or tok.startswith(longo[i])):
            i += 1
        if i == len(longo):
            return False
        i += 1
    return True


def _variantes(titulos: list[Titulo]) -> list[Variante]:
    por_nome: dict[str, list[Titulo]] = {}
    for t in titulos:
        nome = " ".join(t.fornecedor.split())
        if nome:
            por_nome.setdefault(nome, []).append(t)
    return [Variante(nome=n, ocorrencias=len(ts), titulos=tuple(t.id for t in ts),
                     linhas=tuple(t.linha for t in ts)) for n, ts in por_nome.items()]


def _documento(titulos: list[Titulo]) -> str:
    docs = Counter(d for d in (normalizar_documento(t.documento) for t in titulos) if d)
    if not docs:
        return ""
    matriz = [d for d in docs if len(d) == 14 and d[8:12] == "0001"]
    candidatos = matriz or list(docs)
    return max(candidatos, key=lambda d: (docs[d], -candidatos.index(d)))


def _chave(grupo: list[Variante]) -> tuple:
    """Ordem de preferência entre grupos de grafias que normalizam igual (maior vence)."""
    rep = grupo[0].nome
    return (
        -abreviacoes(rep),
        sum(v.ocorrencias for v in grupo),
        any(razao_completa(v.nome) for v in grupo),
        len(normalizar_nome(rep).split()),
        -min(min(v.linhas) for v in grupo),
    )


def _motivo(vencedor: list[Variante], segundo: list[Variante] | None) -> str:
    if segundo is None:
        return "mesmo nome com grafias diferentes; mantida a mais usada (com tipo societário e acento, no empate)"
    a, b = _chave(vencedor), _chave(segundo)
    oc = sum(v.ocorrencias for v in vencedor)
    if a[0] != b[0]:
        return f"nome por extenso, sem abreviação (a outra grafia abrevia: '{segundo[0].nome}')"
    if a[1] != b[1]:
        return f"grafia mais usada: {oc} de {oc + sum(v.ocorrencias for v in segundo)} títulos"
    if a[2] != b[2]:
        return "razão social completa, com o tipo societário"
    if a[3] != b[3]:
        return "nome mais completo (mais palavras)"
    return "empate nos critérios; mantida a grafia que aparece primeiro na planilha"


# --------------------------------------------------------------------------- #
# API do módulo
# --------------------------------------------------------------------------- #

def sugerir_canonico(titulos: list[Titulo]) -> Sugestao | None:
    """Escolhe a grafia a manter entre títulos de um mesmo fornecedor suspeito.

    Devolve None se não houver nenhuma grafia compatível com outra (todas sem relação).
    """
    variantes = _variantes(titulos)
    if not variantes:
        return None
    grupos: dict[str, list[Variante]] = {}
    for v in variantes:
        grupos.setdefault(normalizar_nome(v.nome), []).append(v)
    ordem = sorted(grupos.values(), key=_chave, reverse=True)

    for vencedor in ordem:
        compativeis = [g for g in ordem if g is not vencedor and nomes_compativeis(vencedor[0].nome, g[0].nome)]
        if compativeis or len(ordem) == 1:
            break
    else:
        return Sugestao(nome="", documento="", variantes=(), conferir=tuple(variantes),
                        motivo="nomes sem relação entre si — provável CNPJ digitado errado; "
                               "confira o cadastro antes de unificar")

    unidos = [vencedor] + compativeis
    conferir = tuple(v for g in ordem if not any(g is u for u in unidos) for v in g)
    # dentro das grafias que normalizam igual: a mais usada; depois a com tipo societário;
    # depois a que tem acento/minúsculas (veio digitada com cuidado); depois a primeira
    grafia = max(vencedor, key=lambda v: (v.ocorrencias, razao_completa(v.nome),
                                          v.nome != v.nome.upper() or v.nome != _sem_acentos(v.nome),
                                          -min(v.linhas)))
    nomes_unidos = {v.nome for g in unidos for v in g}
    titulos_unidos = [t for t in titulos if " ".join(t.fornecedor.split()) in nomes_unidos]
    segundo = next(iter(compativeis), None)
    return Sugestao(
        nome=grafia.nome,
        documento=_documento(titulos_unidos),
        motivo=_motivo(vencedor, segundo),
        variantes=tuple(v for g in unidos for v in g),
        conferir=conferir,
    )


def de_para(alertas: list[Alerta]) -> list[dict]:
    """Tabela de unificação a partir dos alertas de fornecedor duplicado.

    Uma linha por grafia a trocar: de → para, com CNPJ sugerido, linhas da planilha e o motivo.
    Grafias marcadas para conferir saem com `para` vazio e `acao='conferir'`.
    """
    linhas: list[dict] = []
    vistos: set[tuple[str, str]] = set()
    for a in alertas:
        if a.tipo != TipoAlerta.FORNECEDOR_DUPLICADO or not a.detalhes.get("canonico"):
            continue
        c = a.detalhes["canonico"]
        for v in c["variantes"]:
            if v["nome"] == c["nome"] or (v["nome"], c["nome"]) in vistos:
                continue
            vistos.add((v["nome"], c["nome"]))
            mesma = normalizar_nome(v["nome"]) == normalizar_nome(c["nome"])
            linhas.append({"de": v["nome"], "para": c["nome"], "documento": c["documento"],
                           "acao": "padronizar grafia" if mesma else "unificar",
                           "ocorrencias": v["ocorrencias"], "linhas": v["linhas"],
                           "criterio": a.detalhes.get("criterio", ""),
                           "motivo": "mesmo nome, só muda a grafia (maiúsculas, acento ou pontuação)"
                                     if mesma else c["motivo"]})
        for v in c["conferir"]:
            if (v["nome"], "") in vistos:
                continue
            vistos.add((v["nome"], ""))
            linhas.append({"de": v["nome"], "para": "", "documento": "", "acao": "conferir",
                           "ocorrencias": v["ocorrencias"], "linhas": v["linhas"],
                           "criterio": a.detalhes.get("criterio", ""), "motivo": c["motivo"]})
    return linhas


def aplicar_unificacao(titulos: list[Titulo], tabela: list[dict]) -> list[Titulo]:
    """Devolve novos títulos com o fornecedor trocado conforme a tabela de `de_para`.

    Só troca o nome e só nas linhas listadas; casos 'conferir' ficam como estão.
    Útil para reanalisar depois da limpeza: NFs duplicadas escondidas atrás de grafias
    diferentes passam a aparecer.
    """
    troca: dict[int, str] = {}
    for row in tabela:
        if row["acao"] == "conferir" or not row["para"]:
            continue
        for ln in row["linhas"]:
            troca[ln] = row["para"]
    return [replace(t, fornecedor=troca[t.linha]) if t.linha in troca else t for t in titulos]
