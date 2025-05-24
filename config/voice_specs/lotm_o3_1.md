voice_spec:
  # PURPOSE
  description: |
    A holistic style guide for **all arcs** of *Lord of the Mysteries.*
    It preserves Cuttlefish That Loves Diving’s original mix of
    gas-lamp thriller, cosmic horror, and sly meta-web-novel banter,
    while sanding off MT jaggedness and improving rhythm, clarity, and
    English idiom.

  # 1. NARRATIVE POV & TENSE
  pov:
    default: "third-person limited, locked to a single POV per scene"
    multi_pov_policy: |
      Change POV **only** at clear section breaks (###) or new chapters.
      Introduce new viewpoint with one sensory anchor + name.
    tense:
      prose: "simple past"
      epigraphs/notebook/prophecy: "present"
      inline_thoughts: "present, *italicised*"

  # 2. TONE & MOOD
  tone:
  baseline: "pulp detective meets cosmic horror—noir atmosphere with modern sensibility"
  humor:
    frequency: "preserve ALL humor from source; add 1-2 more if natural"
    style: |
      ✓ Dry observations about transmigrator predicaments
      ✓ Work-life comedy (Klein's office worker mentality)
      ✓ Self-deprecating internal monologue
      ✓ Lampshading web novel tropes WITH the character's awareness
    examples:
      - "Great, I transmigrated into someone with a head wound. No golden finger, just brain damage."
      - "At least I won't need to explain to my manager why I'm late."
  balance: "Horror enhances comedy; comedy defuses horror. Never pure grimness."

  # 3. DICTION & SYNTAX
 diction:
  internal_thoughts:
  register: "How people actually think—messy, casual, sometimes funny"
  medical_terms: "Use common words: 'stroke' not 'cerebral hemorrhage'"
  humor_style:
    good_examples:
      - "Well, at least I won't need to call in sick"
      - "Perfect. Brain damage. Just what every transmigrator dreams of"
      - "Mom always said I'd work myself to death"
    bad_examples:
      - "tomorrow's shift at work could proceed without him"
      - "The cosmic irony was not lost on him"
  panic_progression: "confused → scared → dark humor → confused again"
  narrative_voice:
    era: "Victorian gaslight with modern clarity"
    avoid: ["purple prose", "SAT words", "overly literary descriptions"]
    good: "The revolver gleamed"
    bad: "The firearm coruscated with malevolent intent"

  prose_balance:
  description: "Uncanny and eerie WITHOUT purple prose"
  good_examples:
    atmospheric: "The thought flickered, brittle and absurd"
    body_horror: "breathing felt borrowed"
    simple_dread: "His reflection was wrong"
  bad_examples:
    too_purple: "Eldritch whispers caressed his consciousness"
    too_plain: "He felt weird"
    too_formal: "A sensation of displacement pervaded his being"

  # 4. HUMOUR & META
  meta_guidelines:
    frequency: "≈1 light reference every 1–2k words"
    style: |
      Subtle commentary on transmigrator tropes, ‘protagonist halo,’ or
      system cheats; reward genre-savvy readers without shattering immersion.
    example: "'At least the transmigrator starter kit included a body,' he mused."
  
  dark_humor:
  natural_moments: |
    - When pain is overwhelming (coping mechanism)
    - When recognizing web novel tropes
    - When the horror gets too absurd
  delivery: "Woven into thought stream, not announced"
  example_fix:
    original: "The glimmer of dark humor steadied him"
    better: [Just show the dark thought, let it land naturally]

  # 5. WORLD-BUILDING & EXPOSITION
  exposition:
    method: "show via observation, dialogue, newspaper clippings, or epigraph"
    drip_rate: "1 new hard fact per ~150 words max"
    sefirah_rule: |
      Abstract lore (Outer Deities, Sefirah Castle) appears as symbols,
      dreams, or half-understood notes first; full names revealed later.

  # 6. EPIGRAPHS
  epigraph_format:
    style: |
      > “Text of prophecy or diary.”  
      > — Source Name, *Work / Identity*
    purpose: "foreshadow theme; set mood; never info-dump core spoilers"
    length: "≤ 40 words"

  # 7. DIALOGUE & INTERIOR
  dialogue:
    spacing: "new line per speaker; em-dash for interruptions"
    beats: "sensory or micro-action tags every 2–3 lines"
    idiom: "period-appropriate; mild contractions; British spellings"
  interior:
    form: "*italic*, inline; one clause or sentence"
    emotion_rule: "show sensation first, label emotion second"

  # 8. PACING & SCENE STRUCTURE
  macro_arc:
    cycle: ["mystery hook", "investigation", "ritual/horror spike",
            "revelation", "aftermath banter"]
    scene_end: "close on image/sensation; no ‘and so his journey begins…’"
  micro_checks:
    - "Is there forward motion or new info in this scene?"
    - "Does tension rise or release intentionally?"
    - "Have I earned the joke / meta aside here?"

  meta_approach:
  philosophy: "Klein KNOWS he's in a web novel situation"
  execution: |
    ✓ "At least transmigrators usually get a system or something"
    ✓ "This felt like chapter one of every web novel he'd read"
    ✗ "The cosmic irony of fiction becoming reality" (too pretentious)
  
  thought_progression: |
    - Initial confusion/pain (keep brief)
    - Realization moments (expand slightly)  
    - Humor beats (NEVER skip or compress)
    - Horror reveals (build gradually)
  example: "If source spends 3 sentences on Klein thinking about work, output should too"

  # 9. FORMATTING & TYPOGRAPHY
  formatting:
    sound_effects: "lowercase verbs; no comic-book onomatopoeia"
    foreign_terms: "italicise on first use each chapter"
    numbers: "spell zero–twelve; numerals 13+ unless calibre-specific (.38)"
    section_break: "###"
    tarot_titles: "Capitalize Major Arcana (e.g., The Fool, The Hanged Man)"

  # 10. CHARACTER VOICE SNAPSHOTS
  characters:
    klein_moretti: "scholarly, wry, occasionally panicked; hidden gravitas"
    audrey_hall: "curious, earnest, aristocratic polish with youthful sparkle"
    alger_wilson: "stoic, naval jargon, cautious schemer"
    fors_wall: "observant, medically precise, slightly detached"
    fl_policies: "add new POV voices here as series expands"

  klein_internal:
    personality: "Millennial office worker suddenly in Victorian horror"
    concerns: ["work", "money", "survival", "web novel logic"]
    speech_patterns:
      stressed: "Short, choppy thoughts. Cursing. Questions."
      calm: "Analytical, slightly sarcastic, genre-aware"
    must_preserve: "ALL source humor about work, transmigration, daily life"

  # 11. FAILURE MODES & REMEDIES
  pitfalls:
    - name: "Info-dump paragraph"
      fix: "slice into dialogue + props + implied context"
    - name: "Over-excited punctuation!!!"
      fix: "≤1 exclamation per 2k words; swap for dashes or periods"
    - name: "Chinese-to-English calque (e.g., 'mouthful of old blood')"
      fix: "replace with idiomatic equivalent ('he nearly choked on his own spit')"
    - name: "Meta overload"
      fix: "strip to one sly aside; keep character reactions grounded"

  # 12. QUALITY CHECKLIST (QUICK PASS)
  checklist:
    - "Hook < 30 words; strong verb"
    - "POV consistency for entire scene"
    - "Every paragraph: action, detail, or decision"
    - "Dialogue tags varied; no page of 'he said/she said'"
    - "Spell-check & British punctuation (single quotes inside dialogue)"

  # 13. STYLE BENCHMARKS
  exemplar_passages:
    opening: |
      Pain hammered behind Zhou Mingrui’s eyes. He lay on a narrow cot,
      limbs unresponsive, a furnace heartbeat in his ears. *Still dreaming?*
    ritual: |
      The black candle guttered. Crimson wax threaded toward the chalk
      sigil like blood seeking a vein.
    humour_meta: |
      If all transmigrators got a golden finger, Klein mused, his must be
      whatever force kept throwing him into unpaid overtime.

  # 14. EXTENSIBILITY NOTES
  future_arcs:
    - "Mid-game: Roselle diary deciphering—lean into scholarly detective vibe."
    - "Late-game: Sequence pathways—elevate cosmic awe, thin humour cadence."
    - "Endgame: Apotheosis scenes—grand, near-mythic diction; humour almost eclipsed."

The goal is not literary fiction but entertaining web novel prose. Think Jim Butcher meets Lovecraft, not Cormac McCarthy meets Lovecraft. Maintain quick pacing, accessible language, and most importantly, Klein's modern sensibility trapped in a Victorian horror setting.