"""CLI para resultados en vivo de LIDOM."""

from .client import LidomApiClient, LidomGameScore, get_today_in_dominican_republic

__all__ = ["LidomApiClient", "LidomGameScore", "get_today_in_dominican_republic"]
