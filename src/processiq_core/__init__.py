"""processiq-core — motor de análise de planilhas de contas a pagar."""

from .canonico import aplicar_unificacao, de_para, sugerir_canonico
from .detectores import analisar, resumo
from .leitor import ErroLeitura, ler_planilha, titulos_de_linhas
from .modelo import Alerta, Severidade, TipoAlerta, Titulo

__version__ = "0.2.0"
__all__ = ["analisar", "resumo", "sugerir_canonico", "de_para", "aplicar_unificacao", "ler_planilha", "titulos_de_linhas", "ErroLeitura",
           "Alerta", "Severidade", "TipoAlerta", "Titulo"]
