# processiq-core

[![tests](https://github.com/Alantustoni/processiq-core/actions/workflows/tests.yml/badge.svg)](https://github.com/Alantustoni/processiq-core/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/Python-3.11%2B-3776ab?logo=python&logoColor=white)
![Licença](https://img.shields.io/badge/licen%C3%A7a-MIT-green)

Motor de análise de planilhas de **contas a pagar** para pequenas empresas: lê o Excel ou CSV que a empresa já usa, reconhece as colunas sozinho e aponta o que vai doer — fornecedor cadastrado duas vezes, nota lançada em duplicidade, título vencido, valor fora do padrão, CNPJ inválido.

É o back-end do [ProcessIQ](https://github.com/Alantustoni/processiq). O protótipo da interface foi feito primeiro, com dados simulados; este pacote é a parte que faz a análise de verdade.

## Por que existe

Trabalho com contas a pagar dentro de um ERP, com CNAB240, DDA e conciliação bancária. Em empresas menores nada disso existe: o controle é uma planilha, o fornecedor aparece como "Mercado Central Ltda" numa linha e "MERCADO CENTRAL" em outra, a mesma NF entra duas vezes e o vencimento passa. Este motor é a tentativa de levar para esse público a checagem que um setor financeiro estruturado faz todo dia.

## Uso

```bash
pip install git+https://github.com/Alantustoni/processiq-core
processiq contas_a_pagar.xlsx
```

```
15 títulos · total R$ 119,625.00 · vencido R$ 14,400.00 · saúde 8/100
colunas reconhecidas: id=col1, fornecedor=col2, documento=col3, valor=col5, vencimento=col6, categoria=col4, status=col7

!! [titulo_duplicado] 2 lançamentos iguais para 'Mercado Central Ltda': R$ 4,820.00 vencendo em 12/05/2026 (linhas 4, 7)
!! [vencido] 'Transportes Fictícios S/A' venceu há 45 dia(s) (26/03/2026) e não consta como pago
!  [fornecedor_duplicado] CNPJ raiz 90100200 aparece com 2 nomes diferentes: MERC CENTRAL ALIMENTOS | MERCADO CENTRAL
!  [valor_suspeito] 'Distribuidora Alpha': R$ 61,500.00 é 5.0x a mediana do fornecedor (R$ 12,200.00) — confira
-  [documento_invalido] CNPJ/CPF inválido na linha 14 ('12345678000100') para 'Peças Exemplo Eireli'
```

`--json` devolve o mesmo resultado estruturado (colunas reconhecidas, resumo e alertas) para alimentar um painel. `--hoje AAAA-MM-DD` fixa a data de referência.

Como biblioteca:

```python
from processiq_core import ler_planilha, analisar, resumo

titulos, colunas = ler_planilha("contas_a_pagar.xlsx")
alertas = analisar(titulos)
print(resumo(titulos, alertas)["saude_operacional"])
```

Para ver tudo funcionando com uma planilha sintética cheia de problemas plantados: `python examples/demo.py`.

## O que ele detecta

| Alerta | Regra | Severidade |
|---|---|---|
| `titulo_duplicado` | mesmo fornecedor + valor + vencimento em mais de uma linha | crítica |
| `fornecedor_duplicado` | mesma **raiz de CNPJ** com nomes diferentes; ou nomes muito parecidos sem CNPJ em comum (tolera abreviação: "Distrib." ↔ "Distribuidora") | alta / média |
| `vencido` | vencimento passado e status não é pago; > 30 dias vira crítica | alta / crítica |
| `vence_em_breve` | vence nos próximos 7 dias | baixa |
| `valor_suspeito` | > 4× a mediana do fornecedor (com ≥ 3 títulos de histórico), ou zero/negativo | alta / média |
| `documento_invalido` | CNPJ/CPF com dígito verificador errado | média |
| `campo_incompleto` | sem fornecedor, valor ou vencimento | média |

Nomes parecidos com CNPJs de raízes **diferentes** nunca alertam: são empresas distintas.

## Como lê a planilha

Não exige modelo. O leitor procura a linha de cabeçalho nas 15 primeiras linhas (planilhas de pequena empresa têm título e logo antes da tabela) e reconhece cada campo por sinônimos: `CNPJ` / `CPF/CNPJ` / `Documento`; `Vencimento` / `Dt. Vencto` / `Data Venc`; `Valor` / `Valor Total` / `Vlr`. Devolve o mapa de colunas para o usuário conferir.

Normalização que acontece antes de qualquer regra (`normalizacao.py`, só biblioteca padrão):

- **CNPJ/CPF**: aceita formatado ou não, completa zero à esquerda perdido pelo Excel, valida o dígito verificador; raiz de 8 dígitos agrupa matriz e filiais.
- **Razão social**: maiúsculas, sem acento, sem `LTDA`/`ME`/`EIRELI`/`S.A.`/`S/A`, sem artigos.
- **Valor**: `1.234,56`, `R$ 1.234,56`, `1,234.56`, `(100,00)` → `Decimal`.
- **Data**: `dd/mm/aaaa`, `aaaa-mm-dd`, `datetime` e serial do Excel.

## Estrutura

```
src/processiq_core/
├── normalizacao.py   CNPJ/CPF, nomes, valores, datas (stdlib)
├── leitor.py         .xlsx/.csv → lista de Titulo + mapa de colunas
├── detectores.py     as 7 regras + analisar() + resumo()
├── modelo.py         Titulo, Alerta, enums
└── cli.py            comando `processiq`
tests/                58 testes (pytest)
examples/demo.py      gera planilha sintética e roda o motor; roda no CI como teste de fumaça
```

## Testes

```bash
pip install -e .[dev]
python -m pytest -q
```

CI em Ubuntu e Windows, Python 3.11 a 3.13.

## Roadmap

- [ ] API HTTP (FastAPI) para o painel do ProcessIQ consumir
- [ ] Exportação do relatório em Excel com as linhas marcadas
- [ ] Sugestão de fornecedor canônico ao unificar duplicados
- [ ] Leitura de extrato bancário para cruzar pago × previsto (reaproveitando a lógica do [contas-a-pagar-suite](https://github.com/Alantustoni/contas-a-pagar-suite))

## Licença

MIT — veja [LICENSE](LICENSE).
