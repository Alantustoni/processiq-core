"""Normalização de campos de contas a pagar: CNPJ/CPF, razão social, valores e datas.

Tudo aqui é determinístico e sem dependência externa, para ser fácil de testar
e de reaproveitar em outros projetos (CNAB, conciliação etc.).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# Sufixos societários que não distinguem um fornecedor do outro.
_SUFIXOS = (
    "LTDA", "LIMITADA", "ME", "EPP", "EIRELI", "SA", "S/A", "S.A", "S.A.",
    "CIA", "SOCIEDADE", "E", "DE", "DA", "DO", "DOS", "DAS",
)
_SUFIXOS_SET = frozenset(_SUFIXOS)


def somente_digitos(texto: str | int | None) -> str:
    """Retorna só os dígitos de qualquer entrada ('12.345.678/0001-90' → '12345678000190')."""
    if texto is None:
        return ""
    return re.sub(r"\D", "", str(texto))


def _dv_cnpj(base: str) -> str:
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    s1 = sum(int(d) * p for d, p in zip(base, pesos1))
    d1 = 0 if s1 % 11 < 2 else 11 - s1 % 11
    s2 = sum(int(d) * p for d, p in zip(base + str(d1), pesos2))
    d2 = 0 if s2 % 11 < 2 else 11 - s2 % 11
    return f"{d1}{d2}"


def _dv_cpf(base: str) -> str:
    s1 = sum(int(d) * p for d, p in zip(base, range(10, 1, -1)))
    d1 = 0 if s1 % 11 < 2 else 11 - s1 % 11
    s2 = sum(int(d) * p for d, p in zip(base + str(d1), range(11, 1, -1)))
    d2 = 0 if s2 % 11 < 2 else 11 - s2 % 11
    return f"{d1}{d2}"


def cnpj_valido(cnpj: str | int | None) -> bool:
    """Valida CNPJ pelos dígitos verificadores (rejeita sequências repetidas)."""
    d = somente_digitos(cnpj)
    if len(d) != 14 or len(set(d)) == 1:
        return False
    return _dv_cnpj(d[:12]) == d[12:]


def cpf_valido(cpf: str | int | None) -> bool:
    d = somente_digitos(cpf)
    if len(d) != 11 or len(set(d)) == 1:
        return False
    return _dv_cpf(d[:9]) == d[9:]


def normalizar_documento(doc: str | int | None) -> str:
    """CNPJ → 14 dígitos; CPF → 11 dígitos; vazio/inválido → ''.

    Planilhas costumam perder zeros à esquerda quando o campo vira número;
    aqui completamos à esquerda antes de validar.
    """
    d = somente_digitos(doc)
    if not d:
        return ""
    if len(d) <= 11:
        d = d.zfill(11)
        return d if cpf_valido(d) else ""
    d = d.zfill(14)
    return d if cnpj_valido(d) else ""


def formatar_documento(doc: str | int | None) -> str:
    """'90100200000109' → '90.100.200/0001-09'; CPF → '123.456.789-09'; inválido → ''."""
    d = normalizar_documento(doc)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return ""


def raiz_cnpj(cnpj: str | int | None) -> str:
    """Primeiros 8 dígitos: identifica a empresa independentemente da filial."""
    d = normalizar_documento(cnpj)
    return d[:8] if len(d) == 14 else ""


def _sem_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar_nome(nome: str | None) -> str:
    """Razão social comparável: maiúsculas, sem acento/pontuação, sem LTDA/ME/S.A. e artigos.

    'Mercado Central Ltda.' e 'MERCADO CENTRAL LTDA' viram ambos 'MERCADO CENTRAL'.
    """
    if not nome:
        return ""
    t = _sem_acentos(str(nome)).upper()
    t = re.sub(r"\bS[./ ]?A\.?(?=\s|$)", " ", t)          # S.A. / S/A / S A → remove como um só sufixo
    t = re.sub(r"[^A-Z0-9 ]+", " ", t)
    tokens = [tok for tok in t.split() if tok not in _SUFIXOS_SET]
    return " ".join(tokens)


def parse_valor(valor) -> Decimal | None:
    """Aceita 1234.56, '1.234,56', 'R$ 1.234,56', '1234,56', '(100,00)' (negativo)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float, Decimal)):
        try:
            return Decimal(str(valor)).quantize(Decimal("0.01"))
        except InvalidOperation:
            return None
    s = str(valor).strip()
    negativo = s.startswith("(") and s.endswith(")") or s.startswith("-")
    s = re.sub(r"[^\d,.]", "", s)
    if not s:
        return None
    # decide qual é o separador decimal pelo último símbolo presente
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        v = Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return -v if negativo else v


_FORMATOS_DATA = ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y")


def parse_data(valor) -> date | None:
    """Aceita date/datetime, 'dd/mm/aaaa', 'aaaa-mm-dd' e serial do Excel."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, (int, float)) and 20000 < float(valor) < 80000:
        # serial do Excel (dias desde 30/12/1899)
        from datetime import timedelta
        return date(1899, 12, 30) + timedelta(days=int(valor))
    s = str(valor).strip()[:10]
    for fmt in _FORMATOS_DATA:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None
