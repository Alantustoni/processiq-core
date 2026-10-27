"""Camada HTTP do processiq-core. Requer o extra `[api]`: pip install processiq-core[api]"""

from .app import app

__all__ = ["app"]
