from datetime import date
from decimal import Decimal

from processiq_core.detectores import (
    analisar, detectar_campos_incompletos, detectar_fornecedores_duplicados, detectar_titulos_duplicados,
    detectar_valores_suspeitos, detectar_vencidos, resumo,
)
from processiq_core.modelo import Severidade, TipoAlerta, Titulo

HOJE = date(2026, 5, 10)
CNPJ_A = "90100200000109"       # Mercado Central (matriz)
CNPJ_A_FILIAL = "90100200002586"
CNPJ_B = "90100300001700"       # Distribuidora Alpha


def t(id, forn, doc="", valor="100.00", venc=date(2026, 5, 20), linha=2, status="", doc_bruto=None):
    return Titulo(id=id, fornecedor=forn, documento=doc, valor=Decimal(valor) if valor is not None else None,
                  vencimento=venc, linha=linha, status=status,
                  documento_bruto=doc_bruto if doc_bruto is not None else doc)


# ---------- fornecedor duplicado ----------

def test_mesmo_cnpj_raiz_com_nomes_diferentes_e_alta():
    tit = [t("1", "Mercado Central Ltda", CNPJ_A, linha=2),
           t("2", "MERCADO CENTRAL LTDA", CNPJ_A_FILIAL, linha=3),      # mesmo nome normalizado: não é duplicidade
           t("3", "Merc. Central Alimentos", CNPJ_A, linha=4)]          # nome diferente: é
    al = detectar_fornecedores_duplicados(tit)
    assert len(al) == 1
    assert al[0].severidade == Severidade.ALTA
    assert al[0].detalhes["criterio"] == "cnpj"
    assert set(al[0].linhas) == {2, 3, 4}


def test_nomes_parecidos_sem_cnpj_e_media():
    tit = [t("1", "Distribuidora Alpha Ltda", linha=2), t("2", "Distrib. Alpha Ltda", linha=3)]
    al = detectar_fornecedores_duplicados(tit)
    assert len(al) == 1
    assert al[0].severidade == Severidade.MEDIA
    assert al[0].detalhes["criterio"] == "nome"


def test_nomes_parecidos_mas_cnpjs_diferentes_nao_alerta():
    tit = [t("1", "Distribuidora Alpha", CNPJ_A), t("2", "Distribuidora Alpha Sul", CNPJ_B)]
    assert detectar_fornecedores_duplicados(tit) == []


def test_nomes_distintos_nao_alerta():
    tit = [t("1", "Mercado Central"), t("2", "Clinica Sao Lucas")]
    assert detectar_fornecedores_duplicados(tit) == []


# ---------- título duplicado ----------

def test_titulo_duplicado_mesmo_fornecedor_valor_vencimento():
    tit = [t("1001", "Fornecedor Exemplo", valor="4820.00", linha=2),
           t("1001", "FORNECEDOR EXEMPLO LTDA", valor="4820.00", linha=9)]
    al = detectar_titulos_duplicados(tit)
    assert len(al) == 1 and al[0].severidade == Severidade.CRITICA
    assert al[0].linhas == (2, 9)


def test_titulo_nao_duplicado_se_valor_diferente():
    tit = [t("1", "Fornecedor", valor="100.00"), t("2", "Fornecedor", valor="100.01")]
    assert detectar_titulos_duplicados(tit) == []


# ---------- vencimentos ----------

def test_vencido_alta_e_critica_apos_30_dias():
    tit = [t("1", "A", venc=date(2026, 5, 1), linha=2), t("2", "B", venc=date(2026, 3, 1), linha=3)]
    al = detectar_vencidos(tit, hoje=HOJE)
    assert [a.severidade for a in al] == [Severidade.ALTA, Severidade.CRITICA]
    assert al[0].detalhes["dias_atraso"] == 9


def test_vencido_mas_pago_nao_alerta():
    tit = [t("1", "A", venc=date(2026, 5, 1), status="Pago")]
    assert detectar_vencidos(tit, hoje=HOJE) == []


def test_vence_em_breve_baixa():
    tit = [t("1", "A", venc=date(2026, 5, 15))]
    al = detectar_vencidos(tit, hoje=HOJE)
    assert al[0].tipo == TipoAlerta.VENCE_EM_BREVE and al[0].detalhes["dias_para_vencer"] == 5


def test_vence_depois_da_janela_nao_alerta():
    tit = [t("1", "A", venc=date(2026, 6, 15))]
    assert detectar_vencidos(tit, hoje=HOJE) == []


# ---------- valor suspeito ----------

def test_outlier_contra_mediana_do_fornecedor():
    tit = [t(str(i), "Fornecedor", valor="1000.00", linha=i) for i in range(2, 6)] + [t("9", "Fornecedor", valor="9000.00", linha=9)]
    al = detectar_valores_suspeitos(tit)
    assert len(al) == 1 and al[0].linhas == (9,) and al[0].detalhes["motivo"] == "outlier"


def test_sem_historico_minimo_nao_alerta_outlier():
    tit = [t("1", "F", valor="100.00"), t("2", "F", valor="9000.00")]
    assert detectar_valores_suspeitos(tit) == []


def test_valor_zero_ou_negativo():
    tit = [t("1", "F", valor="0.00"), t("2", "F", valor="-10.00")]
    al = detectar_valores_suspeitos(tit)
    assert len(al) == 2 and all(a.detalhes["motivo"] == "nao_positivo" for a in al)


# ---------- campos ----------

def test_campo_incompleto_e_documento_invalido():
    tit = [t("1", "", valor=None, venc=None, linha=5),
           t("2", "F", doc="", doc_bruto="12345678000100", linha=6)]
    al = detectar_campos_incompletos(tit)
    tipos = sorted(a.tipo for a in al)
    assert tipos == [TipoAlerta.CAMPO_INCOMPLETO, TipoAlerta.DOCUMENTO_INVALIDO]
    assert al[0].detalhes["faltando"] == ["fornecedor", "valor", "vencimento"]


# ---------- orquestração ----------

def test_analisar_ordena_por_severidade():
    tit = [t("1", "A", venc=date(2026, 5, 12), linha=2),               # baixa
           t("2", "B", venc=date(2026, 1, 1), linha=3),                # crítica (>30 dias)
           t("3", "C", valor="0.00", linha=4)]                         # média
    al = analisar(tit, hoje=HOJE)
    sevs = [a.severidade for a in al]
    assert sevs == sorted(sevs, key=[Severidade.CRITICA, Severidade.ALTA, Severidade.MEDIA, Severidade.BAIXA].index)


def test_resumo_totais_e_saude():
    tit = [t("1", "A", valor="100.00", venc=date(2026, 5, 1)),          # vencido
           t("2", "B", valor="200.00", venc=date(2026, 5, 15)),         # próximos 7 dias
           t("3", "C", valor="300.00", venc=date(2026, 7, 1), status="pago")]
    al = analisar(tit, hoje=HOJE)
    r = resumo(tit, al, hoje=HOJE)
    assert r["titulos"] == 3
    assert r["valor_total"] == "600.00"
    assert r["valor_vencido"] == "100.00"
    assert r["valor_proximos_7_dias"] == "200.00"
    assert 0 <= r["saude_operacional"] < 100
