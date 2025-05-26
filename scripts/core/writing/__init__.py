"""
Writing module - Core logic for draft creation and revision

This module provides:
- PromptBuilder: Creates prompts for various writing tasks
- SourceLoader: Loads text from different source formats
- DraftWriter: Creates first drafts with various modes
- RevisionHandler: Applies revisions based on feedback
"""

from scripts.core.writing.prompts import PromptBuilder
from scripts.core.writing.drafting import SourceLoader, DraftWriter
from scripts.core.writing.revision import RevisionHandler

__all__ = ['PromptBuilder', 'SourceLoader', 'DraftWriter', 'RevisionHandler'] 