# Writer Prompt Templates

This directory contains prompt templates for the prose-forge writing system.

## Directory Structure

### `/defaults/`
System default prompts used when no specific template is provided:
- `segmented_draft.prompt` - Default template for segmented first draft creation
- `standard_draft.prompt` - Default template for standard (non-segmented) drafts
- `revision.prompt` - Default template for revisions based on editor feedback

### Experimental Templates
Your custom experimental prompts:
- `baseline.prompt` - Your baseline segmented draft template
- `baseline_2.prompt` - Your second baseline variant
- `simplified.prompt` - Your simplified prompt template

## Usage

Templates can be specified via:
1. Environment variables:
   - `WRITER_PROMPT_TEMPLATE` - For segmented drafts
   - `STANDARD_PROMPT_TEMPLATE` - For standard drafts
   - `REVISION_PROMPT_TEMPLATE` - For revisions

2. In experiments.yaml, specify the template path in the `writer_spec` field

## Template Format

Templates use placeholders in `{curly_braces}` that get substituted at runtime.

Templates should contain:
- `SYSTEM:` section for system prompt
- `USER:` section for user prompt
- Placeholders for dynamic content

Common placeholders:
- `{voice_spec}` - The voice specification
- `{segments}` - Labeled segments for segmented mode
- `{raw_ending}` - Last ~60 words of source
- `{target_words}` - Target word count
- `{persona_note}` - Persona name if specified
- `{length_hint}` - Length guidance 