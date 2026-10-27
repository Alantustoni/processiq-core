"""API HTTP do motor — camada de transporte, sem regra de negócio.

Tudo que decide se um título é suspeito está em `processiq_core.detectores`.
Aqui só: receber o arquivo, chamar o motor, converter para JSON, tratar erro.

    uvicorn processiq_core.api:app --reload
    → http://localhost:8000/docs
"""

from __future__ import annotations

import os
import tempfile
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from .. import __version__
from ..detectores import analisar, resumo
from ..leitor import ErroLeitura, ler_planilha
from .schemas import AlertaOut, AnaliseOut, ColunasReconhecidas, Erro, Resumo, TituloOut

TAMANHO_MAXIMO = 10 * 1024 * 1024          # 10 MB: planilha de contas a pagar de PME cabe folgado
EXTENSOES = {".xlsx", ".xlsm", ".csv", ".txt"}

app = FastAPI(
    title="ProcessIQ Core API",
    version=__version__,
    description=(
        "Envie uma planilha de contas a pagar (.xlsx ou .csv) e receba as colunas reconhecidas, "
        "um resumo com índice de saúde operacional e a lista de alertas: NF duplicada, fornecedor "
        "duplicado, vencidos, valor suspeito, CNPJ inválido e campos incompletos."
    ),
)


@app.exception_handler(ErroLeitura)
async def _erro_leitura(_, exc: ErroLeitura):
    return JSONResponse(status_code=422, content=Erro(erro=str(exc)).model_dump())


@app.get("/health", tags=["infra"])
def health() -> dict:
    return {"status": "ok", "versao": __version__}


@app.post(
    "/analisar",
    response_model=AnaliseOut,
    responses={413: {"model": Erro}, 415: {"model": Erro}, 422: {"model": Erro}},
    tags=["análise"],
    summary="Analisa uma planilha de contas a pagar",
)
async def analisar_planilha(
    arquivo: UploadFile = File(..., description=".xlsx ou .csv"),
    hoje: date | None = Query(default=None, description="data de referência (padrão: hoje)"),
    incluir_titulos: bool = Query(default=False, description="devolve também os títulos lidos"),
) -> AnaliseOut:
    nome = arquivo.filename or "planilha"
    sufixo = Path(nome).suffix.lower()
    if sufixo not in EXTENSOES:
        raise HTTPException(415, f"formato não suportado: '{sufixo}' (use .xlsx ou .csv)")

    conteudo = await arquivo.read()
    if len(conteudo) > TAMANHO_MAXIMO:
        raise HTTPException(413, f"arquivo acima de {TAMANHO_MAXIMO // (1024 * 1024)} MB")
    if not conteudo:
        raise HTTPException(422, "arquivo vazio")

    # o leitor trabalha com caminho. No Windows um NamedTemporaryFile aberto fica
    # bloqueado para outros leitores, então gravamos, fechamos, lemos e apagamos.
    fd, caminho_tmp = tempfile.mkstemp(suffix=sufixo)
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(conteudo)
        titulos, mapa = ler_planilha(caminho_tmp)
    finally:
        try:
            os.unlink(caminho_tmp)
        except OSError:
            pass

    ref = hoje or date.today()
    alertas = analisar(titulos, hoje=ref)
    res = resumo(titulos, alertas, hoje=ref)

    return AnaliseOut(
        arquivo=nome,
        hoje=ref.isoformat(),
        colunas=ColunasReconhecidas(**mapa),
        resumo=Resumo(**res),
        alertas=[AlertaOut.de_alerta(a) for a in alertas],
        titulos=[TituloOut.de_titulo(t) for t in titulos] if incluir_titulos else None,
    )
