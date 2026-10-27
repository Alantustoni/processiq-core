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
python examples/demo.py                                 # gera uma planilha sintética cheia de problemas
processiq examples/contas_a_pagar_exemplo.xlsx --hoje 2026-05-10
```

Com a sua própria planilha: `processiq contas_a_pagar.xlsx`.

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

## API HTTP

O mesmo motor, atrás de uma API FastAPI, para o painel do ProcessIQ (ou qualquer front) consumir:

```bash
pip install "processiq-core[api] @ git+https://github.com/Alantustoni/processiq-core"
uvicorn processiq_core.api:app --reload
```

Swagger em `http://localhost:8000/docs`. Um único endpoint faz o trabalho:

```bash
curl -X POST "http://localhost:8000/analisar?hoje=2026-05-10" \
     -F "arquivo=@examples/contas_a_pagar_exemplo.xlsx"
```

```json
{
  "arquivo": "contas_a_pagar_exemplo.xlsx",
  "hoje": "2026-05-10",
  "colunas": { "id": 0, "fornecedor": 1, "documento": 2, "valor": 4, "vencimento": 5, "categoria": 3, "status": 6 },
  "resumo": { "titulos": 14, "valor_total": "119625.00", "valor_vencido": "14400.00",
              "alertas": 14, "por_severidade": { "critica": 2, "alta": 5, "media": 3, "baixa": 4 },
              "saude_operacional": 22 },
  "alertas": [
    { "tipo": "titulo_duplicado", "severidade": "critica",
      "mensagem": "2 lançamentos iguais para 'Mercado Central Ltda': R$ 4,820.00 vencendo em 12/05/2026 (linhas 4, 7)",
      "titulos": ["1042", "1045"], "linhas": [4, 7], "detalhes": { "valor": "4820.00", "vencimento": "2026-05-12" } }
  ]
}
```

| Método | Rota | O que faz |
|---|---|---|
| `POST` | `/analisar` | recebe `.xlsx`/`.csv` (multipart), devolve colunas, resumo e alertas; `?hoje=AAAA-MM-DD` fixa a data; `?incluir_titulos=true` devolve também os títulos lidos |
| `GET` | `/health` | versão e status, para o orquestrador |

Erros chegam como JSON com código certo: `415` formato não suportado, `413` acima de 10 MB, `422` planilha ilegível (a mensagem do motor vai junto: "cabeçalho não reconhecido: preciso de colunas de fornecedor, valor e vencimento").

Para subir em container: `docker build -t processiq-core . && docker run -p 8000:8000 processiq-core`.

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

## Arquitetura

Duas camadas, com uma fronteira explícita:

```
                    ┌──────────────────────────────────────────────┐
  CLI (processiq)   │  motor — processiq_core                       │
  ───────────────►  │  leitor.py  →  Titulo[]  →  detectores.py    │   só stdlib + openpyxl + rapidfuzz
                    │  modelo.py (dataclasses)   normalizacao.py   │   sem HTTP, sem framework, sem I/O além do arquivo
  API (FastAPI)     │                                              │
  ───────────────►  └──────────────────────────────────────────────┘
        │
        └── processiq_core.api: schemas.py (Pydantic) converte dataclasses → JSON na borda;
            app.py só recebe upload, chama o motor e traduz erro em status HTTP.
```

- **O motor não sabe que a API existe.** `detectores.py` recebe `list[Titulo]` e devolve `list[Alerta]`; é testado direto, sem subir servidor (58 testes).
- **A API não contém regra.** Nenhum `if` de negócio em `app.py`; ela valida tamanho e extensão, chama `ler_planilha → analisar → resumo` e converte. Testada com `TestClient` enviando planilhas reais (10 testes).
- **Mesmo resultado por qualquer porta de entrada.** CLI e API chamam as mesmas funções; o demo roda nas duas no CI.
- **O painel escala separado.** O front do ProcessIQ só precisa do contrato em `schemas.py` (exposto no OpenAPI); o motor pode mudar por dentro sem quebrar o painel, e vice-versa.

```
src/processiq_core/
├── normalizacao.py   CNPJ/CPF, nomes, valores, datas (stdlib)
├── leitor.py         .xlsx/.csv → lista de Titulo + mapa de colunas
├── detectores.py     as 7 regras + analisar() + resumo()
├── modelo.py         Titulo, Alerta, enums
├── cli.py            comando `processiq`
└── api/
    ├── app.py        FastAPI: /analisar, /health, tratamento de erro
    └── schemas.py    contratos Pydantic (AnaliseOut, AlertaOut, Resumo…)
tests/                68 testes (pytest): 58 do motor + 10 da API
examples/demo.py      gera planilha sintética e roda o motor; roda no CI como teste de fumaça
Dockerfile            imagem slim com o extra [api]
```

## Testes

```bash
pip install -e .[dev]
python -m pytest -q
```

CI em Ubuntu e Windows, Python 3.11 a 3.13; além do pytest, o workflow sobe a API e envia a planilha de exemplo pelo `curl`.

## Roadmap

- [x] API HTTP (FastAPI) para o painel do ProcessIQ consumir
- [ ] Exportação do relatório em Excel com as linhas marcadas
- [ ] Sugestão de fornecedor canônico ao unificar duplicados
- [ ] Leitura de extrato bancário para cruzar pago × previsto (reaproveitando a lógica do [contas-a-pagar-suite](https://github.com/Alantustoni/contas-a-pagar-suite))

## Licença

MIT — veja [LICENSE](LICENSE).
