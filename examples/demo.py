"""Gera uma planilha sintética de contas a pagar com problemas plantados e roda o motor.

    python examples/demo.py

Todos os dados são fictícios; os CNPJs têm dígito verificador válido mas não
pertencem a nenhuma empresa real.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook

from processiq_core import analisar, ler_planilha, resumo

HOJE = date(2026, 5, 10)
SAIDA = Path(__file__).with_name("contas_a_pagar_exemplo.xlsx")


def gerar_planilha(caminho: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Contas a pagar"
    ws.append(["Contas a pagar — maio/2026"])                      # título, deve ser ignorado
    ws.append([])
    ws.append(["NF", "Fornecedor", "CNPJ", "Categoria", "Valor", "Vencimento", "Status"])
    d = lambda n: HOJE + timedelta(days=n)
    linhas = [
        (1042, "Mercado Central Ltda",        "90.100.200/0001-09", "Suprimentos",  4820.00, d(2),   "Pendente"),
        (1043, "Distribuidora Alpha",         "90.100.300/0017-00", "Distribuição", 12300.00, d(-7), "Pendente"),   # vencida
        (1044, "Clínica São Lucas",           "90.100.400/0008-38", "Saúde",        980.00,  d(8),   "Pendente"),
        (1045, "MERCADO CENTRAL LTDA",        "90.100.200/0001-09", "Suprimentos",  4820.00, d(2),   "Pendente"),   # NF duplicada (1042)
        (1046, "Merc. Central Alimentos",     "90.100.200/0025-86", "Suprimentos",  1200.00, d(15),  "Pendente"),   # mesma raiz, nome diferente
        (1047, "Transportes Fictícios S/A",   "90.100.500/0262-35", "Logística",    2100.00, d(-45), "Pendente"),   # vencida > 30 dias
        (1048, "Transportes Ficticios SA",    "",                   "Logística",    2050.00, d(20),  "Pendente"),   # sem CNPJ, nome parecido
        (1049, "Distribuidora Alpha",         "90.100.300/0017-00", "Distribuição", 11800.00, d(30), "Pendente"),
        (1050, "Distribuidora Alpha",         "90.100.300/0017-00", "Distribuição", 12100.00, d(60), "Pendente"),
        (1051, "Distribuidora Alpha",         "90.100.300/0017-00", "Distribuição", 61500.00, d(45), "Pendente"),   # 5x a mediana
        (1052, "Peças Exemplo Eireli",        "12.345.678/0001-00", "Manutenção",   3315.00, d(5),   "Pendente"),   # CNPJ inválido
        (1053, "Serviços Demonstração Ltda",  "90.100.500/0262-35", "Serviços",     0.00,    d(10),  "Pendente"),   # valor zero
        (1054, "",                            "",                   "",             750.00,  d(3),    ""),           # sem fornecedor
        (1055, "Energia Modelo S.A.",         "90.100.400/0008-38", "Utilidades",   1890.00, d(-3),  "Pago"),       # vencida mas paga: ok
    ]
    for l in linhas:
        ws.append(list(l))
    ws.append([None, None, None, None, "=SUM(E4:E17)", None, None])   # rodapé de total
    wb.save(caminho)


def main() -> int:
    gerar_planilha(SAIDA)
    titulos, mapa = ler_planilha(SAIDA)
    alertas = analisar(titulos, hoje=HOJE)
    r = resumo(titulos, alertas, hoje=HOJE)

    print(f"planilha: {SAIDA.name}")
    print(f"colunas reconhecidas: {mapa}")
    print(f"{r['titulos']} títulos · total R$ {float(r['valor_total']):,.2f} · "
          f"vencido R$ {float(r['valor_vencido']):,.2f} · saúde {r['saude_operacional']}/100\n")
    for a in alertas:
        print(f"[{a.severidade.value:>7}] {a.tipo.value:<22} {a.mensagem}")

    # o demo também serve de teste de fumaça no CI
    tipos = {a.tipo.value for a in alertas}
    esperados = {"titulo_duplicado", "fornecedor_duplicado", "vencido", "vence_em_breve",
                 "valor_suspeito", "documento_invalido", "campo_incompleto"}
    faltando = esperados - tipos
    if faltando:
        print(f"\nERRO: detectores que não dispararam: {faltando}", file=sys.stderr)
        return 1
    print(f"\nok: {len(alertas)} alertas, todos os {len(esperados)} tipos de detector dispararam.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
