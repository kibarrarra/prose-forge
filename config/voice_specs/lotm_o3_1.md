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
    baseline: "tense, inquisitive, steampunk-noir with Lovecraftian awe"
    humour:
      dark_humour: "allowed; deadpan one-liners relieve tension"
      meta_jokes: |
        ✓ Light fourth-wall pokes at web-novel tropes
        ✓ Lampshade Klein’s ‘cheat’ & forum-brain moments
        ✗ No meme slang or out-of-era references
    awe_scale: "grounded unease → cosmic dread; escalate gradually"

  # 3. DICTION & SYNTAX
  diction:
    verbs: "concrete, sensory (throbbed, rasped, shimmered)"
    sentence_rhythm: "mix 5–25 word lines; short pulses in action"
    vocabulary:
      era: "19C industrial / ecclesiastical / esoteric"
      avoid: ["modern tech metaphors", "gamer skill trees", "OTT purple prose"]
    register_by_context:
      ritual: "archaic, near-biblical cadence"
      tarot_table: "measured, slightly theatrical"
      comedy_beats: "lean, sardonic"

  # 4. HUMOUR & META
  meta_guidelines:
    frequency: "≈1 light reference every 1–2k words"
    style: |
      Subtle commentary on transmigrator tropes, ‘protagonist halo,’ or
      system cheats; reward genre-savvy readers without shattering immersion.
    example: "'At least the transmigrator starter kit included a body,' he mused."

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
