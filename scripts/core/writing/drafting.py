"""
drafting.py - First draft creation logic

This module handles:
- Loading source text from various formats (JSON, segments, context)
- Creating first drafts with segmented mode support
- Sample truncation for auditions
- Prompt building and LLM interaction
"""

import json
import os
import pathlib
import time
from typing import List, Optional, Tuple
from scripts.utils.io_helpers import read_utf8, write_utf8
from scripts.utils.text_processing import (
    strip_html, normalize_whitespace, smart_estimate_words,
    create_length_hint
)
from scripts.utils.logging_helper import get_logger
from scripts.utils.llm_client import get_llm_client
from scripts.core.writing.prompts import PromptBuilder

log = get_logger()


class SourceLoader:
    """Handles loading text from various source formats."""
    
    def __init__(self, raw_dir: pathlib.Path, seg_dir: pathlib.Path, ctx_dir: pathlib.Path):
        self.raw_dir = raw_dir
        self.seg_dir = seg_dir
        self.ctx_dir = ctx_dir
    
    def load_raw_text(self, chap_path: pathlib.Path) -> Tuple[str, str]:
        """Load raw text from JSON or plain text file.
        
        Returns:
            Tuple of (raw_text, chapter_id)
        """
        if chap_path.suffix == ".json":
            # Load from JSON
            with open(chap_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Handle both list and dict formats
            if isinstance(data, list):
                # Take the first item if it's a list
                if data:
                    data = data[0]
                else:
                    raise ValueError(f"Empty JSON list in {chap_path}")
            
            # Extract text from various possible keys
            raw_text = ""
            for key in ["raw", "_raw", "body", "content", "text"]:
                if key in data and isinstance(data[key], str):
                    raw_text = data[key]
                    break
            
            if not raw_text:
                raise ValueError(f"No text content found in {chap_path}")
            
            raw_text = strip_html(raw_text)
            # Normalize whitespace
            raw_text = normalize_whitespace(raw_text)
            chap_id = chap_path.stem
            
            log.info(f"loaded {smart_estimate_words(raw_text)} words from {chap_path.name}")
        elif chap_path.suffix == ".txt":
            # Plain text file
            raw_text = read_utf8(chap_path)
            chap_id = chap_path.stem
        else:
            # Chapter ID - look for source
            chap_id = chap_path.stem
            
            # Try RAW_DIR first
            json_path = self.raw_dir / f"{chap_id}.json"
            if json_path.exists():
                return self.load_raw_text(json_path)
            
            # Try SEG_DIR
            seg_path = self.seg_dir / f"{chap_id}.txt"
            if seg_path.exists():
                raw_text = read_utf8(seg_path)
            # Try CTX_DIR
            elif (ctx_path := self.ctx_dir / f"{chap_id}.txt").exists():
                raw_text = read_utf8(ctx_path)
            else:
                raise FileNotFoundError(f"No source found for chapter {chap_id}")
        
        return raw_text, chap_id
    
    def load_segments(self, chap_id: str) -> Optional[List[str]]:
        """Load segmented text if available."""
        seg_path = self.seg_dir / f"{chap_id}.txt"
        if not seg_path.exists():
            return None
            
        content = read_utf8(seg_path)
        
        # Split on [S1], [S2], etc.
        import re
        parts = re.split(r'\n?\[S\d+\]\n?', content)
        segments = [p.strip() for p in parts if p.strip()]
        
        return segments if segments else None


class DraftWriter:
    """Creates first drafts using LLM with various modes."""
    
    def __init__(self, source_loader: SourceLoader, test_mode: bool = False):
        self.source_loader = source_loader
        self.test_mode = test_mode
        self.prompt_builder = PromptBuilder()
        self.llm_client = get_llm_client(test_mode=test_mode)
        self.max_retries = 3
        self.retry_delay = 2.0
    
    def create_first_draft(self,
                          text: str,
                          chap_id: str,
                          voice_spec: str,
                          persona: Optional[str] = None,
                          prev_final: Optional[str] = None,
                          target_words: Optional[int] = None,
                          target_ratio: float = 1.0,
                          sample_words: Optional[int] = None,
                          segmented: bool = False,
                          chunk_size: int = 250,
                          model: str = "claude-opus-4-20250514",
                          temperature: float = 0.7,
                          output_dir: Optional[pathlib.Path] = None) -> str:
        """Create a first draft of a chapter.
        
        Args:
            text: Raw source text
            chap_id: Chapter identifier
            voice_spec: Voice specification markdown
            persona: Optional persona name
            prev_final: Previous final chapter for consistency
            target_words: Target word count (overrides target_ratio)
            target_ratio: Target length as ratio of source
            sample_words: If set, truncate to first N words (for auditions)
            segmented: Use segmented draft mode
            chunk_size: Words per segment in segmented mode
            model: LLM model to use
            temperature: Temperature for LLM generation
            output_dir: Optional output directory for logging prompts alongside outputs
            
        Returns:
            Generated draft text
        """
        # Handle sample truncation
        working_text = text
        if sample_words:
            words = text.split()
            if len(words) > sample_words:
                working_text = " ".join(words[:sample_words])
                log.info(f"Truncated to {sample_words} words for audition")
        
        # Calculate target length
        source_words = smart_estimate_words(working_text)
        if not target_words:
            target_words = int(source_words * target_ratio)
        
        length_hint = create_length_hint(target_words)
        
        # Extract raw ending for alignment
        raw_ending = self._extract_ending(working_text, 60)
        
        # Build prompt based on mode
        if segmented:
            segments = self._create_segments(working_text, chunk_size)
            log.info(f"Using segmented mode with {len(segments)} segments")
            
            # Get writer template path - default to segmented_draft.prompt if not specified
            template_path = os.environ.get("WRITER_PROMPT_TEMPLATE", 
                                         "config/writer_specs/defaults/segmented_draft.prompt")
            if not os.path.exists(template_path):
                raise FileNotFoundError(f"Template file not found: {template_path}")
            
            messages = self.prompt_builder.build_segment_author_prompt(
                raw_segments=segments,
                voice_spec=voice_spec,
                length_hint=length_hint,
                persona=persona,
                raw_ending=raw_ending,
                target_words=target_words,
                template_path=template_path
            )
        else:
            # Standard mode
            messages = self.prompt_builder.build_author_prompt(
                source=working_text,
                voice_spec=voice_spec,
                length_hint=length_hint,
                prev_final=prev_final,
                persona=persona,
                include_raw=True,
                raw_ending=raw_ending
            )
        
        # Log prompt
        self._log_prompt(messages, chap_id, persona, output_dir)
        
        # Generate draft with retries
        log.info(f"Generating draft for {chap_id}")
        draft = self._generate_with_retries(messages, model, temperature)
        log.info(f"Draft generated, length before cleaning: {len(draft)} chars")
        
        # Clean the output
        draft = self._clean_draft_output(draft)
        log.info(f"Draft cleaned, length after cleaning: {len(draft)} chars")
        
        # Validate length
        draft_words = smart_estimate_words(draft)
        log.info(f"Generated {draft_words} words (target: {target_words})")
        
        return draft
    
    def _create_segments(self, text: str, chunk_size: int) -> List[str]:
        """Split text into segments of approximately chunk_size words."""
        words = text.split()
        segments = []
        
        i = 0
        while i < len(words):
            # Take chunk_size words
            chunk_words = words[i:i + chunk_size]
            
            # Find sentence boundary if possible
            chunk_text = " ".join(chunk_words)
            
            # Look ahead for sentence ending
            if i + chunk_size < len(words):
                # Look for sentence end in next 50 words
                lookahead = words[i + chunk_size:i + chunk_size + 50]
                for j, word in enumerate(lookahead):
                    chunk_text += " " + word
                    if word.endswith(('.', '!', '?', '"', '."', '!"', '?"')):
                        i += j + 1  # Advance past this sentence
                        break
            
            segments.append(chunk_text.strip())
            i += chunk_size
        
        return segments
    
    def _extract_ending(self, text: str, word_count: int) -> str:
        """Extract the last N words from text."""
        words = text.split()
        if len(words) <= word_count:
            return text
        return " ".join(words[-word_count:])
    
    def _generate_with_retries(self, messages: List[dict], model: str, temperature: float) -> str:
        """Generate draft with retry logic."""
        for attempt in range(self.max_retries):
            try:
                log.info(f"Attempting LLM call (attempt {attempt + 1}/{self.max_retries})")
                response = self.llm_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=8000
                )
                
                # Extract content from response
                if hasattr(response, 'choices') and response.choices:
                    choice = response.choices[0]
                    if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                        content = choice.message.content.strip()
                        log.info(f"Received response with {len(content)} characters")
                        return content
                
                raise ValueError("Unexpected response structure from LLM")
                
            except Exception as e:
                log.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                else:
                    raise
    
    def _clean_draft_output(self, draft: str) -> str:
        """Clean common LLM output artifacts."""
        # Remove common preambles
        preambles = [
            "Here is the draft:",
            "Here is the revised draft:",
            "Here's the draft:",
            "I'll rewrite this chapter",
            "I'll create a draft",
            "Let me rewrite",
        ]
        
        for preamble in preambles:
            if draft.strip().startswith(preamble):
                draft = draft[len(preamble):].strip()
        
        # Don't call clean_json_text - it expects List[dict], not str
        # Just return the cleaned draft
        return draft.strip()
    
    def _log_prompt(self, messages: List[dict], chap_id: str, persona: Optional[str], output_dir: Optional[pathlib.Path] = None) -> None:
        """Log the prompt to logs/prompts directory and optionally to output directory.
        
        Args:
            messages: The prompt messages
            chap_id: Chapter identifier
            persona: Optional persona name
            output_dir: Optional output directory to also save the prompt
        """
        # Always log to the central logs directory
        log_dir = pathlib.Path("logs/prompts")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        persona_tag = f"_{persona}" if persona else ""
        filename = f"{chap_id}{persona_tag}_{timestamp}.json"
        
        log_data = {
            "timestamp": timestamp,
            "chapter": chap_id,
            "persona": persona,
            "messages": messages
        }
        
        # Save to central logs
        with open(log_dir / filename, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        
        # Also save to output directory if provided
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            prompt_filename = f"prompt_{chap_id}_{timestamp}.json"
            with open(output_dir / prompt_filename, "w", encoding="utf-8") as f:
                json.dump(log_data, f, indent=2, ensure_ascii=False)
            log.debug(f"Prompt also saved to output directory: {output_dir / prompt_filename}") 