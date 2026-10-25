"""processiq-core — motor de análise de planilhas de contas a pagar."""

from .detectores import analisar, resumo
from .leitor import ErroLeitura, ler_planilha, titulos_de_linhas
from .modelo import Alerta, Severidade, TipoAlerta, Titulo

__version__ = "0.1.0"
__all__ = ["analisar", "resumo", "ler_planilha", "titulos_de_linhas", "ErroLeitura",
           "Alerta", "Severidade", "TipoAlerta", "Titulo"]
