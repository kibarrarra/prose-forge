"""
revision.py - Draft revision logic based on editor feedback

This module handles:
- Loading and validating editor feedback
- Applying revisions to existing drafts
- Validating revision changes
"""

import json
import pathlib
from typing import Dict, List, Optional, Any
from scripts.utils.io_helpers import read_utf8
from scripts.utils.text_processing import smart_estimate_words
from scripts.utils.logging_helper import get_logger
from scripts.utils.llm_client import get_llm_client
from scripts.core.writing.prompts import PromptBuilder

log = get_logger()


class RevisionHandler:
    """Handles draft revisions based on editor feedback."""
    
    def __init__(self, source_loader, test_mode: bool = False):
        self.source_loader = source_loader
        self.test_mode = test_mode
        self.prompt_builder = PromptBuilder()
        self.llm_client = get_llm_client(test_mode=test_mode)
    
    def load_feedback(self, feedback_path: pathlib.Path) -> Dict[str, Any]:
        """Load and validate editor feedback from JSON file.
        
        Args:
            feedback_path: Path to the feedback JSON file
            
        Returns:
            Feedback dictionary
            
        Raises:
            ValueError: If feedback is invalid or missing required fields
        """
        if not feedback_path.exists():
            raise ValueError(f"Feedback file not found: {feedback_path}")
        
        try:
            with open(feedback_path, 'r', encoding='utf-8') as f:
                feedback = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in feedback file: {e}")
        
        # Validate required fields
        if not isinstance(feedback, dict):
            raise ValueError("Feedback must be a JSON object")
        
        if 'must' not in feedback and 'nice' not in feedback:
            raise ValueError("Feedback must contain 'must' and/or 'nice' lists")
        
        # Ensure lists exist
        feedback.setdefault('must', [])
        feedback.setdefault('nice', [])
        
        # Validate list types
        if not isinstance(feedback['must'], list):
            raise ValueError("'must' field must be a list")
        if not isinstance(feedback['nice'], list):
            raise ValueError("'nice' field must be a list")
        
        return feedback
    
    def revise_draft(self,
                     current_draft: str,
                     feedback: Dict[str, Any],
                     voice_spec: str,
                     chap_id: str,
                     model: str = "claude-opus-4-20250514",
                     temperature: float = 0.3) -> str:
        """Apply revisions to a draft based on feedback.
        
        Args:
            current_draft: The current draft text
            feedback: Editor feedback dictionary with 'must' and 'nice' lists
            voice_spec: Voice specification markdown
            chap_id: Chapter identifier
            model: LLM model to use
            temperature: Temperature for the LLM
            
        Returns:
            Revised draft text
        """
        # Extract raw ending if available
        raw_ending = self._get_raw_ending(chap_id)
        
        # Build revision prompt
        messages = self.prompt_builder.build_revision_prompt(
            current=current_draft,
            change_list=feedback,
            voice_spec=voice_spec,
            raw_ending=raw_ending
        )
        
        # Log the revision attempt
        log.info(f"Revising {chap_id} with {len(feedback.get('must', []))} must-have changes "
                 f"and {len(feedback.get('nice', []))} nice-to-have changes")
        
        # Generate revision
        revised = self._generate_revision(messages, model, temperature)
        
        # Clean output
        revised = self._clean_revision_output(revised)
        
        return revised
    
    def validate_revision(self,
                          original: str,
                          revised: str,
                          feedback: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that a revision meets requirements.
        
        Args:
            original: Original draft text
            revised: Revised draft text
            feedback: Editor feedback that was applied
            
        Returns:
            Dictionary with validation results and any warnings
        """
        results = {
            "word_count_change": 0,
            "percent_change": 0.0,
            "warnings": [],
            "must_changes_count": len(feedback.get('must', [])),
            "nice_changes_count": len(feedback.get('nice', []))
        }
        
        # Check word count
        original_words = smart_estimate_words(original)
        revised_words = smart_estimate_words(revised)
        
        results["word_count_change"] = revised_words - original_words
        results["percent_change"] = (results["word_count_change"] / original_words * 100) if original_words > 0 else 0
        
        # Warn if word count changed significantly (>10%)
        if abs(results["percent_change"]) > 10:
            results["warnings"].append(
                f"Word count changed by {results['percent_change']:.1f}% "
                f"({original_words} → {revised_words} words)"
            )
        
        # Check that ending hasn't changed dramatically
        original_ending = self._extract_ending(original, 50)
        revised_ending = self._extract_ending(revised, 50)
        
        if self._endings_differ_significantly(original_ending, revised_ending):
            results["warnings"].append(
                "The ending appears to have changed significantly. "
                "Ensure it still matches the raw ending beat."
            )
        
        return results
    
    def _get_raw_ending(self, chap_id: str) -> Optional[str]:
        """Get the raw ending for a chapter if available."""
        try:
            # Try to load from the source loader
            if hasattr(self.source_loader, 'raw_dir'):
                json_path = self.source_loader.raw_dir / f"{chap_id}.json"
                if json_path.exists():
                    raw_text, _ = self.source_loader.load_raw_text(json_path)
                    return self._extract_ending(raw_text, 60)
        except Exception as e:
            log.debug(f"Could not load raw ending for {chap_id}: {e}")
        
        return None
    
    def _generate_revision(self, messages: List[dict], model: str, temperature: float) -> str:
        """Generate revision using LLM."""
        max_retries = 3
        retry_delay = 2.0
        
        for attempt in range(max_retries):
            try:
                response = self.llm_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=8000
                )
                
                # Extract content
                if hasattr(response, 'choices') and response.choices:
                    choice = response.choices[0]
                    if hasattr(choice, 'message') and hasattr(choice.message, 'content'):
                        return choice.message.content.strip()
                
                raise ValueError("Unexpected response structure from LLM")
                
            except Exception as e:
                log.warning(f"Revision attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay * (2 ** attempt))
                else:
                    raise
    
    def _clean_revision_output(self, text: str) -> str:
        """Clean common artifacts from revision output."""
        # Remove common preambles
        preambles = [
            "Here is the revised draft:",
            "Here's the revised version:",
            "I'll revise the draft",
            "Let me apply the changes",
            "Applying the requested changes:",
            "FINAL:",
            "Final draft:",
        ]
        
        for preamble in preambles:
            if text.strip().startswith(preamble):
                text = text[len(preamble):].strip()
        
        return text.strip()
    
    def _extract_ending(self, text: str, word_count: int) -> str:
        """Extract the last N words from text."""
        words = text.split()
        if len(words) <= word_count:
            return text
        return " ".join(words[-word_count:])
    
    def _endings_differ_significantly(self, ending1: str, ending2: str) -> bool:
        """Check if two endings differ significantly."""
        # Simple heuristic: check if the last sentence is dramatically different
        # This is a basic check - could be made more sophisticated
        
        # Get last sentences
        def get_last_sentence(text: str) -> str:
            sentences = text.replace('!', '.').replace('?', '.').split('.')
            sentences = [s.strip() for s in sentences if s.strip()]
            return sentences[-1] if sentences else ""
        
        last1 = get_last_sentence(ending1).lower()
        last2 = get_last_sentence(ending2).lower()
        
        # Check for significant differences
        if len(last1) == 0 or len(last2) == 0:
            return True
        
        # Simple word overlap check
        words1 = set(last1.split())
        words2 = set(last2.split())
        
        if not words1 or not words2:
            return True
            
        overlap = len(words1.intersection(words2))
        total = len(words1.union(words2))
        
        # If less than 50% word overlap, consider it significantly different
        return (overlap / total) < 0.5 if total > 0 else True 