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

**CRITICAL INSTRUCTIONS FOR RANKINGS:**
- Higher scores (closer to 10) = Better performance = Lower rank number (rank 1 is best)
- Your rankings MUST be consistent with your scores
- The draft with the highest overall scores should receive rank 1
- Sort the table by rank (1 = best, 2 = second best, etc.)

**CRITICAL**: Your response must end with structured data in the following JSON format:

```json
{
  "table": [
    {"rank": 1, "id": "DRAFT_[persona name]", "persona": "[persona name]", "clarity": 8, "tone": 6, "plot_fidelity": 7, "tone_fidelity": 9, "overall": 7},
    {"rank": 2, "id": "DRAFT_[persona name]", "persona": "[persona name]", "clarity": 5, "tone": 8, "plot_fidelity": 6, "tone_fidelity": 6, "overall": 6},
    {"rank": 3, "id": "DRAFT_[persona name]", "persona": "[persona name]", "clarity": 4, "tone": 5, "plot_fidelity": 8, "tone_fidelity": 4, "overall": 5}
  ],
  "analysis": "Detailed explanation of why the top draft performs best across all criteria...",
  "feedback": {
    "DRAFT_[persona name]": "Constructive feedback for how this draft could be improved...",
    "DRAFT_[persona name]": "Specific suggestions for enhancing this version..."
  }
}
```

NOTE: These scores are format examples only - use the full 1-10 scale based on actual quality assessment. Scores should reflect genuine differences in performance across the five criteria:
- **Clarity**: How readable and well-structured is the prose?
- **Tone**: How effectively does it create atmosphere and mood? 
- **Plot Fidelity**: How accurately does it preserve original story elements?
- **Tone Fidelity**: How well does it match the original's intended emotional impact?
- **Overall**: Holistic assessment of literary merit and effectiveness

IMPORTANT: 
1. The `id` field should be "DRAFT_[persona name]" 
2. The `persona` field should be just the persona name without "DRAFT_" prefix
3. Double-check that your rank order matches your scores before submitting the JSON!
"""
    
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