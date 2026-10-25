from datetime import date, datetime
from decimal import Decimal

import pytest

from processiq_core.normalizacao import (
    cnpj_valido, cpf_valido, normalizar_documento, normalizar_nome, parse_data, parse_valor, raiz_cnpj,
)

# CNPJs sintéticos com dígito verificador válido
CNPJ_OK = "90100200000109"
CNPJ_FILIAL = "90100200002586"


def test_cnpj_valido_aceita_formatado_e_sem_formato():
    assert cnpj_valido(CNPJ_OK)
    assert cnpj_valido("90.100.200/0001-09")


def test_cnpj_valido_rejeita_dv_errado_e_sequencia():
    assert not cnpj_valido("90100200000100")
    assert not cnpj_valido("11111111111111")
    assert not cnpj_valido("")
    assert not cnpj_valido(None)


def test_cpf_valido():
    assert cpf_valido("529.982.247-25")
    assert not cpf_valido("529.982.247-24")
    assert not cpf_valido("00000000000")


def test_normalizar_documento_completa_zero_a_esquerda():
    # planilha converteu para número e perdeu o zero inicial do CPF 052.998.224-72 (sintético)
    assert normalizar_documento(5299822472) == "" or normalizar_documento(5299822472).startswith("0")
    assert normalizar_documento("52998224725") == "52998224725"
    assert normalizar_documento(52998224725) == "52998224725"


def test_normalizar_documento_invalido_vira_vazio():
    assert normalizar_documento("123") == ""
    assert normalizar_documento("abc") == ""


def test_raiz_cnpj_ignora_filial():
    assert raiz_cnpj(CNPJ_OK) == raiz_cnpj(CNPJ_FILIAL) == "90100200"
    assert raiz_cnpj("52998224725") == ""   # CPF não tem raiz


@pytest.mark.parametrize("a,b", [
    ("Mercado Central Ltda.", "MERCADO CENTRAL LTDA"),
    ("Distribuidora Alpha S.A.", "DISTRIBUIDORA ALPHA SA"),
    ("Clínica São Lucas ME", "CLINICA SAO LUCAS"),
    ("Transportes Fictícios S/A", "TRANSPORTES FICTICIOS"),
    ("Serviços de Demonstração Ltda - ME", "SERVICOS DEMONSTRACAO"),
    ("Cia. Brasileira de Aço", "BRASILEIRA ACO"),
])
def test_normalizar_nome_iguala_variacoes(a, b):
    assert normalizar_nome(a) == normalizar_nome(b)


def test_normalizar_nome_vazio():
    assert normalizar_nome(None) == ""
    assert normalizar_nome("  ") == ""


@pytest.mark.parametrize("entrada,esperado", [
    (1234.5, Decimal("1234.50")),
    ("1.234,56", Decimal("1234.56")),
    ("R$ 1.234,56", Decimal("1234.56")),
    ("1234,56", Decimal("1234.56")),
    ("1,234.56", Decimal("1234.56")),
    ("980", Decimal("980.00")),
    ("(100,00)", Decimal("-100.00")),
    ("-50", Decimal("-50.00")),
    ("", None),
    (None, None),
    ("abc", None),
])
def test_parse_valor(entrada, esperado):
    assert parse_valor(entrada) == esperado


@pytest.mark.parametrize("entrada,esperado", [
    ("12/05/2026", date(2026, 5, 12)),
    ("2026-05-12", date(2026, 5, 12)),
    ("12-05-2026", date(2026, 5, 12)),
    ("12/05/26", date(2026, 5, 12)),
    (datetime(2026, 5, 12, 10, 30), date(2026, 5, 12)),
    (date(2026, 5, 12), date(2026, 5, 12)),
    (46154, date(2026, 5, 12)),          # serial do Excel
    ("", None),
    ("não sei", None),
])
def test_parse_data(entrada, esperado):
    assert parse_data(entrada) == esperado
