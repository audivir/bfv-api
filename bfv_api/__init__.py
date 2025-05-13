"""A module for retrieving data from the BFV API."""

from __future__ import annotations

from bfv_api.bfv import BFV
from bfv_api.bfv import Match as BFVMatch
from bfv_api.standings import Match, Tiebreaker, show_standings

__version__ = "0.1.0"

__all__ = ["BFV", "BFVMatch", "Match", "Tiebreaker", "show_standings"]
