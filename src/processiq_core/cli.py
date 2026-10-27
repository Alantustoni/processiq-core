"""Uso: processiq caminho/para/planilha.xlsx [--json] [--excel relatorio.xlsx] [--hoje AAAA-MM-DD]"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from .detectores import analisar, resumo
from .exportacao import exportar_excel
from .leitor import ErroLeitura, ler_planilha

_ICONE = {"critica": "!!", "alta": "! ", "media": "- ", "baixa": ". "}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="processiq", description="Analisa uma planilha de contas a pagar.")
    p.add_argument("arquivo", help=".xlsx ou .csv")
    p.add_argument("--json", action="store_true", help="saída em JSON (para integrar com o painel)")
    p.add_argument("--excel", metavar="SAIDA.xlsx", help="grava um relatório Excel com as linhas problemáticas marcadas")
    p.add_argument("--hoje", type=date.fromisoformat, default=None, help="data de referência (padrão: hoje)")
    args = p.parse_args(argv)

    try:
        titulos, mapa = ler_planilha(args.arquivo)
    except ErroLeitura as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2

    alertas = analisar(titulos, hoje=args.hoje)
    res = resumo(titulos, alertas, hoje=args.hoje)

    if args.excel:
        destino = exportar_excel(titulos, alertas, res, args.hoje or date.today(), args.excel, origem=args.arquivo)
        print(f"relatório gravado em {destino}", file=sys.stderr)

    if args.json:
        json.dump({"colunas": mapa, "resumo": res, "alertas": [a.to_dict() for a in alertas]},
                  sys.stdout, ensure_ascii=False, indent=2, default=str)
        print()
        return 0

    print(f"{res['titulos']} títulos · total R$ {float(res['valor_total']):,.2f} · "
          f"vencido R$ {float(res['valor_vencido']):,.2f} · saúde {res['saude_operacional']}/100")
    print(f"colunas reconhecidas: {', '.join(f'{k}=col{v + 1}' for k, v in mapa.items())}")
    print()
    for a in alertas:
        print(f"{_ICONE[a.severidade.value]} [{a.tipo.value}] {a.mensagem}")
    if not alertas:
        print("nenhum alerta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
