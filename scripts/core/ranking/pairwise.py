"""
pairwise.py - Pairwise comparison ranking

This module provides pairwise comparison functionality for
comprehensive ranking of chapter versions.
"""

from typing import Dict, List, Tuple, Any

def pairwise_rank_chapter_versions(
    chapter_id: str,
    versions: List[Tuple[str, str, str]],
    repeats: int = 1,
) -> Dict[str, Any]:
    """
    Rank versions using comprehensive pairwise comparisons.
    
    TODO: Extract this function from elo_ranking.py
    """
    # Temporary import to maintain functionality during refactoring
    from ..elo_ranking import pairwise_rank_chapter_versions as _pairwise_rank
    return _pairwise_rank(chapter_id, versions, repeats) 