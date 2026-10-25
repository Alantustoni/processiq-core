from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from processiq_core.leitor import ErroLeitura, ler_planilha, mapear_colunas, titulos_de_linhas

CNPJ = "90.100.200/0001-09"


def test_mapear_colunas_sinonimos_e_acentos():
    cab = ["Nº NF", "Fornecedor", "CNPJ/CPF", "Valor Total", "Dt. Vencto", "Categoria", "Situação"]
    m = mapear_colunas(cab)
    assert m == {"id": 0, "fornecedor": 1, "documento": 2, "valor": 3, "vencimento": 4, "categoria": 5, "status": 6}


def test_mapear_colunas_documento_fiscal_nao_vira_cnpj():
    m = mapear_colunas(["Documento Fiscal", "Razão Social", "CNPJ", "Valor", "Vencimento"])
    assert m["id"] == 0 and m["documento"] == 2


def test_titulos_de_linhas_pula_titulo_e_rodape():
    linhas = [
        ["Contas a pagar — maio/2026"],
        [],
        ["NF", "Fornecedor", "CNPJ", "Valor", "Vencimento", "Status"],
        [1001, "Mercado Central Ltda", CNPJ, "4.820,00", "12/05/2026", "Pendente"],
        [1002.0, "Clínica São Lucas", "", 980, date(2026, 5, 18), ""],
        [None, None, None, "=SUM(D4:D5)", None, None],       # rodapé de total
    ]
    tit, mapa = titulos_de_linhas(linhas)
    assert mapa["fornecedor"] == 1
    assert [t.id for t in tit] == ["1001", "1002"]
    assert tit[0].documento == "90100200000109"
    assert tit[0].valor == Decimal("4820.00")
    assert tit[0].vencimento == date(2026, 5, 12)
    assert tit[0].linha == 4                      # 1-based, como o usuário vê no Excel
    assert tit[1].documento == "" and tit[1].vencimento == date(2026, 5, 18)


def test_sem_cabecalho_reconhecido_da_erro_claro():
    with pytest.raises(ErroLeitura, match="cabeçalho não reconhecido"):
        titulos_de_linhas([["a", "b", "c"], [1, 2, 3]])


def test_planilha_vazia():
    with pytest.raises(ErroLeitura):
        titulos_de_linhas([])


def test_id_ausente_usa_numero_da_linha():
    tit, _ = titulos_de_linhas([["Fornecedor", "Valor", "Vencimento"], ["F", 10, "01/01/2026"]])
    assert tit[0].id == "L2"


def test_ler_csv_com_ponto_e_virgula_latin1(tmp_path: Path):
    p = tmp_path / "cap.csv"
    p.write_bytes("Fornecedor;CNPJ;Valor;Vencimento\nDistribuidora Alpha;90.100.300/0001-70;1.234,56;03/05/2026\n".encode("latin-1"))
    tit, _ = ler_planilha(p)
    assert tit[0].fornecedor == "Distribuidora Alpha" and tit[0].valor == Decimal("1234.56")


def test_ler_xlsx(tmp_path: Path):
    from openpyxl import Workbook
    wb = Workbook(); ws = wb.active
    ws.append(["Fornecedor", "CNPJ", "Valor", "Vencimento"])
    ws.append(["Peças Exemplo Eireli", CNPJ, 3315.5, date(2026, 6, 1)])
    p = tmp_path / "cap.xlsx"; wb.save(p)
    tit, _ = ler_planilha(p)
    assert tit[0].valor == Decimal("3315.50") and tit[0].vencimento == date(2026, 6, 1)


def test_formato_nao_suportado(tmp_path: Path):
    p = tmp_path / "x.pdf"; p.write_bytes(b"%PDF")
    with pytest.raises(ErroLeitura, match="formato não suportado"):
        ler_planilha(p)
