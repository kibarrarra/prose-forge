#!/usr/bin/env python
"""
sanity_checker.py - Verify if a revised draft correctly implements changes.

Uses an LLM to compare the previous draft, the change list, and the new draft
to ensure:
1. All MUST edits were applied.
2. NICE edits (if applied) are reasonable.
3. No major hallucinations or unsupported plot points were introduced.
4. The narrative ending constraint (if provided) was respected.
"""
import argparse
import json
import pathlib
import textwrap
import sys
import os

from utils.io_helpers import read_utf8
from utils.logging_helper import get_logger
from utils.llm_client import get_llm_client  # Assuming shared client

log = get_logger()
MODEL = os.getenv("SANITY_CHECK_MODEL", "gpt-4o-mini") # Use a cheaper model for verification
client = get_llm_client()

def call_verifier_llm(prompt: str) -> str:
    # Basic call, add retries if needed later
    try:
        res = client.chat.completions.create(
            model=MODEL,
            temperature=0.1,  # Low temp for deterministic checking
            messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content.strip()
    except Exception as e:
        log.error("Verifier LLM call failed: %s", e)
        return "ERROR: LLM call failed."

def build_verifier_prompt(prev_draft: str, new_draft: str, change_list: dict, raw_ending: str | None) -> str:
    
    must_list = "\n".join(f"- {item}" for item in change_list.get("must", []))
    nice_list = "\n".join(f"- {item}" for item in change_list.get("nice", []))

    prompt_parts = [
        textwrap.dedent(f"""\
        You are a meticulous Sanity Checker AI. Your task is to verify if NEW DRAFT correctly implements the required changes based on PREVIOUS DRAFT and CHANGE LIST, without introducing errors.

        PREVIOUS DRAFT:
        ```
        {prev_draft}
        ```

        NEW DRAFT:
        ```
        {new_draft}
        ```

        CHANGE LIST:
        MUST apply these changes:
        {must_list if must_list else "(none)"}

        NICE-TO-HAVE (optional) changes:
        {nice_list if nice_list else "(none)"}
        """)
    ]

    if raw_ending:
        prompt_parts.append(textwrap.dedent(f"""\
        RAW ENDING CONSTRAINT:
        The final sentence must conclude on the *same narrative beat* as this:
        ```
        {raw_ending}
        ```
        Absolutely forbid introduction of foreshadowing or closure that is absent in the RAW ENDING.
        """))

    # Now replace with clearer checklist format with symbols
    prompt_parts.append(textwrap.dedent("""\
        VERIFICATION CHECKLIST:
        1. MANDATORY EDITS: ✓/✗ - Were ALL items under MUST applied in the NEW DRAFT? (Answer ✓ if all were applied, ✗ if any were missed, and list specific failures if ✗)
        2. NICE EDITS: ✓/✗/NA - If any NICE items were applied, are they reasonable and well-integrated? (Answer ✓ if good, ✗ if problematic, NA if none applied)
        3. HALLUCINATIONS/ERRORS: ✓/✗ - Is the NEW DRAFT free of factual errors or plot inconsistencies? (Answer ✓ if clean, ✗ if problems found, providing examples)
        4. ENDING BEAT: ✓/✗/NA - Does the NEW DRAFT's final sentence respect the RAW ENDING constraint? (Answer ✓ if respected, ✗ if violated)

        OUTPUT FORMAT:
        Provide your assessment based *only* on the checklist above. Start with a single line: "VERDICT: OK" or "VERDICT: ISSUES FOUND". Then list each numbered point with its ✓/✗/NA symbol first, followed by explanation. For a perfect draft, all applicable items should have ✓.
        """))

    return "\n\n".join(prompt_parts)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Verify draft revisions against a change list.")
    p.add_argument("--prev-draft", type=pathlib.Path, required=True, help="Path to the previous draft file.")
    p.add_argument("--new-draft", type=pathlib.Path, required=True, help="Path to the newly revised draft file.")
    p.add_argument("--change-list-json", type=pathlib.Path, required=True, help="Path to the JSON file containing the 'change_list' (output from editor_panel).")
    p.add_argument("--raw-context", type=pathlib.Path, help="Optional: Path to the raw context file (e.g., lotm_000x.txt) to extract the ending constraint.")
    p.add_argument("--output-status", type=pathlib.Path, help="Optional: File path to write the final verdict (OK/ISSUES FOUND).")

    return p.parse_args()

def main() -> None:
    args = parse_args()

    if not args.prev_draft.exists():
        log.error(f"Previous draft not found: {args.prev_draft}")
        sys.exit(1)
    if not args.new_draft.exists():
        log.error(f"New draft not found: {args.new_draft}")
        sys.exit(1)
    if not args.change_list_json.exists():
        log.error(f"Change list JSON not found: {args.change_list_json}")
        sys.exit(1)

    prev_draft_text = read_utf8(args.prev_draft)
    new_draft_text = read_utf8(args.new_draft)
    
    try:
        feedback_data = json.loads(read_utf8(args.change_list_json))
        change_list = feedback_data.get("change_list", {})
        if not change_list.get("must") and not change_list.get("nice"):
             log.warning("Change list JSON does not contain 'must' or 'nice' keys under 'change_list'.")
             # Proceeding anyway, checker will see empty lists
             change_list = {"must": [], "nice": []} # Ensure structure exists
    except json.JSONDecodeError:
        log.error(f"Failed to parse change list JSON: {args.change_list_json}")
        sys.exit(1)

    raw_ending_text = None
    if args.raw_context:
        if args.raw_context.exists():
            # Assuming load_raw_text exists or we implement a simpler reader here
            # For simplicity, just read the whole file and take last ~60 words
            try:
                # Need to import or define load_raw_text if used
                # from scripts.writer import load_raw_text 
                # raw_full_text, _ = load_raw_text(args.raw_context)
                # For now, simplified:
                raw_full_text = read_utf8(args.raw_context)
                raw_ending_text = " ".join(raw_full_text.split()[-60:])
            except Exception as e:
                log.warning(f"Failed to load or process raw context {args.raw_context}: {e}")
        else:
            log.warning(f"Raw context file not found: {args.raw_context}")

    log.info(f"Checking revision: {args.new_draft.name} vs {args.prev_draft.name}")
    verifier_prompt = build_verifier_prompt(prev_draft_text, new_draft_text, change_list, raw_ending_text)
    
    # For debugging: print the prompt
    # print("--- VERIFIER PROMPT ---")
    # print(verifier_prompt)
    # print("--- END PROMPT ---")

    assessment = call_verifier_llm(verifier_prompt)

    log.info("Sanity Check Assessment:\n%s", assessment)

    # Extract verdict
    verdict = "UNKNOWN"
    if assessment.startswith("VERDICT: OK"):
        verdict = "OK"
    elif assessment.startswith("VERDICT: ISSUES FOUND"):
        verdict = "ISSUES FOUND"
    elif assessment.startswith("ERROR:"):
        verdict = "ERROR"

    log.info(f"Final Verdict: {verdict}")

    if args.output_status:
        try:
            with open(args.output_status, "w", encoding="utf-8") as f:
                f.write(f"VERDICT: {verdict}\n\n")
                f.write(assessment)
            log.info(f"Full assessment written to {args.output_status}")
        except IOError as e:
            log.error(f"Failed to write assessment to {args.output_status}: {e}")

    if verdict != "OK":
        # Optionally exit with error code if issues are found
        # sys.exit(1)
        pass # Or just log


if __name__ == "__main__":
    main() 