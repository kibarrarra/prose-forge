"""
prompts.py - Prompt building logic for writing tasks

This module handles the creation of prompts for:
- First draft creation
- Segmented draft creation  
- Revision based on feedback
"""

import os
import textwrap
from typing import List, Dict, Optional
from scripts.utils.text_processing import escape_for_fstring


class PromptBuilder:
    """Builds prompts for various writing tasks."""
    
    def build_author_prompt(self, source: str, voice_spec: str, length_hint: str,
                            prev_final: Optional[str], persona: Optional[str],
                            include_raw: bool = True,
                            raw_ending: Optional[str] = None,
                            template_path: Optional[str] = None) -> List[Dict[str, str]]:
        """Compose prompt for the LLM to create or revise a draft.

        Args:
            source: Raw source text
            voice_spec: Voice specification markdown
            length_hint: Guidance on target length
            prev_final: Previous final draft (if revising)
            persona: Optional persona name
            include_raw: If False, omit the RAW SOURCE block
            raw_ending: Last ~60 words of raw text for ending alignment
            template_path: Path to template file (defaults to standard_default.prompt)

        Returns:
            List of message dictionaries for LLM API
        """
        # Use template if provided, otherwise use default
        if not template_path:
            template_path = os.environ.get("STANDARD_PROMPT_TEMPLATE",
                                         "config/writer_specs/defaults/standard_draft.prompt")
        
        # Read template
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        
        # Build sections
        persona_note = f" as {persona}" if persona else ""
        
        raw_source_section = ""
        if include_raw:
            raw_source_section = f"RAW SOURCE:\n{source}"
        
        prev_final_section = ""
        if prev_final:
            prev_final_section = f"PREVIOUS FINAL CHAPTER:\n{prev_final}"
        
        raw_ending_section = ""
        if raw_ending:
            raw_ending_section = textwrap.dedent(f"""\
                RAW ENDING (last ≈60 words):
                ---------------------------
                {raw_ending}

                Do NOT add any interpretation, foreshadowing, or sense of closure
                that is absent in the RAW ENDING. Maintain its exact tone and
                level of uncertainty or suspense.""")
        
        # Prepare variables
        variables = {
            "persona_note": persona_note,
            "length_hint": length_hint,
            "voice_spec": voice_spec,
            "raw_source_section": raw_source_section,
            "prev_final_section": prev_final_section,
            "raw_ending_section": raw_ending_section
        }
        
        # Substitute variables
        content = self._substitute(template, variables)
        
        # Split into system and user parts
        if "USER:" in content:
            system_part, user_part = content.split("USER:", 1)
            system_part = system_part.replace("SYSTEM:", "", 1).strip()
            user_part = user_part.strip()
        else:
            system_part = content.strip()
            user_part = ""
        
        return [
            {"role": "system", "content": system_part},
            {"role": "user", "content": user_part}
        ]
    
    def build_segment_author_prompt(self,
                                    raw_segments: List[str],
                                    voice_spec: str,
                                    length_hint: str,
                                    persona: Optional[str],
                                    raw_ending: str,
                                    target_words: int,
                                    template_path: str) -> List[Dict[str, str]]:
        """Build prompt for segmented first draft creation using a template file.
        
        Args:
            raw_segments: List of raw text segments
            voice_spec: Voice specification markdown
            length_hint: Guidance on target length
            persona: Optional persona name
            raw_ending: Last ~60 words of raw text
            target_words: Target word count for the chapter
            template_path: Path to the prompt template file
            
        Returns:
            List of message dictionaries for LLM API
        """
        # Read the template file
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        
        # Delegate to the template-based method
        return self.build_segment_prompt_from_template(
            raw_segments=raw_segments,
            voice_spec=voice_spec,
            length_hint=length_hint,
            persona=persona,
            raw_ending=raw_ending,
            target_words=target_words,
            template=template
        )
    
    def build_segment_prompt_from_template(self,
                                           raw_segments: List[str],
                                           voice_spec: str,
                                           length_hint: str,
                                           persona: Optional[str],
                                           raw_ending: str,
                                           target_words: int,
                                           template: str) -> List[Dict[str, str]]:
        """Build a segment prompt from a string template with placeholders.
        
        This is the preferred method for experiments using external templates
        like baseline.prompt or baseline_2.prompt.
        
        Args:
            template: Template string with placeholders like {voice_spec}, {segments}, etc.
                     Should contain SYSTEM: and USER: sections
        """
        persona_note = f" as {persona}" if persona else ""

        labelled = [f"[S{i}]\n{seg}" for i, seg in enumerate(raw_segments, 1)]

        variables = {
            "voice_spec": voice_spec,
            "length_hint": length_hint,
            "persona_note": persona_note,
            "segment_count": len(raw_segments),
            "segments": "\n\n".join(labelled),
            "raw_ending": raw_ending,
            "target_words": target_words,
        }

        content = self._substitute(template, variables)

        if "USER:" in content:
            system_part, user_part = content.split("USER:", 1)
            system_part = system_part.replace("SYSTEM:", "", 1).strip()
            user_part = user_part.strip()
        else:
            system_part = content.strip()
            user_part = ""

        return [
            {"role": "system", "content": system_part},
            {"role": "user", "content": user_part},
        ]
    
    def build_revision_prompt(self, 
                              current: str, 
                              change_list: dict, 
                              voice_spec: str, 
                              raw_ending: Optional[str] = None,
                              template_path: Optional[str] = None) -> List[Dict[str, str]]:
        """Build prompt for revising a draft based on editor feedback.
        
        Args:
            current: Current draft text
            change_list: Dictionary of required and nice-to-have changes
            voice_spec: Voice specification markdown
            raw_ending: Last ~60 words of raw text for ending alignment
            template_path: Path to revision template file (defaults to revision_default.prompt)
            
        Returns:
            List of message dictionaries for LLM API
        """
        # Use template if provided, otherwise use default
        if not template_path:
            template_path = os.environ.get("REVISION_PROMPT_TEMPLATE",
                                         "config/writer_specs/defaults/revision.prompt")
        
        # Read template
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        
        # Build raw ending section if provided
        raw_ending_section = ""
        if raw_ending:
            raw_ending_section = textwrap.dedent(f"""\
RAW ENDING (last ≈60 words):
---------------------------
{raw_ending}
---------------------------
Do NOT add any interpretation, foreshadowing, or sense of closure
that is absent in the RAW ENDING. Maintain its exact tone and
level of uncertainty or suspense.""")
        
        # Prepare variables
        variables = {
            "voice_spec": voice_spec,
            "current_draft": current,
            "change_list": self._format_json(change_list),
            "raw_ending_section": raw_ending_section
        }
        
        # Substitute variables
        content = self._substitute(template, variables)
        
        # Split into system and user parts
        if "USER:" in content:
            system_part, user_part = content.split("USER:", 1)
            system_part = system_part.replace("SYSTEM:", "", 1).strip()
            user_part = user_part.strip()
        else:
            system_part = content.strip()
            user_part = ""
        
        return [
            {"role": "system", "content": system_part},
            {"role": "user", "content": user_part}
        ]
    
    @staticmethod
    def _substitute(text: str, variables: dict) -> str:
        """Replace {placeholders} in text using variables."""
        for k, v in variables.items():
            # Ensure values are properly escaped for f-strings when they contain backslashes
            if isinstance(v, str):
                v = escape_for_fstring(v)
            text = text.replace(f"{{{k}}}", str(v))
        return text
    
    @staticmethod
    def _format_json(obj: dict) -> str:
        """Format a dictionary as JSON for inclusion in prompts."""
        import json
        return json.dumps(obj, indent=2, ensure_ascii=False) 