"""
critics.py - Literary critic simulation and scoring systems

This module handles:
- Critic system prompts and personas
- Scoring rubrics and criteria
- Feedback generation and analysis
"""

from typing import Dict, List, Any
from utils.llm_client import get_llm_client

# Global constants for scoring rubrics and prompts
SCORING_CRITERIA = [
    "Clarity & readability",
    "Tone & atmosphere", 
    "Fidelity to original plot points",
    "Fidelity to original intended tone",
    "Overall literary quality"
]

CRITIC_SYSTEM_PROMPT = """You are a simulation of two literary critics (Critic A and Critic B) discussing prose drafts.

Critic A focuses on technical writing quality, clarity, and structure.
Critic B focuses on creative elements, atmosphere, and storytelling.

Respond in the format of a conversation between these two critics."""

MODEL = "gpt-4o-mini"   # cheap for discussion

def get_scoring_rubric(context: str = "comparison") -> str:
    """Generate a standardized scoring rubric for critics."""
    if context == "comparison":
        instruction = "Each critic should first independently evaluate the texts on:"
        format_instruction = """For each version:
        - Give the five numeric scores above.
        - Briefly justify each score (≤ 30 words).
        - Highlight most effective elements (≤ 2 bullets).
        
        After individual evaluations, discuss the relative merits of each version. Conclude with a summary paragraph naming which version works best overall and why.
        
        Format your response as a conversation:
        
        CRITIC A: [evaluation of first version]
        
        CRITIC B: [evaluation of first version]
        
        [Continue for all versions, then discussion]
        
        FINAL CONSENSUS: [which version is best and why]"""
    else:  # ranking context
        instruction = "For each draft, provide:"
        format_instruction = """Each critic should evaluate each draft first. Then, have a brief discussion about the drafts.
Finally, reach a consensus on the rankings.

**CRITICAL**: Your response must end with structured data in the following JSON format:

```json
{
  "table": [
    {"rank": 1, "id": "DRAFT_[persona name]", "clarity": 9, "tone": 8, "plot_fidelity": 9, "tone_fidelity": 8, "overall": 9},
    {"rank": 2, "id": "DRAFT_[persona name]", "clarity": 7, "tone": 8, "plot_fidelity": 8, "tone_fidelity": 7, "overall": 8}
  ],
  "analysis": "Why the top draft is best...",
  "feedback": {
    "DRAFT_[persona name]": "Feedback for second place...",
    "DRAFT_[persona name]": "Feedback for third place..."
  }
}
```"""
    
    criteria_list = "\n".join(f"{i+1}. {criteria} — score 1-10" for i, criteria in enumerate(SCORING_CRITERIA))
    
    return f"""As literary critics, provide an *objective evaluation* of the following prose drafts.

{instruction}
{criteria_list}

{format_instruction}"""

def get_comparison_feedback(comparison_text: str, versions: List[str], chapters: List[str], original_texts: Dict[str, str] = None) -> Dict[str, Any]:
    """Get feedback from critics based on comparison text in a single prompt."""
    client = get_llm_client()
    
    # Build the full comparison text with original context if available
    full_comparison_text = comparison_text
    
    # Add original text context if provided
    if original_texts:
        original_context = "\n\n=== ORIGINAL SOURCE TEXTS FOR REFERENCE ===\n"
        for chapter_id, original_text in original_texts.items():
            if original_text:  # Only add if we have original text
                original_context += f"\nOriginal {chapter_id}:\n{original_text}\n"
        original_context += "\n=== END ORIGINAL TEXTS ===\n\n"
        full_comparison_text = original_context + comparison_text
    
    # Get the standardized rubric
    rubric = get_scoring_rubric("comparison")
    
    # Use a single prompt to get the critics' discussion
    result = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
            {"role": "user", "content": f"{rubric}\n\n{full_comparison_text}"}
        ],
        temperature=0.2
    )
    
    discussion = result.choices[0].message.content.strip()
    
    # Extract critic summaries (for backward compatibility)
    # Try to split between critics A and B first evaluations
    parts = discussion.split("CRITIC B:")
    critic_A_summary = parts[0].replace("CRITIC A:", "").strip() if len(parts) > 1 else discussion
    
    # Try to get Critic B's first evaluation
    critic_B_parts = parts[1].split("CRITIC A:") if len(parts) > 1 else []
    critic_B_summary = critic_B_parts[0].strip() if critic_B_parts else ""
    
    return {
        "critic_A_summary": critic_A_summary,
        "critic_B_summary": critic_B_summary,
        "discussion_transcript": discussion,
        "versions": versions,
        "chapters": chapters
    }

def chat(system: str, user: str) -> str:
    """Simple chat interface for critic interactions."""
    client = get_llm_client()
    res = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}]
    )
    return res.choices[0].message.content.strip() 