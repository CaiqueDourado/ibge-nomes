"""IBGE names API (Censo 2010): rank, frequency, states, sex and decade of birth for Brazilian first names."""

from .client import DECADES, ApiError, IbgeNomes, decade_label, fold, summarize

__all__ = ["IbgeNomes", "ApiError", "DECADES", "decade_label", "fold", "summarize"]
__version__ = "0.1.0"
