"""
text_processing.py - Text processing and normalization utilities

Provides common text processing functions used across the project.
"""

import re
import html
import unicodedata
from typing import List, Optional
from ftfy import fix_text


def strip_html(text: str) -> str:
    """Remove HTML tags from text (light fallback).
    
    Args:
        text: Text potentially containing HTML
        
    Returns:
        Text with HTML tags removed
    """
    return re.sub(r"<[^>]+>", "", html.unescape(text))


def normalize_text(text: str) -> str:
    """Normalize text using Unicode NFKC normalization.
    
    Handles line endings and Unicode normalization.
    
    Args:
        text: Text to normalize
        
    Returns:
        Normalized text
    """
    return unicodedata.normalize("NFKC", text.replace("\r\n", "\n"))


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text.
    
    Collapses multiple whitespace characters into single spaces,
    removes leading/trailing whitespace, and normalizes line endings.
    
    Args:
        text: Text to normalize
        
    Returns:
        Text with normalized whitespace
    """
    # Normalize line endings first
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse multiple whitespace into single spaces
    text = re.sub(r'\s+', ' ', text)
    # Remove leading/trailing whitespace
    return text.strip()


def smart_estimate_words(text: str) -> int:
    """Smart word count estimation that handles various text formats.
    
    More accurate than simple split() for text with punctuation,
    contractions, and formatting.
    
    Args:
        text: Text to count words in
        
    Returns:
        Estimated word count
    """
    if not text:
        return 0
    
    # Remove extra whitespace and normalize
    text = normalize_whitespace(text)
    
    # Split on whitespace and filter out empty strings
    words = [word for word in text.split() if word.strip()]
    
    return len(words)


def estimate_max_tokens(words: int, factor: float = 1.4) -> int:
    """Estimate maximum tokens needed based on word count.
    
    Uses approximation: 1 token ≈ 0.75 words, padded by factor.
    
    Args:
        words: Number of words
        factor: Padding factor for safety margin
        
    Returns:
        Estimated max tokens (minimum 1024, maximum 8192)
    """
    return max(1024, min(int(words / 0.75 * factor), 8192))


def extract_ending_words(text: str, num_words: int = 60) -> str:
    """Extract the last N words from text.
    
    Args:
        text: Source text
        num_words: Number of words to extract from end
        
    Returns:
        Last N words as a string
    """
    return " ".join(text.split()[-num_words:])


def segment_text(text: str, chunk_words: int = 250) -> List[str]:
    """Segment text into chunks of approximately N words.
    
    Args:
        text: Text to segment
        chunk_words: Target words per chunk
        
    Returns:
        List of text segments
    """
    words = text.split()
    return [" ".join(words[i:i+chunk_words])
            for i in range(0, len(words), chunk_words)]


def count_words(text: str) -> int:
    """Count words in text.
    
    Args:
        text: Text to count words in
        
    Returns:
        Number of words
    """
    return len(text.split())


def escape_for_fstring(text: str) -> str:
    """Escape text for safe use in f-strings.
    
    Handles braces and backslashes that would otherwise cause issues.
    
    Args:
        text: Text to escape
        
    Returns:
        Escaped text safe for f-string substitution
    """
    # Escape braces for f-string safety
    text = text.replace("{", "{{").replace("}", "}}")
    # Escape backslashes
    text = text.replace("\\", "\\\\")
    return text


def clean_json_text(blocks: List[dict], 
                   content_keys: List[str] = None) -> str:
    """Extract and clean text from JSON blocks.
    
    Args:
        blocks: List of JSON blocks/dictionaries
        content_keys: Keys to check for content (default: content, body, text)
        
    Returns:
        Cleaned and joined text
    """
    if content_keys is None:
        content_keys = ["content", "body", "text"]
    
    parts = []
    for block in blocks:
        for key in content_keys:
            if key in block and isinstance(block[key], str):
                # Apply ftfy to fix encoding issues, then strip HTML
                cleaned = strip_html(fix_text(block[key]))
                if cleaned:  # Only add non-empty parts
                    parts.append(cleaned)
    
    return normalize_text("\n\n".join(parts))


def truncate_to_words(text: str, max_words: int) -> str:
    """Truncate text to a maximum number of words.
    
    Args:
        text: Text to truncate
        max_words: Maximum number of words
        
    Returns:
        Truncated text
    """
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words])


def create_length_hint(target_words: int, tolerance: float = 0.1) -> str:
    """Create a length hint string for prompts.
    
    Args:
        target_words: Target word count
        tolerance: Tolerance as fraction (0.1 = ±10%)
        
    Returns:
        Human-readable length hint
    """
    tolerance_pct = int(tolerance * 100)
    return f"Match the source length within ±{tolerance_pct}% (≈{target_words} words)." 