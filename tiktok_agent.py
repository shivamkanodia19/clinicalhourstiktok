#!/usr/bin/env python3
"""
ClinicalHours TikTok Slideshow Agent v5
Deep-research powered. Retention-optimized. Screenshot-ready.

New in v5:
  - Rejection learning: rejected copy and images logged to output/rejection_log.json.
    Rejection patterns injected into future Claude and Gemini prompts automatically.
  - Image rejection: [X] Reject option in interactive mode logs + regenerates.
  - Copy rejection: [R] Rewrite now asks for reason and logs to rejection_log.json.
  - Prompt variation: layout variant randomly selected per image generation.
  - Marketing psychology principles injected into every copy prompt.
  - Conciseness rules enforced on all output fields via prompt.

New in v4:
  - Fixed Claude model to claude-sonnet-4-6 (was broken model name).
  - Removed deprecated Gemini fallback model (gemini-2.0-flash-exp-image-generation).
  - Emoji preserved in TikTok captions (no longer stripped).
  - Robust JSON parsing: extracts first {..} block, survives Claude preamble.
  - New framework: amcas-countdown (deadline-driven, Jan-June AMCAS season).
  - --variations N: generate N carousel variants with different hook angles (batch).
  - Topic dedup: warns if you have made a carousel on this topic before.
  - Visual style shown in batch copy summary.
  - Expanded ClinicalHours product context with key AMCAS numbers and mistake list.

Modes:
  Default (interactive)  Deep research -> slide-by-slide questions -> approve each image
  --batch                Deep research -> all-at-once generation
  --skip-images          Copy only: no Gemini calls (free, fast, great for testing)
  --no-research          Skip the research phase, go straight to slides
  --variations N         Batch only: generate N variants using different hook angles

Usage:
  python tiktok_agent.py
  python tiktok_agent.py --topic "premeds forget to log hours" --framework pain-hook
  python tiktok_agent.py --batch --topic "200 users zero spend" --framework social-proof
  python tiktok_agent.py --batch --topic "AMCAS deadline" --framework amcas-countdown
  python tiktok_agent.py --batch --topic "losing track of hours" --variations 3
  python tiktok_agent.py --skip-images --topic "test copy" --framework stat-drop
  python tiktok_agent.py --no-research --topic "quick test" --framework tutorial
"""

from __future__ import annotations

import os
import re
import sys
import json
import base64
import argparse
import platform
import textwrap
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict

# ── dotenv ─────────────────────────────────────────────────────────────────────

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:
    pass


# ── String safety ──────────────────────────────────────────────────────────────
# All strings sent to either API must be pure ASCII to avoid 400 errors.

_UNICODE_MAP = {
    '\u2018': "'", '\u2019': "'",
    '\u201c': '"', '\u201d': '"',
    '\u2013': '-', '\u2014': '-',
    '\u2026': '...', '\u2022': '-',
    '\u00b7': '-', '\u00a0': ' ',
    '\u00e9': 'e', '\u00e8': 'e',
    '\u00e0': 'a', '\u00fc': 'u',
}

def ascii_safe(text: str) -> str:
    if not text:
        return ''
    for char, rep in _UNICODE_MAP.items():
        text = text.replace(char, rep)
    return text.encode('ascii', 'ignore').decode('ascii')


# ── Constants ──────────────────────────────────────────────────────────────────

BASE_DIR        = Path(__file__).parent / 'output'
SCREENSHOTS_DIR = Path(__file__).parent / 'assets' / 'screenshots'
LOGO_DIR        = Path(__file__).parent / 'assets' / 'logo'
GENERATED_DIR   = Path(__file__).parent / 'assets' / 'generated'
GENERATED_STAGING_DIR = Path(__file__).parent / 'assets' / 'generated' / 'staging'
INDEX_FILE      = BASE_DIR / 'index.md'
REJECTION_LOG_FILE = BASE_DIR / 'rejection_log.json'

CLAUDE_MODEL   = 'claude-sonnet-4-6'
GEMINI_PRIMARY = 'gemini-3.1-flash-image-preview'


# ── Slide specs ────────────────────────────────────────────────────────────────
# Each entry drives one slide in the Pillow render pipeline.
# validate_deck() enforces consistency rules before any rendering starts.

SLIDE_SPECS: List[Dict] = [
    {
        "treatment":      "typography_only",
        "accent":         True,
        "device":         None,
        "tab":            None,
        "generated_asset": False,
    },
    {
        "treatment":      "app_screenshot",
        "accent":         False,
        "device":         "phone",
        "tab":            "opportunities",
        "generated_asset": False,
    },
    {
        "treatment":      "stat_callout",
        "accent":         True,
        "device":         None,
        "tab":            None,
        "generated_asset": False,
    },
    {
        "treatment":      "split_layout",
        "accent":         False,
        "device":         None,
        "tab":            None,
        "generated_asset": False,
    },
    {
        "treatment":      "color_block",
        "accent":         False,
        "device":         None,
        "tab":            None,
        "generated_asset": False,
    },
]


# ── Deck validation ────────────────────────────────────────────────────────────

def validate_deck(slide_specs: List[Dict]) -> None:
    """
    Validate SLIDE_SPECS before rendering anything.
    Raises ValueError with the failing rule and slide index on first violation.

    Rules enforced:
    1. No two consecutive slides share the same treatment.
    2. At least 2 slides must have accent=True.
    3. Slide 0 and Slide 4 cannot both be 'typography_only'.
    """
    # Rule 1: no consecutive same treatment
    for i in range(len(slide_specs) - 1):
        if slide_specs[i]["treatment"] == slide_specs[i + 1]["treatment"]:
            raise ValueError(
                f"validate_deck failed: RULE 1 — slides {i} and {i + 1} "
                f"both have treatment='{slide_specs[i]['treatment']}'. "
                "No two consecutive slides may share the same treatment."
            )

    # Rule 2: at least 2 accent=True
    accent_count = sum(1 for s in slide_specs if s.get("accent"))
    if accent_count < 2:
        raise ValueError(
            f"validate_deck failed: RULE 2 — only {accent_count} slide(s) have "
            "accent=True. At least 2 are required."
        )

    # Rule 3: slides 0 and 4 cannot both be typography_only
    if (
        slide_specs[0]["treatment"] == "typography_only"
        and slide_specs[4]["treatment"] == "typography_only"
    ):
        raise ValueError(
            "validate_deck failed: RULE 3 — slides 0 and 4 cannot both be "
            "'typography_only'. Change the treatment for slide index 0 or 4."
        )


# ── Render dispatch ────────────────────────────────────────────────────────────

def _get_render_fn(treatment: str):
    """Return the render() callable for the given treatment string."""
    if treatment == "typography_only":
        from renders.typography import render
    elif treatment == "app_screenshot":
        from renders.app_screenshot import render
    elif treatment == "color_block":
        from renders.color_block import render
    elif treatment == "stat_callout":
        from renders.stat_callout import render
    elif treatment == "split_layout":
        from renders.split_layout import render
    else:
        raise NotImplementedError(
            f"Unknown treatment: '{treatment}'. "
            "Valid values: typography_only, app_screenshot, color_block, "
            "stat_callout, split_layout."
        )
    return render


# ── Render pipeline orchestrator ───────────────────────────────────────────────

def run_render_pipeline(slides_copy: List[Dict], output_dir: Optional[Path] = None) -> None:
    """
    Run the full Pillow render pipeline against SLIDE_SPECS.

    1. Validates the deck (raises on bad config).
    2. For each spec, calls generate_asset() if generated_asset=True,
       then checks assets/generated/ for the approved asset.
    3. Calls the appropriate render(spec, copy, output_path) function.
    4. Saves slide_01.png … slide_05.png to output_dir (default: /output/).
    5. Prints one summary line per slide.
    """
    if output_dir is None:
        output_dir = BASE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Fail fast on bad spec configuration.
    validate_deck(SLIDE_SPECS)

    from generators.nano_banana import generate_asset

    print('\n' + '=' * 62)
    print('  RENDER PIPELINE')
    print(f'  Output: {output_dir}')
    print('=' * 62)

    for i, spec in enumerate(SLIDE_SPECS):
        output_path = output_dir / f"slide_{i + 1:02d}.png"
        treatment   = spec["treatment"]
        accent_flag = "Y" if spec.get("accent") else "N"
        asset_used  = "none"

        # Generate Nano Banana asset if required
        if spec.get("generated_asset"):
            copy    = slides_copy[i] if i < len(slides_copy) else {}
            prompt  = copy.get("visual_direction", f"slide {i + 1} asset")
            slug    = re.sub(r'[^a-z0-9-]', '', prompt.lower().replace(' ', '-'))[:40]
            staging_name = f"{slug}.png"
            staged_path  = GENERATED_STAGING_DIR / staging_name
            approved_path = GENERATED_DIR / staging_name

            if not approved_path.exists():
                # Trigger generation into staging (if not already there)
                if not staged_path.exists():
                    generate_asset(prompt, staged_path)
                raise FileNotFoundError(
                    f"Slide {i}: generated asset has not been approved.\n"
                    f"  Staged:   {staged_path}\n"
                    f"  Approve:  move the file to {approved_path}"
                )
            asset_used = approved_path.name

        # Render slide
        copy       = slides_copy[i] if i < len(slides_copy) else {}
        render_fn  = _get_render_fn(treatment)
        render_fn(spec, copy, output_path)

        print(f"  {i} | {treatment:<18} | accent={accent_flag} | asset={asset_used}  →  {output_path.name}")


# ── ClinicalHours product context ─────────────────────────────────────────────

PRODUCT_CONTEXT = ascii_safe("""
ABOUT CLINICALHOURS (use this as ground truth in every prompt):
- Free app for pre-med undergrads in the US at clinicalhours.org
- Core features: (1) clinical volunteer hours tracker with supervisor verification,
  (2) free clinic finder - map of real HRSA-verified volunteer opportunities near the user,
  (3) AMCAS activity essay builder with AI writing assistance from your actual hour log
- Founded by two Texas A&M undergrad students (authentic, relatable origin story)
- 200+ organic users, zero marketing spend - pure word of mouth
- Completely free, always will be
- Target user: pre-med undergrad aged 18-24, 1-3 years out from AMCAS submission

KEY NUMBERS TO USE IN SLIDES (cite these when they fit):
- AMCAS application opens May 1st every year. Ideal first submit: June 1st.
  Each week of delay meaningfully lowers interview invitation rates.
- Most US medical schools: minimum 100-200 clinical hours required.
  Top 20 schools (Hopkins, Mayo, Harvard): competitive applicants have 400-600+.
- AMCAS Activities section: 15 slots total, 700 characters each.
  Clinical experience is its own category - it must be verified.
- "Most Meaningful" flag: 3 of your 15 activities get an extra 1,325 chars.
  Clinical experience should almost always be one of your 3.
- ClinicalHours auto-generates your 700-char AMCAS activity description
  from your actual logged hours - no blank-page writing anxiety.
- Verification: supervisor confirms hours via one-click email from the app.
  Takes them under 60 seconds. Pre-med does nothing except send the request.

COMMON PRE-MED MISTAKES (these are gold for hook slides - use them):
- Logging nothing all year, then trying to reconstruct 200 hours from memory
  2 weeks before the AMCAS deadline. (This is more common than people admit.)
- Losing contact with supervisors who can no longer verify
  (graduated, changed jobs, left the clinic, retired).
- Confusing volunteering / physician-shadowing / research - AMCAS tracks them
  in SEPARATE categories. Hours in the wrong category do not count.
- Choosing non-clinical volunteering (food bank, tutoring) and discovering
  it does not count toward clinical hours on the AMCAS.
- Writing a vague AMCAS activity description ("I helped patients") instead of
  a specific, quantified, supervisor-verified narrative.
- Starting clinical hours junior year - not enough time to hit 400+ before June.
- Not asking supervisors to verify hours before they leave the organization.

APP FEATURES - be specific when you reference them:
- Hours tracker: log date, location, clinic name, hours, supervisor name + email, notes.
- Verification: one-click email to supervisor. They confirm in under 60 seconds.
- Free clinic finder: map + list of HRSA-verified free clinics near you,
  filterable by city and state. Real volunteer opportunities, not fabricated listings.
- AMCAS essay builder: AI drafts your 700-char activity description
  from your actual hour log. Supervisor-verified facts, not invented details.
- Dashboard: total hours, category breakdown, verification status, full timeline.

KEY PAIN POINTS (use to drive hooks):
- AMCAS requires verified clinical hours. Most pre-meds lose track,
  panic, or discover problems weeks before the application deadline.
- Finding real free-clinic volunteer opportunities is fragmented and hard.
- Writing the AMCAS activities section from memory is stressful and imprecise.

BRAND VOICE: calm, direct, founder voice. Not corporate. Not hype.
Like a senior pre-med giving real advice to a first-year. No em dashes.

APP SCREENSHOTS AVAILABLE (for real compositing into slides):
  dashboard.png     - Hours tracking dashboard with logged hours and progress
  opportunities.png - Map/list of free clinic volunteer opportunities nearby
  essay.png         - AMCAS personal statement / activity essay builder
  tracker.png       - Hour logging entry view with verification status
  (Drop any .png into assets/screenshots/ inside this project to use it)
""")


CONCISENESS_RULES = ascii_safe(
    'CONCISENESS (hard limits - strip every word that does not add meaning):\n'
    '- text: max 6 words. Count them.\n'
    '- subtext: max 8 words. One clause. No filler. Present tense. If you cannot say it in 8 words, cut the weakest idea.\n'
    '- visual_direction: max 4 words. Noun + adjective only. No verbs, no punctuation.\n'
    '- retention_hook: max 4 words. The tension in one phrase.\n'
    '- audio_vibe: max 4 words.\n'
    '- framework_reason: max 8 words.\n'
    '- narrative_arc: max 12 words total.\n'
    'Use your full context to choose the single most important idea per field. Cut the rest.\n'
)

MARKETING_PSYCHOLOGY = ascii_safe("""
MARKETING PSYCHOLOGY (apply the most relevant principle to each slide):

LOSS AVERSION: Losses feel 2x stronger than gains. Frame around what viewer will LOSE.
  "Lose your supervisor contact" beats "Save your supervisor contact."
  Use on hook and agitate slides.

IDENTITY MIRRORING: People act consistent with who they want to be.
  Mirror their ideal identity: "Pre-meds who track from day 1 get 400+ hours."
  Use on hook, agitate, and audience slides.

SPECIFICITY AS PROOF: Vague claims trigger skepticism. Specific numbers pass the filter.
  "273 pre-meds" beats "hundreds." "Verified in 47 seconds" beats "verified fast."
  Use wherever numbers appear.

EFFORT REMOVAL: Overwhelmed people convert when effort feels minimal.
  Emphasize how little ClinicalHours requires: "60 seconds," "one click," "auto-generated."
  Use on solution and CTA slides.

CURIOSITY GAP: Slide 1 must not contain enough info to skip slide 2.
  Never resolve the hook question before slide 3.

SOCIAL MOMENTUM: "200+ and growing" beats "200+." Show direction, not just presence.
  Use on social proof and credential slides.
""")


# ── 2025 TikTok algorithm + retention research ────────────────────────────────

RESEARCH_CONTEXT = ascii_safe("""
TIKTOK CAROUSEL RETENTION PRINCIPLES (2025 - apply all of these):

HOOK (Slide 1 - the only slide that matters if the others fail):
- You have 1.5-2 seconds. The hook must stop the scroll before the brain decides to swipe.
- Curiosity gap formula: name a pain OR promise specific information the viewer doesn't have.
  "The thing pre-meds miss about AMCAS" -> curiosity gap (what thing?)
  "Before you submit, read this" -> curiosity gap (read what?)
  "3 hours that almost cost me med school" -> curiosity gap (which 3 hours?)
- Naming a specific number or deadline converts better than vague hooks.
- Never open with a compliment, an intro, or a question that can be answered without swiping.
- "Swipe ->" cue increases swipe-through rate by ~12% (TikTok internal, 2024).

TEXT RULES (every slide):
- Maximum 6 words for main display text. Fewer is usually better. Count every word.
- One idea per slide. If you have two ideas, you have two slides.
- Bold, high-contrast type. Left-align or center. Pre-meds are on a 6-inch screen.

RETENTION MECHANICS (slides 2-4):
- Each slide should create a micro-tension that only resolves on the NEXT slide.
  Slide 2 ends with an unresolved question. Slide 3 teases the answer. Slide 4 delivers it.
- Pattern interrupt: alternate between emotional and factual slides to maintain attention.
- If the viewer can guess what comes next without swiping, they won't swipe.

SAVES (the #1 algorithm signal in 2025):
- Saves = viewer thought "I'll need this later."
- Checklist slides, stat slides, and 'before/after' slides get the most saves.
- Make at least ONE slide quotable or screenshottable on its own.
- The more specific and surprising the insight, the more likely a save.

CALL TO ACTION (Slide 5):
- Must include a specific action verb: "Log", "Find", "Track", "Start" - not "Check out" or "Learn more."
- Include the URL (clinicalhours.org) in the image and the caption.
- Best CTA formula: [verb] + [specific outcome] + [at/on clinicalhours.org]
  "Log your hours free at clinicalhours.org"
  "Find free clinics near you at clinicalhours.org"

PROMOTING CLINICALHOURS (bake this into slide structure):
- Don't introduce the product until slide 3 or 4. Earn the right to pitch.
- Hook and agitation slides: make the viewer feel the pain before the solution appears.
- Frame ClinicalHours as "the thing I wish I had" not "a new app you should download."
- Founder origin story ("two Texas A&M students built this because they lived the pain")
  adds authentic credibility - especially powerful for the social-proof framework.
- Social proof: "200+ pre-meds already tracking" converts better than any feature list.
- Deadline urgency: AMCAS opens May 1st, submit by June 1st ideally.
  Use this calendar pressure whenever the topic is application-cycle-adjacent.
- Verification angle: "your supervisor can confirm in 60 seconds" removes the biggest
  objection to starting (effort). Lead with ease, not features.
- Free angle: "completely free, always" neutralizes the "just another paid app" objection.
  Mention it on the CTA slide.

SCREENSHOT INTEGRATION:
- Real app screenshots outperform illustrated mockups for credibility. Always prefer them.
- Best slide placements for screenshots: solution reveal (slide 3-4) and CTA (slide 5).
- Hook slides (slide 1) almost never use screenshots - pure text hook converts better.
- Reserve a clear screenshot zone even when no screenshot is available yet.
""")


# ── Marketing frameworks ───────────────────────────────────────────────────────

FRAMEWORKS: Dict[str, Dict] = {
    'pain-hook': {
        'name': 'Pain Hook',
        'description': 'Identify a specific pain -> agitate it -> reframe -> reveal solution -> CTA',
        'best_for': 'Topics where the audience already feels the problem but has not found a fix',
        'slides': [
            {'role': 'Hook showing a specific pain point',   'type': 'hook'},
            {'role': 'Agitate - make the pain feel urgent',  'type': 'agitate'},
            {'role': 'Reframe - the insight that shifts POV','type': 'reframe'},
            {'role': 'Solution reveal (ClinicalHours)',      'type': 'solution'},
            {'role': 'Call to action',                       'type': 'cta'},
        ],
    },
    'stat-drop': {
        'name': 'Stat Drop',
        'description': 'Lead with a surprising stat -> contextualize -> reveal insight -> tie to product -> CTA',
        'best_for': 'Topics where a counterintuitive number can stop the scroll',
        'slides': [
            {'role': 'Surprising statistic hook',            'type': 'stat_hook'},
            {'role': 'Context that makes the stat personal', 'type': 'stat_context'},
            {'role': 'Insight it reveals',                   'type': 'insight'},
            {'role': 'How ClinicalHours solves it',          'type': 'solution'},
            {'role': 'Call to action',                       'type': 'cta'},
        ],
    },
    'before-after': {
        'name': 'Before / After',
        'description': 'Show chaos before -> identify the problem -> show clarity after -> reveal the tool -> CTA',
        'best_for': 'Transformation stories, process improvements, or "I used to do X now I do Y"',
        'slides': [
            {'role': 'Before state (chaos, stress, confusion)','type': 'before'},
            {'role': 'The problem explained',                  'type': 'agitate'},
            {'role': 'After state (clarity, confidence)',      'type': 'after'},
            {'role': 'The tool that creates the after',        'type': 'solution'},
            {'role': 'Call to action',                         'type': 'cta'},
        ],
    },
    'social-proof': {
        'name': 'Social Proof',
        'description': 'Lead with credibility -> explain the product -> name the audience -> show proof -> CTA',
        'best_for': 'When you have numbers, wins, or user validation to lead with',
        'slides': [
            {'role': 'Credibility hook (number, win, validation)', 'type': 'credential'},
            {'role': 'What ClinicalHours does',                    'type': 'solution'},
            {'role': 'Who it is specifically for',                 'type': 'audience'},
            {'role': 'Proof point (stat, outcome, testimonial)',   'type': 'proof'},
            {'role': 'Call to action',                             'type': 'cta'},
        ],
    },
    'tutorial': {
        'name': 'Tutorial',
        'description': 'Promise learning -> step 1 -> step 2 -> step 3 (product appears naturally) -> CTA',
        'best_for': 'How-to content, process explanations, checklist-style education',
        'slides': [
            {'role': 'Promise of what they will learn',            'type': 'promise'},
            {'role': 'Step 1 (delivers standalone value)',         'type': 'step'},
            {'role': 'Step 2 (delivers standalone value)',         'type': 'step'},
            {'role': 'Step 3 (ClinicalHours appears naturally)',   'type': 'solution'},
            {'role': 'Call to action',                             'type': 'cta'},
        ],
    },
    'amcas-countdown': {
        'name': 'AMCAS Countdown',
        'description': 'Deadline hook -> reveal the stakes -> expose the mistake -> 10-min fix -> CTA',
        'best_for': 'Jan-June AMCAS season content. High urgency, deadline-driven. '
                    'Works any time "the clock is ticking" is true for the viewer.',
        'slides': [
            {'role': 'The AMCAS deadline that most pre-meds underestimate', 'type': 'hook'},
            {'role': 'What happens if you are not ready (real stakes)',      'type': 'agitate'},
            {'role': 'The mistake that causes it (specific, relatable)',     'type': 'reframe'},
            {'role': 'The 10-minute fix - ClinicalHours',                   'type': 'solution'},
            {'role': 'Start free now - clinicalhours.org',                  'type': 'cta'},
        ],
    },
}


# ── Per-slide questions ────────────────────────────────────────────────────────

SLIDE_QUESTIONS: Dict[str, List[Tuple[str, str, bool]]] = {
    'hook': [
        ("What specific pain should stop a pre-med mid-scroll?\n"
         "  (e.g. 'realized 50 hours were unverified 2 weeks before AMCAS')",
         'pain_detail', True),
        ("Any specific curiosity-gap angle? Press Enter and Claude will pick one.",
         'hook_angle', False),
    ],
    'agitate': [
        ("What makes this pain feel real and urgent? Press Enter to let Claude decide.\n"
         "  (e.g. rejection fear, wasted summer, AMCAS word count pressure)",
         'agitation_detail', False),
    ],
    'reframe': [
        ("What is the turning point or 'aha' insight? Press Enter to let Claude decide.",
         'reframe_insight', False),
    ],
    'solution': [
        ("Which ClinicalHours feature to spotlight? Press Enter to let Claude decide.\n"
         "  Options: hour tracking / clinic finder / AMCAS essay builder / all three",
         'feature_focus', False),
        ("Use a real screenshot for this slide? (yes/no, or screenshot name)",
         'screenshot_hint', False),
    ],
    'cta': [
        ("What specific action should they take?\n"
         "  (e.g. 'Log free at clinicalhours.org', 'Find your first free clinic')",
         'cta_action', True),
    ],
    'stat_hook': [
        ("Any specific stat to use? Press Enter and Claude will find a compelling one.\n"
         "  (e.g. 'average pre-med logs 200+ hours', 'only 1 in 10 pre-meds tracks consistently')",
         'stat_value', False),
    ],
    'stat_context': [
        ("What does this stat mean for pre-meds personally? Press Enter to skip.",
         'stat_meaning', False),
    ],
    'insight': [
        ("What insight should this reveal? It should feel screenshot-worthy.\n"
         "  Press Enter to let Claude decide.",
         'insight_text', False),
    ],
    'before': [
        ("Describe the 'before' chaos. What does a struggling pre-med's situation look like?\n"
         "  Press Enter to let Claude decide.",
         'before_state', False),
    ],
    'after': [
        ("Describe the 'after' clarity. What does success look like?\n"
         "  Press Enter to let Claude decide.",
         'after_state', False),
    ],
    'credential': [
        ("What credibility hook should open with? Press Enter to let Claude decide.\n"
         "  Options: '200+ pre-meds' / 'Texas A&M founders' / 'Meloy Launch winner' / etc.",
         'credential_detail', False),
    ],
    'audience': [
        ("Who exactly is this for? Press Enter for default (pre-med undergrads applying to med school).",
         'audience_detail', False),
    ],
    'proof': [
        ("Any specific proof point? Press Enter to let Claude decide.\n"
         "  (e.g. user count, outcome stat, competition win, user testimonial snippet)",
         'proof_detail', False),
    ],
    'promise': [
        ("What will they learn by swiping through? Press Enter to let Claude decide.",
         'promise_text', False),
    ],
    'step': [
        ("Any specific content for this step? Press Enter to let Claude decide.",
         'step_content', False),
    ],
}

SLIDE_TIPS: Dict[str, str] = {
    'hook':         'RETENTION: 1.5s scroll decision. Curiosity gap + specific pain = 60-80% swipe-through.',
    'stat_hook':    'RETENTION: Counterintuitive stats stop the scroll. Surprising > informative.',
    'before':       'RETENTION: "Before" slides work best when they feel painfully, specifically relatable.',
    'credential':   'RETENTION: Lead with your strongest single number or validation. Not a list.',
    'promise':      'RETENTION: The promise must be specific enough that skipping feels like a loss.',
    'agitate':      'RETENTION: One concrete consequence > vague suffering. End with unresolved tension.',
    'stat_context': 'RETENTION: Context that makes the stat personally relevant gets saved.',
    'after':        'RETENTION: "After" should feel aspirational but achievable, not utopian.',
    'reframe':      'RETENTION: The reframe is the hinge - it recolors how slide 1 felt. Make it surprising.',
    'solution':     'RETENTION: Product reveal lands best when it feels inevitable after the setup.',
    'insight':      'RETENTION: The insight should feel worth screenshotting. Bold + specific = saves.',
    'audience':     'RETENTION: Mirror their identity: "If you are a pre-med who..." converts better.',
    'proof':        'RETENTION: Specific proof (numbers, outcomes) converts 3x better than generic claims.',
    'step':         'RETENTION: Each step should deliver standalone value, even without the app.',
    'cta':          'RETENTION: Verb + outcome + URL. "Log free at clinicalhours.org" not "check it out".',
}

RETENTION_SIGNALS: Dict[str, str] = {
    'hook':         'swipe-through rate',
    'stat_hook':    'swipe-through rate',
    'before':       'swipe-through rate',
    'credential':   'swipe-through rate',
    'promise':      'swipe-through rate',
    'agitate':      'slide retention',
    'stat_context': 'slide retention + save rate',
    'after':        'slide retention',
    'reframe':      'slide retention + share rate',
    'solution':     'save rate + profile click rate',
    'insight':      'save rate + share rate',
    'audience':     'profile click rate',
    'proof':        'save rate + link click rate',
    'step':         'save rate',
    'cta':          'link click rate + follow rate',
}


# ── Creative brief options ──────────────────────────────────────────────────────

TARGET_EMOTIONS: List[str] = ['curiosity', 'urgency', 'validation', 'calm']
HOOK_TYPES:      List[str] = ['contrarian', 'stat', 'story-opener', 'question']
CTA_TYPES:       List[str] = ['link-in-bio', 'save', 'follow', 'comment']

CONTENT_PILLARS: List[str] = ['education', 'urgency', 'social-proof', 'validation']

# Pre-med pain points to seed topic ideas from
SEED_TOPICS: List[str] = [
    'losing track of clinical hours before AMCAS',
    'AMCAS deadline panic (May 1 opens, June 1 ideal submit)',
    'supervisor left - can no longer verify hours',
    'finding free clinic volunteer opportunities',
    'AMCAS activity essay writer\'s block (700 chars)',
    'starting clinical hours too late (junior year)',
    'rejection recovery and reapplication strategy',
    'first-gen pre-med impostor syndrome',
    'gap year doubt and how to redirect it',
    'confusing clinical vs. non-clinical volunteer hours',
    'comparing hour counts with other pre-meds',
    'shadowing vs. clinical hours - what actually counts',
    'AMCAS "most meaningful" activity selection anxiety',
    'free clinic volunteering is underrated',
    'how early you really need to start clinical hours',
]

# Banned filler openers - any slide starting with these should be flagged/rewritten
BANNED_OPENERS: List[str] = [
    "here's why", "did you know", "the truth about", "let me explain",
    "in this post", "have you ever", "what if i told you", "fun fact",
    "i'm going to show you", "today we're talking about", "a lot of pre-meds",
    "most pre-meds don't know", "you might not know", "nobody talks about",
]

# Typography spec - DM Sans exclusively
FONT_SPEC = ascii_safe(
    'FONT: DM Sans exclusively. No other fonts. '
    'Headlines: DM Sans 700-800 weight, charcoal (#1A1A1A), left-aligned with generous left margin. '
    'Subtext: DM Sans 300 weight, warm gray (#888880). '
    'Max 6 words per line. Max 3 lines per headline. '
    'Always separate headline from secondary elements with a thin 1px charcoal horizontal rule. '
    'No colored text. No Instrument Serif. No teal on text.'
)


# ── Visual style guide ─────────────────────────────────────────────────────────
# Applies universally to every slide regardless of device choice.

VISUAL_STYLE_GUIDE = ascii_safe(
    'GLOBAL STYLE (non-negotiable on every slide):\n'
    'Background: rich, visible gradient as specified per slide. '
    'Colors are derived from the brand palette and should be clearly visible and beautiful. '
    'Background must look distinct and intentional - not washed out or near-white.\n'
    'Typography: DM Sans exclusively. Headlines 700-800 weight, charcoal (#1A1A1A), '
    'left-aligned with a generous left margin (~100px from edge). '
    'Subtext 300 weight, warm gray (#888880). '
    'Max 6 words per line, max 3 lines per headline. '
    'Separate headline from all secondary elements with a thin 1px charcoal horizontal rule.\n'
    'Lighting: soft diffused studio light, warm cast throughout.\n'
    'NEVER include: faces, icons, brand bars, colored text, '
    'wood textures, table surfaces, desk surfaces, '
    'rectangular image insets, multiple devices in one frame.\n'
)

# ── Brand palette (from ClinicalHours logo) ────────────────────────────────────

BRAND_PALETTE = {
    'coral':    '#C6837A',  # muted coral / dusty rose
    'peach':    '#D8A68E',  # warm peach / sand
    'lavender': '#BFC9D6',  # pale lavender blue
    'slate':    '#565D6D',  # slate blue / deep gray
    'pearl':    '#E8EBF2',  # off-white / pearl
}

# Per-slide visual theme: unique gradient + foreground element type per slide number.
# visual: 'object' = single isolated real-world object (no device)
#         'device' = phone or laptop (controlled by user's visual_style choice)
#         'typography' = text only, no foreground element
SLIDE_THEMES: Dict[int, Dict] = {
    1: {
        'gradient': (
            'Bold linear gradient from warm coral #C6837A at the top-left, '
            'transitioning through pearl #E8EBF2 in the middle, '
            'to soft off-white #F5F2EE at the bottom-right. '
            'The coral is rich and clearly visible at the top. '
            'Smooth, clean gradient - no banding.'
        ),
        'visual': 'object',
        'objects': [
            'a single analog clock face photographed from directly above, clean white dial, '
            'minimal numerals, no surroundings, floating on the gradient with a soft drop shadow',
            'a single hourglass with fine white sand, centered, floating on the gradient background, '
            'soft shadow beneath, no table or surface visible',
            'a single wall calendar page, one date circled in dark ink, lying flat overhead view, '
            'floating on the gradient, no surrounding context',
        ],
    },
    2: {
        'gradient': (
            'Bold linear gradient from warm peach #D8A68E at the right edge, '
            'sweeping left through #E8EBF2 pearl, '
            'to soft off-white #F5F2EE at the left edge. '
            'The peach is warm and visible on the right side. '
            'Smooth transition, no banding.'
        ),
        'visual': 'object',
        'objects': [
            'a single stethoscope coiled neatly, photographed overhead flat-lay, '
            'floating on the gradient background, soft drop shadow, no surface or props',
            'a single medical notepad with a pen resting diagonally across it, overhead flat-lay, '
            'floating on the gradient, no table or surface visible',
            'a single open textbook, top-down view, clean white pages, floating on the gradient, '
            'no other objects or surfaces',
        ],
    },
    3: {
        'gradient': (
            'Bold linear gradient from pale lavender blue #BFC9D6 at the top, '
            'fading through #E8EBF2 pearl to soft off-white #F5F2EE at the bottom. '
            'The lavender blue is clearly visible at the top, giving a cool calm mood. '
            'Smooth, clean gradient.'
        ),
        'visual': 'object',
        'objects': [
            'a single open notebook with a clean fountain pen resting across it, overhead flat-lay, '
            'floating on the gradient, soft drop shadow, no table or surface',
            'a single brass compass lying flat, overhead view, floating on the gradient background, '
            'soft shadow, no surrounding context or props',
            'a single sealed white envelope lying flat, overhead view, floating on the gradient, '
            'soft drop shadow, no address or text on the envelope',
        ],
    },
    4: {
        'gradient': (
            'Radial gradient: soft off-white #F5F2EE at the center, '
            'expanding outward to slate blue #565D6D at the frame edges. '
            'The slate blue border is rich and visible, framing the center content. '
            'Smooth vignette effect.'
        ),
        'visual': 'device',
        'objects': [],
    },
    5: {
        'gradient': (
            'Diagonal gradient from coral #C6837A at the top-left corner, '
            'through pearl #E8EBF2 in the center, '
            'to warm peach #D8A68E at the bottom-right corner. '
            'Both coral and peach are clearly visible. '
            'Warm, inviting close to the carousel.'
        ),
        'visual': 'typography',
        'objects': [],
    },
}

OBJECT_VISUAL_SPEC = ascii_safe(
    'Object photography rules (non-negotiable):\n'
    '- Single object only. No props, no context, no surrounding environment.\n'
    '- Object floats directly on the gradient background with a soft drop shadow beneath.\n'
    '- Object fills approximately 28-38% of the canvas area.\n'
    '- Position: centered or slightly off-center to complement the text zone.\n'
    '- Photography style: clean studio still-life, warm diffused light matching the slide.\n'
    '- No humans, no hands, no faces, no text on the object itself.\n'
    '- Object color palette: neutral or muted tones that complement the gradient. Nothing loud.\n'
    '- Headline text is the dominant visual element. Object is secondary and supporting.\n'
)

# Device / layout variants - what the 4 visual style choices now mean
VISUAL_STYLES: Dict[str, str] = {
    'typography': (
        'NO DEVICE. Pure typography composition only. '
        'DM Sans headline 700-800 weight, charcoal (#1A1A1A). '
        'Text alignment: left-aligned with ~100px left margin, or centered for emphasis - '
        'choose based on the headline length and emotional weight. '
        '1px charcoal horizontal rule below the headline. '
        'Subtext in DM Sans 300 warm gray (#888880) below the rule. '
        'No phone frames. No device illustrations. No screenshots. '
        'Off-white matte (#F5F2EE) background fills the entire frame with breathing room.'
    ),
    'mockup': (
        'SINGLE PHONE floating directly on the off-white matte (#F5F2EE) background. '
        'No desk, no wood surface, no table - phone floats in open space. '
        'Soft drop shadow beneath the phone. '
        'Phone angle: upright or slight perspective tilt of 8-10 degrees - choose one. '
        'Screen content: light UI only, no dark mode. Screen is always the brightest element. '
        'ClinicalHours branding on screen only if this is the solution reveal slide. '
        'DM Sans 700-800 headline in charcoal above the device, left-aligned. '
        '1px charcoal rule between the text zone and device.'
    ),
    'hybrid': (
        'SINGLE LAPTOP floating directly on the off-white matte (#F5F2EE) background. '
        'No desk, no wood surface, no table - laptop floats in open space. '
        'Soft drop shadow beneath. Slight perspective tilt of 8-10 degrees. '
        'Screen content: light UI only, no dark mode. Screen is always the brightest element. '
        'ClinicalHours branding on screen only if this is the solution reveal slide. '
        'DM Sans 700-800 headline in charcoal, left-aligned, above or beside the device. '
        '1px charcoal rule separating the text zone from the device zone.'
    ),
    'screenshot-focus': (
        'OVERHEAD BIRD\'S EYE VIEW. Phone or laptop photographed from directly above. '
        'Device lies flat on the off-white matte (#F5F2EE) background - no desk, no surface. '
        'Soft shadow visible around the device edges. '
        'Screen content: light UI only, no dark mode. Screen is always the brightest element. '
        'ClinicalHours branding on screen only if this is the solution reveal slide. '
        'DM Sans 700-800 headline in charcoal overlaid above the device, left-aligned. '
        '1px charcoal rule below the headline.'
    ),
}

SLIDE_ROLE_SLUGS: Dict[int, str] = {1: 'hook', 2: 'body', 3: 'body', 4: 'reveal', 5: 'cta'}

# Which screenshots work best on each slide number
SCREENSHOT_SUGGESTIONS: Dict[str, List[str]] = {
    'solution':  ['dashboard.png', 'tracker.png', 'opportunities.png'],
    'after':     ['dashboard.png', 'tracker.png'],
    'proof':     ['dashboard.png', 'opportunities.png'],
    'cta':       ['opportunities.png', 'essay.png'],
    'insight':   ['dashboard.png', 'essay.png'],
}

# Layout variants — controls text position and spatial composition within the unified style.
# A new variant is randomly selected on each generation (and each retry), ensuring visual variety.
LAYOUT_VARIANTS_TIKTOK: List[Dict[str, str]] = [
    {
        'name': 'headline-top',
        'modifier': (
            'Headline and rule in the upper third of the canvas. '
            'Device or open space occupies the lower two-thirds. '
            'Generous breathing room between text and device.'
        ),
    },
    {
        'name': 'headline-bottom',
        'modifier': (
            'Device or open space in the upper two-thirds. '
            'Headline, 1px rule, and subtext anchored to the lower third. '
            'Text reads after the visual impact.'
        ),
    },
    {
        'name': 'headline-mid',
        'modifier': (
            'Headline and rule centered vertically on the canvas. '
            'Equal breathing room above and below. '
            'Balanced, editorial composition.'
        ),
    },
    {
        'name': 'text-dominant',
        'modifier': (
            'Large headline fills 40% of canvas height - oversized, maximum presence. '
            'DM Sans at maximum weight. Device is small and secondary if present. '
            'Every word readable as a 6-inch thumbnail.'
        ),
    },
    {
        'name': 'device-dominant',
        'modifier': (
            'Device fills 55-65% of the frame - product is the visual anchor. '
            'Headline is compact, above the device, small but sharp. '
            'Minimal text, maximum product visibility.'
        ),
    },
]

LAYOUT_VARIANTS_INSTAGRAM: List[Dict[str, str]] = [
    {
        'name': 'text-left',
        'modifier': (
            'Landscape split layout: headline and rule flush to the left third of the canvas, '
            'vertically centered. Visual element (device or object) anchored to the right half. '
            'Clean vertical breathing room on both sides.'
        ),
    },
    {
        'name': 'text-right',
        'modifier': (
            'Landscape split layout: visual element (device or object) fills the left half. '
            'Headline, rule, and subtext anchored to the right third, vertically centered. '
            'Text reads after the visual impact.'
        ),
    },
    {
        'name': 'headline-center',
        'modifier': (
            'Headline and rule centered horizontally and vertically on the canvas. '
            'Visual element placed subtly in the background or lower-right corner. '
            'Balanced, editorial composition with generous white space.'
        ),
    },
    {
        'name': 'text-dominant',
        'modifier': (
            'Oversized headline spans 60% of canvas width — maximum typographic presence. '
            'DM Sans at maximum weight, left-aligned. Visual element is small and secondary. '
            'Every word readable as a thumbnail.'
        ),
    },
    {
        'name': 'visual-dominant',
        'modifier': (
            'Visual element (device or object) fills 60-70% of the frame as the primary anchor. '
            'Headline is compact and sharp, top-left corner. '
            'Minimal text, maximum product or object visibility.'
        ),
    },
]

# Keep LAYOUT_VARIANTS as alias (used by pick_layout_variant default)
LAYOUT_VARIANTS = LAYOUT_VARIANTS_TIKTOK


# ── API key guards ─────────────────────────────────────────────────────────────

def check_api_keys() -> None:
    missing = []
    if not os.environ.get('ANTHROPIC_API_KEY'):
        missing.append('ANTHROPIC_API_KEY')
    if not os.environ.get('GEMINI_API_KEY'):
        missing.append('GEMINI_API_KEY')
    if missing:
        print('Error: the following environment variables are not set:\n')
        for key in missing:
            print(f'  {key}')
        print('\nFix: edit the .env file in this folder and add your keys.')
        sys.exit(1)


def check_copy_only_keys() -> None:
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('Error: ANTHROPIC_API_KEY is not set.')
        print('Fix: edit the .env file in this folder.')
        sys.exit(1)


# ── Slug / normalize ───────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = ascii_safe(text).lower().strip()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text)
    text = re.sub(r'-+', '-', text).strip('-')
    return text[:40]


def parse_json_response(raw: str) -> Dict:
    """Robustly extract and parse the first JSON object from a Claude response."""
    raw = raw.strip()
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```\s*$', '', raw)
    # If Claude added a preamble, extract only the first {...} block
    match = re.search(r'\{[\s\S]*\}', raw)
    if match:
        raw = match.group(0)
    return json.loads(raw)


def normalize_framework(val: str) -> Optional[str]:
    v = val.lower().strip()
    if v in FRAMEWORKS:
        return v
    for k, fw in FRAMEWORKS.items():
        if v == fw['name'].lower():
            return k
    s = slugify(val)
    return s if s in FRAMEWORKS else None


# ── Screenshot helpers ─────────────────────────────────────────────────────────

def setup_screenshots_dir() -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    readme = SCREENSHOTS_DIR / 'README.txt'
    first_time = not readme.exists()
    if first_time:
        readme.write_text(
            'Place real ClinicalHours app screenshots here.\n'
            'The agent will offer to composite them into slides automatically.\n\n'
            'Suggested filenames (these are auto-selected by slide type):\n'
            '  dashboard.png     - Main hours tracking dashboard\n'
            '  opportunities.png - Volunteer opportunities list / map\n'
            '  essay.png         - AMCAS personal statement / activity editor\n'
            '  tracker.png       - Hours logging entry with verification status\n\n'
            'You can drop in any .png and select it by name or number during generation.\n'
            'All visual styles reserve a screenshot zone even without real screenshots.\n',
            encoding='utf-8',
        )
        # Open the screenshots folder in Explorer the first time so user can see it
        _open_folder(SCREENSHOTS_DIR)
    print(f'  Screenshots folder: {SCREENSHOTS_DIR}')


def list_available_screenshots() -> List[Path]:
    if not SCREENSHOTS_DIR.exists():
        return []
    return sorted(SCREENSHOTS_DIR.glob('*.png'))


def pick_screenshot_interactive(slide_number: int, slide_type: str) -> Optional[Path]:
    available = list_available_screenshots()
    if not available:
        print(f'\n  No screenshots found in {SCREENSHOTS_DIR}')
        print('  (A screenshot placeholder zone will still be reserved in the image)')
        return None

    suggested = SCREENSHOT_SUGGESTIONS.get(slide_type, [])
    auto_match = None
    for name in suggested:
        match = SCREENSHOTS_DIR / name
        if match.exists():
            auto_match = match
            break

    print(f'\n  Screenshot for slide {slide_number}:')
    for i, p in enumerate(available, 1):
        marker = ' <- suggested' if auto_match and p == auto_match else ''
        print(f'    {i}. {p.name}{marker}')
    print('    Enter = no real screenshot (placeholder zone still reserved)')

    raw = input('  > ').strip()
    if not raw:
        return None
    if raw.isdigit() and 1 <= int(raw) <= len(available):
        return available[int(raw) - 1]
    for p in available:
        if raw.lower() in p.name.lower():
            return p
    return None


def suggest_screenshot(slide_type: str) -> Optional[Path]:
    """Auto-suggest a screenshot for batch mode based on slide type."""
    for name in SCREENSHOT_SUGGESTIONS.get(slide_type, []):
        p = SCREENSHOTS_DIR / name
        if p.exists():
            return p
    return None


# ── Rejection log ──────────────────────────────────────────────────────────────

def load_rejection_log() -> Dict:
    """Read rejection log from disk; return empty structure on missing/error."""
    try:
        if REJECTION_LOG_FILE.exists():
            return json.loads(REJECTION_LOG_FILE.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {'copy_rejections': [], 'image_rejections': []}


def save_rejection_log(log: Dict) -> None:
    """Write rejection log to disk."""
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    REJECTION_LOG_FILE.write_text(
        json.dumps(log, indent=2, ensure_ascii=True), encoding='utf-8'
    )


def log_copy_rejection(slide: Dict, topic: str, reason: str = '') -> None:
    """Append a copy rejection entry to the rejection log."""
    log = load_rejection_log()
    log['copy_rejections'].append({
        'timestamp': datetime.now().isoformat(),
        'topic': ascii_safe(topic),
        'slide_role': ascii_safe(slide.get('role', '')),
        'text': ascii_safe(slide.get('text', '')),
        'visual_direction': ascii_safe(slide.get('visual_direction', '')),
        'reason': ascii_safe(reason),
    })
    save_rejection_log(log)


def log_image_rejection(slide: Dict, slide_number: int, reason: str = '') -> None:
    """Append an image rejection entry to the rejection log."""
    log = load_rejection_log()
    log['image_rejections'].append({
        'timestamp': datetime.now().isoformat(),
        'slide_number': slide_number,
        'slide_role': ascii_safe(slide.get('role', '')),
        'text': ascii_safe(slide.get('text', '')),
        'visual_direction': ascii_safe(slide.get('visual_direction', '')),
        'reason': ascii_safe(reason),
    })
    save_rejection_log(log)


def format_copy_rejection_context(limit: int = 6) -> str:
    """Format the last N copy rejections as a prompt string."""
    log = load_rejection_log()
    rejections = log.get('copy_rejections', [])[-limit:]
    if not rejections:
        return ''
    lines = ['REJECTED COPY PATTERNS (never repeat these):']
    for r in rejections:
        reason_str = f' -- reason: {r["reason"]}' if r.get('reason') else ''
        lines.append(f'  [{r.get("slide_role", "")}] "{r.get("text", "")}"' + reason_str)
    return ascii_safe('\n'.join(lines) + '\n')


def format_image_rejection_context(slide_role: str = '', limit: int = 4) -> str:
    """Format the last N image rejections as a prompt string, optionally filtered by role."""
    log = load_rejection_log()
    rejections = log.get('image_rejections', [])
    if slide_role:
        rejections = [r for r in rejections if r.get('slide_role', '') == slide_role]
    rejections = rejections[-limit:]
    if not rejections:
        return ''
    lines = ['REJECTED IMAGE DESIGNS (avoid these visual patterns):']
    for r in rejections:
        reason_str = f' -- reason: {r["reason"]}' if r.get('reason') else ''
        lines.append(
            f'  [{r.get("slide_role", "")}] "{r.get("text", "")}" '
            f'visual: {r.get("visual_direction", "")}' + reason_str
        )
    return ascii_safe('\n'.join(lines) + '\n')


def pick_layout_variant(platform: str = 'tiktok') -> str:
    """Return a random layout modifier string for the given platform."""
    import random
    variants = LAYOUT_VARIANTS_INSTAGRAM if platform == 'instagram' else LAYOUT_VARIANTS_TIKTOK
    return ascii_safe(random.choice(variants)['modifier'])


# ── Deep Research Phase ────────────────────────────────────────────────────────

def research_topic(topic: str, client) -> Dict:
    """
    Deep research pass: Claude analyzes the topic and returns a structured brief
    that informs every subsequent slide prompt. This is the key v3 upgrade.
    """
    print('\n  Running deep research...', end='', flush=True)

    prompt = ascii_safe(
        'You are a TikTok content strategist specializing in pre-med content.\n'
        'A startup called ClinicalHours wants to make a viral TikTok carousel about:\n'
        f'  TOPIC: {topic}\n\n'
        + PRODUCT_CONTEXT + '\n'
        + RESEARCH_CONTEXT + '\n'
        'Your job: research this topic deeply and produce a content brief.\n\n'
        'Think through:\n'
        '1. What is the most painful, specific version of this topic for a pre-med?\n'
        '2. What counterintuitive stat or insight would stop a pre-med mid-scroll?\n'
        '3. What is the strongest hook angle (curiosity gap that names a specific pain)?\n'
        '4. What is the narrative arc that earns the right to pitch ClinicalHours?\n'
        '5. Which ClinicalHours feature is most relevant to this topic?\n'
        '6. Which screenshot would make the product feel most real on this topic?\n'
        '7. What is the best CTA (verb + outcome + clinicalhours.org)?\n'
        '8. Which of the 5 frameworks fits this topic best and why?\n\n'
        'Return valid JSON ONLY. No markdown. No explanation. Exact format:\n'
        '{\n'
        '  "recommended_framework": "pain-hook|stat-drop|before-after|social-proof|tutorial",\n'
        '  "framework_reason": "one sentence why",\n'
        '  "core_pain": "the single most specific pain point for a pre-med on this topic",\n'
        '  "surprising_stat": "a counterintuitive stat or fact (can be estimated if real unknown)",\n'
        '  "hook_options": ["hook angle 1", "hook angle 2", "hook angle 3"],\n'
        '  "narrative_arc": "hook -> agitation -> reframe -> solution -> CTA in one sentence",\n'
        '  "feature_spotlight": "which ClinicalHours feature fits best",\n'
        '  "screenshot_suggestion": "dashboard|tracker|opportunities|essay|none",\n'
        '  "best_cta": "specific verb + outcome + clinicalhours.org",\n'
        '  "save_bait": "one screenshottable insight worth saving"\n'
        '}'
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=800,
        messages=[{'role': 'user', 'content': prompt}],
    )
    data = parse_json_response(response.content[0].text)
    print(' done.')
    return data


def print_research_brief(brief: Dict) -> None:
    print('\n' + '=' * 62)
    print('  RESEARCH BRIEF')
    print('=' * 62)
    print(f'  Recommended framework:  {brief.get("recommended_framework", "N/A")}')
    print(f'  Why:                    {brief.get("framework_reason", "")}')
    print(f'\n  Core pain:              {brief.get("core_pain", "")}')
    print(f'  Surprising stat:        {brief.get("surprising_stat", "")}')
    print(f'  Save-bait insight:      {brief.get("save_bait", "")}')
    print(f'\n  Feature spotlight:      {brief.get("feature_spotlight", "")}')
    print(f'  Screenshot suggestion:  {brief.get("screenshot_suggestion", "")}')
    print(f'  Best CTA:               {brief.get("best_cta", "")}')
    print(f'\n  Hook options:')
    for i, h in enumerate(brief.get('hook_options', []), 1):
        print(f'    {i}. {h}')
    print(f'\n  Narrative arc:')
    print(f'    {brief.get("narrative_arc", "")}')
    print('=' * 62)


# ── Claude: single-slide copy ──────────────────────────────────────────────────

def generate_single_slide(
    topic: str,
    framework_key: str,
    slide_index: int,
    answers: Dict[str, str],
    previous_slides: List[Dict],
    client,
    research_brief: Optional[Dict] = None,
    session_config: Optional[Dict] = None,
    is_hook_written_last: bool = False,
) -> Dict:
    fw           = FRAMEWORKS[framework_key]
    slide_def    = fw['slides'][slide_index]
    role         = slide_def['role']
    slide_number = slide_index + 1
    is_first     = slide_number == 1
    is_last      = slide_number == 5
    cfg          = session_config or {}

    prev_ctx = ''
    if previous_slides:
        label = ('Slides 2-5 already written (slide 1 / hook is written LAST '
                 'to match what the content actually delivers):\n'
                 if is_hook_written_last and is_first
                 else 'Previous slides already written (maintain narrative continuity):\n')
        prev_ctx = label
        for s in sorted(previous_slides, key=lambda x: x['slide_number']):
            prev_ctx += f'  Slide {s["slide_number"]} [{s["role"]}]: "{s["text"]}"\n'
        prev_ctx += '\n'

    answers_ctx = ''
    if answers:
        answers_ctx = 'User-provided details for this slide:\n'
        for k, v in answers.items():
            answers_ctx += f'  {k}: {v}\n'
        answers_ctx += '\n'

    research_ctx = ''
    if research_brief:
        research_ctx = (
            'RESEARCH BRIEF (use this to inform copy):\n'
            f'  Core pain: {research_brief.get("core_pain", "")}\n'
            f'  Surprising stat: {research_brief.get("surprising_stat", "")}\n'
            f'  Save-bait insight: {research_brief.get("save_bait", "")}\n'
            f'  Feature to spotlight: {research_brief.get("feature_spotlight", "")}\n'
            f'  Best CTA: {research_brief.get("best_cta", "")}\n'
            f'  Narrative arc: {research_brief.get("narrative_arc", "")}\n'
        )
        if is_first and research_brief.get('hook_options'):
            research_ctx += '  Hook options to consider:\n'
            for h in research_brief['hook_options']:
                research_ctx += f'    - {h}\n'
        if research_brief.get('hook_override'):
            research_ctx += f'  HOOK ANGLE TO USE: {research_brief["hook_override"]}\n'
        research_ctx += '\n'

    brief_ctx = ''
    if cfg:
        brief_ctx = (
            'CREATIVE BRIEF FOR THIS DECK:\n'
            f'  Target emotion: {cfg.get("target_emotion", "curiosity")}\n'
            f'  Hook type: {cfg.get("hook_type", "contrarian")} (apply to slide 1)\n'
            f'  CTA type: {cfg.get("cta_type", "link-in-bio")} (apply to slide 5)\n'
            f'  Audience: {cfg.get("audience", "pre-med undergrads applying to US medical schools")}\n\n'
        )

    banned_str = ', '.join(f'"{o}"' for o in BANNED_OPENERS[:8])
    hook_rule = (
        '- HOOK SLIDE (written after slides 2-5 so it matches what the deck delivers):\n'
        '  Write a hook that promises EXACTLY what slides 2-5 contain - no overpromising.\n'
        f'  Hook type for this deck: {cfg.get("hook_type", "contrarian")}.\n'
        '  Stop the scroll in 1.5 seconds. Name a specific pain or promise specific info.\n'
        f'  BANNED OPENERS (never start the text with): {banned_str}.\n'
        '  Include "Swipe ->" in visual_direction.\n'
    ) if is_first else ''

    tension_rule = (
        '- End this slide with micro-tension that makes the viewer need the next slide.\n'
        '- This slide must NOT work as standalone content - it must require slide '
        + str(slide_number + 1) + ' to resolve.\n'
    ) if not is_last and not is_first else ''

    cta_rule = (
        f'- CTA type for this deck: {cfg.get("cta_type", "link-in-bio")}.\n'
        '- CTA SLIDE: specific action verb + specific outcome + clinicalhours.org.\n'
        '  Not "check it out" or "learn more". Use the best_cta from research if provided.\n'
        '  Mention "free" - it neutralizes the "just another paid app" objection.\n'
    ) if is_last else ''

    voice_rule = (
        '- Active voice, present tense only. Never passive ("hours are lost" -> "you lost hours").\n'
        '- No two consecutive slides should share the same sentence structure.\n'
    )

    # JSON schema for hook slide includes hook_score
    hook_score_field = (
        ', "hook_score": 3, "hook_score_reason": "one line on why this stops the scroll"'
        if is_first else ''
    )

    prompt = ascii_safe(
        'You are writing ONE slide of a TikTok carousel for ClinicalHours.\n\n'
        + PRODUCT_CONTEXT + '\n'
        + RESEARCH_CONTEXT + '\n'
        + brief_ctx
        + format_copy_rejection_context()
        + MARKETING_PSYCHOLOGY + '\n'
        + CONCISENESS_RULES + '\n'
        + research_ctx
        + prev_ctx
        + f'Topic: {topic}\n'
        + f'Framework: {fw["name"]} - {fw["description"]}\n'
        + f'This is slide {slide_number} of 5. Role: {role}\n\n'
        + answers_ctx
        + 'RULES:\n'
        + '- Main display text: MAXIMUM 6 words. Count every word. Non-negotiable.\n'
        + '- Tone: direct, calm, founder voice. Not corporate. Not hype.\n'
        + '- ASCII only. No curly quotes, em dashes, ellipsis.\n'
        + voice_rule
        + hook_rule
        + tension_rule
        + cta_rule
        + '\nReturn valid JSON ONLY. No markdown. No explanation. Exact format:\n'
        + '{"slide_number": ' + str(slide_number) + ', '
        + '"role": "' + ascii_safe(role) + '", '
        + '"text": "max 6 words displayed on slide", '
        + '"subtext": "one sentence of context not shown on slide", '
        + '"visual_direction": "brief image composition description", '
        + '"retention_hook": "what makes the viewer swipe to next slide", '
        + '"content_pillar": "education|urgency|social-proof|validation", '
        + '"animation": "fade-in|slide-up|scale-in|slide-left"'
        + hook_score_field + '}'
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=600,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return parse_json_response(response.content[0].text)


# ── Claude: all-5-slides (batch mode) ─────────────────────────────────────────

def generate_all_slides(
    topic: str,
    framework_key: str,
    client,
    research_brief: Optional[Dict] = None,
    session_config: Optional[Dict] = None,
) -> Dict:
    fw  = FRAMEWORKS[framework_key]
    cfg = session_config or {}

    # Slide 1 is written LAST: instruct Claude to draft slides 2-5 first,
    # then craft the hook based on what the content actually delivers.
    slides_25_list = '\n'.join(
        f'  Slide {i+1}: {s["role"]}' for i, s in enumerate(fw['slides']) if i > 0
    )
    hook_role = fw['slides'][0]['role']

    research_ctx = ''
    if research_brief:
        research_ctx = (
            'RESEARCH BRIEF (use this to inform the entire carousel):\n'
            f'  Core pain: {research_brief.get("core_pain", "")}\n'
            f'  Surprising stat: {research_brief.get("surprising_stat", "")}\n'
            f'  Save-bait insight: {research_brief.get("save_bait", "")}\n'
            f'  Feature to spotlight: {research_brief.get("feature_spotlight", "")}\n'
            f'  Best CTA: {research_brief.get("best_cta", "")}\n'
            f'  Narrative arc: {research_brief.get("narrative_arc", "")}\n'
            f'  Hook options: {"; ".join(research_brief.get("hook_options", []))}\n'
        )
        if research_brief.get('hook_override'):
            research_ctx += (
                f'  HOOK ANGLE TO USE FOR SLIDE 1: {research_brief["hook_override"]}\n'
            )
        research_ctx += '\n'

    brief_ctx = ''
    if cfg:
        brief_ctx = (
            'CREATIVE BRIEF FOR THIS DECK:\n'
            f'  Target emotion: {cfg.get("target_emotion", "curiosity")}\n'
            f'  Hook type: {cfg.get("hook_type", "contrarian")} (for slide 1)\n'
            f'  CTA type: {cfg.get("cta_type", "link-in-bio")} (for slide 5)\n'
            f'  Audience: {cfg.get("audience", "pre-med undergrads applying to US medical schools")}\n\n'
        )

    banned_str = ', '.join(f'"{o}"' for o in BANNED_OPENERS[:8])

    prompt = ascii_safe(
        'You are writing a 5-slide TikTok carousel for ClinicalHours.\n\n'
        + PRODUCT_CONTEXT + '\n'
        + RESEARCH_CONTEXT + '\n'
        + brief_ctx
        + format_copy_rejection_context()
        + MARKETING_PSYCHOLOGY + '\n'
        + CONCISENESS_RULES + '\n'
        + research_ctx
        + f'Topic: {topic}\n'
        + f'Framework: {fw["name"]} - {fw["description"]}\n\n'
        + 'CRITICAL PROCESS - SLIDE 1 IS WRITTEN LAST:\n'
        + f'  Step 1: Write slides 2-5 in order:\n{slides_25_list}\n'
        + f'  Step 2: THEN write slide 1 ({hook_role}) based on what slides 2-5 actually deliver.\n'
        + '  This prevents slide 1 from overpromising what the deck cannot deliver.\n\n'
        + 'RULES (apply to all slides):\n'
        + '- Main display text: MAXIMUM 6 words per slide. Count every word. Flag if over.\n'
        + '- Tone: direct, calm, founder voice. Not corporate. Not hype.\n'
        + '- Active voice, present tense. Never passive voice.\n'
        + '- No two consecutive slides with the same sentence structure.\n'
        + '- Each slide 2-4 must create micro-tension that requires the next slide to resolve.\n'
        + '- No slide 2-4 should work as standalone content without the others.\n'
        + f'- BANNED openers for slide 1: {banned_str}.\n'
        + f'- Slide 1 hook type: {cfg.get("hook_type", "contrarian")}. '
        + '  The hook must promise exactly what slides 2-5 deliver.\n'
        + '- Slide 5 CTA: specific verb + specific outcome + clinicalhours.org. '
        + f'  CTA type: {cfg.get("cta_type", "link-in-bio")}. Mention "free".\n'
        + '- At least one slide must be save-worthy / screenshottable on its own.\n'
        + '- ASCII only.\n\n'
        + 'Return valid JSON ONLY. No markdown. Slides in final order (1-5). Format:\n'
        + '{"slides": ['
        + '{"slide_number": 1, "role": "...", "text": "...", "subtext": "...", '
        + '"visual_direction": "...", "retention_hook": "...", '
        + '"content_pillar": "education|urgency|social-proof|validation", '
        + '"animation": "fade-in|slide-up|scale-in|slide-left", '
        + '"hook_score": 3, "hook_score_reason": "..."},'
        + '{"slide_number": 2, ..., "content_pillar": "...", "animation": "...", "hook_score": null},'
        + '...], '
        + '"caption": "...", "audio_vibe": "...", "save_bait_slide": 1, '
        + '"content_pillar_mix": ["education", "urgency"]}'
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2500,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return parse_json_response(response.content[0].text)


# ── Claude: caption ────────────────────────────────────────────────────────────

def generate_caption(topic: str, slides: List[Dict], client) -> Tuple[str, str]:
    slide_texts = '\n'.join(
        f'  Slide {s["slide_number"]} [{s.get("role","")}]: "{s.get("text","")}"'
        for s in slides
    )
    prompt = ascii_safe(
        f'Based on this TikTok carousel for ClinicalHours:\n{slide_texts}\n\n'
        f'Topic: {topic}\n\n'
        'Write two things:\n'
        '1. caption: ready-to-paste TikTok caption under 150 chars. Must include clinicalhours.org '
        'and 3-5 hashtags (#premed #medschool #AMCAS #clinicalhours etc.). '
        'Use a direct opening line, not a question. Emoji are encouraged in captions.\n'
        '2. audio_vibe: trending audio vibe that matches the mood '
        '(e.g. "lo-fi study beat, calm and slow" or "ambient piano, focused energy")\n\n'
        'Return valid JSON ONLY: {"caption": "...", "audio_vibe": "..."}'
    )
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=300,
        messages=[{'role': 'user', 'content': prompt}],
    )
    data = parse_json_response(response.content[0].text)
    # Keep captions as-is (emoji + unicode are valid in TikTok captions).
    # Only audio_vibe needs ascii_safe since it may go into filenames/metadata.
    return data.get('caption', ''), ascii_safe(data.get('audio_vibe', ''))


# ── Copy approval ──────────────────────────────────────────────────────────────

def check_banned_opener(text: str) -> Optional[str]:
    """Return the matched banned opener, or None if clean."""
    t = text.lower().strip()
    for opener in BANNED_OPENERS:
        if t.startswith(opener):
            return opener
    return None


def approve_copy(slide: Dict, slide_type: str, topic: str = '') -> Optional[Dict]:
    text       = slide.get('text', '')
    word_count = len(text.split())
    signal     = RETENTION_SIGNALS.get(slide_type, 'engagement')
    pillar     = slide.get('content_pillar', '')
    hook_score = slide.get('hook_score')
    hook_reason= slide.get('hook_score_reason', '')

    # Word count warning
    wc_warn = '  *** OVER 6 WORDS - rewrite recommended' if word_count > 6 else ''

    # Banned opener warning
    banned = check_banned_opener(text)
    banned_warn = f'  *** BANNED OPENER detected: "{banned}" - rewrite' if banned else ''

    print(f'\n  Text ({word_count}w): "{text}"{wc_warn}{banned_warn}')
    print(f'  Context:        {slide.get("subtext", "")}')
    print(f'  Visual:         {slide.get("visual_direction", "")}')
    print(f'  Retention hook: {slide.get("retention_hook", "N/A")}')
    print(f'  Optimizes for:  {signal}')
    if pillar:
        print(f'  Content pillar: {pillar}')
    if hook_score:
        print(f'  Hook score:     {hook_score}/5  ({hook_reason})')

    while True:
        print('\n  [A] Approve  [R] Rewrite (logs rejection)  [E] Edit manually')
        choice = input('  > ').strip().upper()
        if choice in ('A', ''):
            return slide
        if choice == 'R':
            reason = input('  Rejection reason (press Enter to skip): ').strip()
            if topic:
                log_copy_rejection(slide, topic, reason)
                print('  Rejection logged.')
            return None
        if choice == 'E':
            new_text = input('  New text (max 6 words): ').strip()
            if new_text:
                slide['text'] = ascii_safe(new_text)
            return slide


# ── Image prompt builder ───────────────────────────────────────────────────────

def build_image_prompt(
    slide: Dict,
    slide_number: int,
    visual_style: str,
    has_screenshot: bool,
    platform: str = 'tiktok',
) -> str:
    import random as _random
    text       = ascii_safe(slide.get('text', ''))
    subtext    = ascii_safe(slide.get('subtext', ''))
    visual_dir = ascii_safe(slide.get('visual_direction', ''))
    role       = ascii_safe(slide.get('role', ''))
    is_hook    = slide_number == 1
    is_cta     = slide_number == 5

    theme      = SLIDE_THEMES.get(slide_number, SLIDE_THEMES[3])
    gradient   = theme['gradient']
    vis_type   = theme['visual']
    obj_subject = _random.choice(theme['objects']) if theme.get('objects') else ''
    style_desc = ascii_safe(VISUAL_STYLES.get(visual_style, VISUAL_STYLES['mockup']))

    if platform == 'instagram':
        canvas_spec = 'Create a landscape Instagram post image, exactly 1080 pixels wide by 810 pixels tall (4:3 ratio).'
    else:
        canvas_spec = 'Create a vertical TikTok slideshow image, exactly 1080 pixels wide by 1920 pixels tall (9:16 ratio).'

    lines = [
        canvas_spec,
        '',
        VISUAL_STYLE_GUIDE,
        '',
        f'BACKGROUND GRADIENT: {gradient}',
        '',
        f'LAYOUT COMPOSITION: {pick_layout_variant(platform)}',
        '',
    ]

    if vis_type == 'object' and obj_subject:
        lines += [
            f'FOREGROUND ELEMENT: {obj_subject}',
            '',
            OBJECT_VISUAL_SPEC,
            '',
        ]
    elif vis_type == 'device':
        lines += [
            f'DEVICE: {style_desc}',
            '',
        ]
    # vis_type == 'typography': no foreground element, just text on gradient

    lines += [
        f'HEADLINE (render exactly, DM Sans 700-800, charcoal #1A1A1A): "{text}"',
        'Place a thin 1px charcoal (#1A1A1A) horizontal rule immediately below the headline.',
        'Left-aligned, ~100px left margin. Charcoal only - no colored headline text.',
        '',
        'TYPE HIERARCHY: (1) headline DM Sans 700-800 #1A1A1A  '
        '(2) 1px charcoal rule  (3) subtext DM Sans 300 #888880  (4) URL DM Sans 500 #1A1A1A',
        '',
        'Safe zone: 150px from every edge. Nothing critical below 1720px (TikTok chrome).',
    ]

    if subtext:
        lines += [
            '',
            f'SUBTEXT (DM Sans 300, #888880, below rule, max 8 words): "{subtext}"',
        ]

    if vis_type == 'device':
        if has_screenshot:
            lines += [
                '',
                'Screenshot provided as input - place inside device screen.',
                'Keep screen light UI, do not darken. Screen is brightest element.',
            ]
        else:
            lines += [
                '',
                'Device screen: minimal light UI, white background, subtle gray elements.',
                'No ClinicalHours branding on screen unless solution reveal slide.',
            ]

    if is_hook:
        lines += [
            '',
            'SWIPE CUE: small "Swipe ->" in warm gray (#888880), lower-right, inside safe zone.',
        ]

    if is_cta:
        lines += [
            '',
            'FOOTER: "clinicalhours.org" in DM Sans 500 charcoal, at least 200px from bottom.',
        ]

    rejection_ctx = ascii_safe(format_image_rejection_context(role))
    if rejection_ctx.strip():
        lines += ['', rejection_ctx]

    lines += [
        '',
        f'MOOD: {visual_dir}',
        '',
        'NEVER: faces, additional gradients beyond the background, dark backgrounds, '
        'icons, brand bars, colored text, wood/desk/table surfaces, '
        'multiple devices, rectangular insets, TikTok chrome, watermarks.',
    ]

    return ascii_safe('\n'.join(lines))


# ── Gemini: generate image ─────────────────────────────────────────────────────

def _extract_image_bytes(response) -> Optional[bytes]:
    try:
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if not hasattr(part, 'inline_data') or not part.inline_data:
                    continue
                data = part.inline_data.data
                if not data:
                    continue
                if isinstance(data, (bytes, bytearray)):
                    return bytes(data)
                if isinstance(data, str):
                    return base64.b64decode(data)
    except Exception:
        pass
    return None


def generate_image(
    prompt: str,
    screenshot_path: Optional[Path] = None,
) -> Tuple[Optional[bytes], str]:
    """Generate image via Gemini. Returns (bytes, model_name) or (None, error_message)."""
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        return None, 'google-genai not installed. Run: pip install google-genai Pillow'

    client      = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
    safe_prompt = ascii_safe(prompt)

    try:
        contents: List = []

        if screenshot_path and screenshot_path.exists():
            try:
                import PIL.Image as PILImage
                img = PILImage.open(str(screenshot_path)).convert('RGB')
                contents.append(img)
            except Exception as img_err:
                print(f'\n    Warning: could not load {screenshot_path.name}: {img_err}')

        contents.append(safe_prompt)

        gen_config = genai_types.GenerateContentConfig(
            response_modalities=['IMAGE', 'TEXT'],
        )

        response    = client.models.generate_content(
            model=GEMINI_PRIMARY,
            contents=contents,
            config=gen_config,
        )
        image_bytes = _extract_image_bytes(response)

        if image_bytes:
            return image_bytes, GEMINI_PRIMARY
        return None, f'No image in response from {GEMINI_PRIMARY}'

    except Exception as exc:
        return None, str(exc)


# ── Claude: refine image prompt based on rejection ────────────────────────────

def refine_image_prompt(
    original_prompt: str,
    reason: str,
    slide: Dict,
    client,
) -> str:
    """Ask Claude to rewrite the Gemini image prompt to address a specific rejection."""
    text   = ascii_safe(slide.get('text', ''))
    role   = ascii_safe(slide.get('role', ''))
    why    = ascii_safe(reason) if reason else 'not visually interesting enough - try a different composition'

    prompt = ascii_safe(
        'You are refining a Gemini image generation prompt for a TikTok slide that was rejected.\n\n'
        f'SLIDE TEXT (keep exactly): "{text}"\n'
        f'SLIDE ROLE: {role}\n'
        f'REJECTION REASON: {why}\n\n'
        'ORIGINAL PROMPT:\n' + original_prompt + '\n\n'
        'Rewrite the prompt to directly fix the rejection reason. Rules:\n'
        '- Keep the slide text, headline, subtext, gradient spec, and brand style unchanged.\n'
        '- Change only the visual composition, object/element choice, layout positioning, '
        'or specific details that caused the rejection.\n'
        '- Be more specific and concrete about the problematic area than the original.\n'
        '- Do not add new brand rules or contradict the existing style guide.\n'
        '- Return the improved prompt text only. No explanation, no preamble.\n'
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return ascii_safe(response.content[0].text.strip())


# ── Auto-critique (Claude vision) ─────────────────────────────────────────────

def _detect_mime(image_bytes: bytes) -> str:
    """Detect image MIME type from magic bytes."""
    if image_bytes[:3] == b'\xff\xd8\xff':
        return 'image/jpeg'
    return 'image/png'


def critique_slide_image(
    image_bytes: bytes,
    slide: Dict,
    slide_number: int,
    framework_key: str,
    previous_slide_visuals: List[str],
    client,
) -> Dict:
    """
    Claude vision call: analyze a generated image and return critique + refined_prompt.
    Lean context only - no product background injected.
    Returns {issues[], similarity_flags[], marketing_verdict, refined_prompt}.
    """
    fw        = FRAMEWORKS.get(framework_key, {})
    slide_def = fw.get('slides', [{}] * 5)[slide_number - 1] if fw.get('slides') else {}
    role      = ascii_safe(slide.get('role', slide_def.get('role', '')))
    goal_type = ascii_safe(slide_def.get('type', 'slide'))
    text      = ascii_safe(slide.get('text', ''))
    subtext   = ascii_safe(slide.get('subtext', ''))

    prev_ctx = ''
    if previous_slide_visuals:
        prev_ctx = 'Previously completed slides in this deck (check for visual similarity):\n'
        for desc in previous_slide_visuals:
            prev_ctx += f'  {desc}\n'
        prev_ctx += '\n'

    brand_ctx = ascii_safe(
        'CLINICALHOURS BRAND PALETTE (mandatory — every refined_prompt MUST use these):\n'
        '  coral    #C6837A  — warm dusty rose, use for warm-dominant gradients\n'
        '  peach    #D8A68E  — sandy peach, pairs with pearl for soft warmth\n'
        '  lavender #BFC9D6  — cool pale blue, use for calm/clarity slides\n'
        '  slate    #565D6D  — deep blue-gray, use as a dark anchor or vignette edge\n'
        '  pearl    #E8EBF2  — off-white, always the gradient midpoint or light terminus\n'
        'ALLOWED GRADIENT PATTERNS (vary per slide, never repeat the same pattern twice):\n'
        '  - coral top-left -> pearl center -> off-white #F5F2EE bottom-right\n'
        '  - peach right-edge -> pearl -> off-white left-edge\n'
        '  - lavender top -> pearl -> off-white bottom\n'
        '  - slate edge vignette -> pearl center (radial)\n'
        '  - coral top -> lavender bottom (diagonal, for contrast slides)\n'
        '  - peach top-left -> lavender bottom-right (warm-to-cool diagonal)\n'
        'FORBIDDEN in refined_prompt: dark backgrounds, gray backgrounds, black, '
        'navy, teal, generic "neutral" gradients, gradients not from the palette above.\n'
        'TYPOGRAPHY (non-negotiable): DM Sans 700-800 charcoal #1A1A1A. No colored text.\n'
    )

    prompt_text = ascii_safe(
        f'You are a conversion-focused visual marketing director reviewing a TikTok '
        f'slideshow image for a pre-med SaaS product (ClinicalHours).\n\n'
        f'SLIDE ROLE: {role}\n'
        f'SLIDE TYPE / GOAL: {goal_type}\n'
        f'COPY TEXT on slide (headline): "{text}"\n'
        f'SUBTEXT: "{subtext}"\n\n'
        + prev_ctx
        + brand_ctx + '\n'
        + 'Evaluate on exactly 6 criteria. Think like a marketer first — '
        'does this image stop a pre-med scrolling TikTok and make them feel the pain/relief?\n\n'
        '1. WORD COUNT: Is the headline text visible? Does it exceed 6 words?\n'
        '2. TEXT HIERARCHY: Is headline dominant? Is there clutter reducing scan speed?\n'
        '3. SCREENSHOT: Should a product screenshot appear for this slide role? '
        'If yes, is placement correct and prominent?\n'
        '4. MARKETING FIT: Does the visual composition viscerally serve the slide\'s '
        'emotional goal? Would a pre-med stop scrolling for this image?\n'
        '5. VISUAL SIMILARITY: Too similar to previously completed slides? '
        'Same object, composition, or color zone?\n'
        '6. COLOR BRAND FIT: Does the gradient use ClinicalHours brand palette colors? '
        'Dark gray, black, or off-brand gradients are a FAIL. '
        'Must use coral, peach, lavender, slate, or pearl from the palette above.\n\n'
        'Return valid JSON ONLY. No markdown. No explanation outside the JSON.\n'
        '{\n'
        '  "issues": ["specific issue 1", "specific issue 2"],\n'
        '  "similarity_flags": ["Slide N looks similar because ..."],\n'
        '  "marketing_verdict": "one sentence on marketing impact for pre-med audience",\n'
        '  "refined_prompt": "complete improved image generation prompt — '
        'MUST specify a brand-palette gradient from the allowed patterns above, '
        'MUST think from a marketing conversion standpoint, '
        'MUST be a complete standalone prompt the image model can act on directly"\n'
        '}\n'
        'The refined_prompt must always be complete and standalone. '
        'It must open by specifying the exact gradient using brand hex values. '
        'It must include DM Sans charcoal typography spec. '
        'It must never use dark/gray/black/teal backgrounds.'
    )

    img_b64   = base64.b64encode(image_bytes).decode('ascii')
    mime_type = _detect_mime(image_bytes)

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1200,
        messages=[{
            'role': 'user',
            'content': [
                {
                    'type': 'image',
                    'source': {
                        'type': 'base64',
                        'media_type': mime_type,
                        'data': img_b64,
                    },
                },
                {'type': 'text', 'text': prompt_text},
            ],
        }],
    )
    try:
        return parse_json_response(response.content[0].text)
    except Exception:
        return {
            'issues': [],
            'similarity_flags': [],
            'marketing_verdict': 'critique parse failed',
            'refined_prompt': '',
        }


def amplify_user_rejection(
    current_prompt: str,
    user_reason: str,
    critique_result: Dict,
    slide: Dict,
    client,
) -> str:
    """
    Claude amplifies the user's rejection reason and merges it with the auto-critique
    issues to produce a fully rewritten image prompt.
    """
    text       = ascii_safe(slide.get('text', ''))
    role       = ascii_safe(slide.get('role', ''))
    issues     = critique_result.get('issues', [])
    issues_str = '\n'.join(f'  - {i}' for i in issues) if issues else '  (none)'
    why        = ascii_safe(user_reason) if user_reason else 'not working visually'

    prompt = ascii_safe(
        'You are rewriting a Gemini image generation prompt after a user rejection.\n\n'
        f'SLIDE TEXT (preserve exactly in the new prompt): "{text}"\n'
        f'SLIDE ROLE: {role}\n\n'
        f'USER REJECTION REASON: {why}\n\n'
        f'AUTO-CRITIQUE ISSUES ALREADY IDENTIFIED:\n{issues_str}\n\n'
        'CURRENT PROMPT:\n' + current_prompt + '\n\n'
        'Rewrite the full prompt to fix both the user rejection reason and the '
        'auto-critique issues simultaneously. '
        'Preserve: brand style, gradient spec, typography rules, and the exact slide text. '
        'Change: visual composition, object/element choice, layout, or approach as needed. '
        'Return the complete improved prompt only. No explanation, no preamble.'
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1500,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return ascii_safe(response.content[0].text.strip())


def generate_with_auto_critique(
    slide: Dict,
    slide_number: int,
    visual_style: str,
    screenshot_path: Optional[Path],
    output_folder: Path,
    framework_key: str,
    previous_slide_visuals: List[str],
    topic: str,
    client,
    extra_prompt: Optional[str] = None,
    skip_images: bool = False,
) -> Tuple[Optional[str], Optional[str], Optional[Dict]]:
    """
    Two-pass image generation with auto-critique between passes.
      Pass 1  ->  Gemini generates image
      Critique -> Claude vision call -> issues + refined_prompt
      Pass 2  ->  Gemini regenerates with refined_prompt (ALWAYS happens)
    Returns (filename, model_used, critique_dict).
    Third element is None when skip_images=True or on hard failure.
    """
    if skip_images:
        return None, None, None

    role_slug = SLIDE_ROLE_SLUGS.get(slide_number, 'slide')
    filename  = f'slide-{slide_number:02d}-{role_slug}.png'
    filepath  = output_folder / filename

    # Build base prompt (or use provided override for rejection loop)
    base_prompt = extra_prompt if extra_prompt else build_image_prompt(
        slide, slide_number, visual_style, bool(screenshot_path)
    )

    # ── Pass 1 ────────────────────────────────────────────────────────────────
    print(f'  Pass 1...', end='', flush=True)
    image_bytes_1, result_1 = generate_image(base_prompt, screenshot_path)
    if not image_bytes_1:
        print(f' FAILED: {result_1}')
        return None, None, None

    print(f' done [{result_1}]')

    # ── Auto-critique ─────────────────────────────────────────────────────────
    print(f'  Critiquing...', end='', flush=True)
    try:
        critique = critique_slide_image(
            image_bytes_1, slide, slide_number, framework_key,
            previous_slide_visuals, client,
        )
        print(' done.')
    except Exception as e:
        print(f' failed ({e}) — skipping critique.')
        critique = {
            'issues': [], 'similarity_flags': [],
            'marketing_verdict': '', 'refined_prompt': '',
        }

    # ── Pass 2 (always) ───────────────────────────────────────────────────────
    refined = ascii_safe(critique.get('refined_prompt', '').strip()) or base_prompt
    print(f'  Pass 2...', end='', flush=True)
    image_bytes_2, result_2 = generate_image(refined, screenshot_path)
    if not image_bytes_2:
        print(f' FAILED: {result_2} — saving pass 1 instead.')
        filepath.write_bytes(image_bytes_1)
        _open_file(filepath)
        return filename, result_1, critique

    print(f' done [{result_2}]')
    filepath.write_bytes(image_bytes_2)
    _open_file(filepath)
    return filename, result_2, critique


def run_image_approval_loop(
    slide: Dict,
    slide_number: int,
    visual_style: str,
    screenshot_path: Optional[Path],
    output_folder: Path,
    framework_key: str,
    previous_slide_visuals: List[str],
    topic: str,
    client,
    skip_images: bool = False,
) -> Tuple[Optional[str], Optional[str], Optional[Dict]]:
    """
    Interactive wrapper around generate_with_auto_critique.
    After pass 2 is shown, presents [A] Approve or [R] Reject.
    [R] -> amplify_user_rejection -> new base prompt -> repeat full 2-pass loop.
    """
    if skip_images:
        return None, None, None

    role_slug            = SLIDE_ROLE_SLUGS.get(slide_number, 'slide')
    filepath             = output_folder / f'slide-{slide_number:02d}-{role_slug}.png'
    current_base_prompt: Optional[str] = None  # None = build from template on first pass
    last_critique:       Optional[Dict] = None

    while True:
        fn, model, critique = generate_with_auto_critique(
            slide, slide_number, visual_style, screenshot_path, output_folder,
            framework_key, previous_slide_visuals, topic, client,
            extra_prompt=current_base_prompt,
        )

        if not fn:
            print('  Image generation failed.')
            print('  [R] Retry  [S] Skip this slide')
            c = input('  > ').strip().upper()
            if c == 'S':
                return None, None, None
            current_base_prompt = None
            continue

        last_critique = critique

        # Show critique summary to user
        if critique:
            issues    = critique.get('issues', [])
            sim_flags = critique.get('similarity_flags', [])
            verdict   = critique.get('marketing_verdict', '')
            if issues:
                print(f'  Auto-critique fixed: {", ".join(issues[:3])}')
            if sim_flags:
                print(f'  Similarity flags: {", ".join(sim_flags[:2])}')
            if verdict:
                print(f'  Marketing verdict: {verdict}')

        print(f'  Saved: {filepath}')
        print('  [A] Approve  [R] Reject with reason')
        c = input('  > ').strip().upper()

        if c in ('A', ''):
            return fn, model, last_critique

        if c == 'R':
            reason = input('  Rejection reason: ').strip()
            log_image_rejection(slide, slide_number, reason)
            print('  Claude amplifying rejection...', end='', flush=True)
            try:
                base_for_amplify   = current_base_prompt or build_image_prompt(
                    slide, slide_number, visual_style, bool(screenshot_path)
                )
                current_base_prompt = amplify_user_rejection(
                    base_for_amplify, reason, last_critique or {}, slide, client
                )
                print(' done.')
            except Exception as e:
                print(f' failed ({e}). Rebuilding from template.')
                current_base_prompt = None
            filepath.unlink(missing_ok=True)
            continue


# ── Image: generate + approve loop (kept, no longer called) ───────────────────

def generate_and_approve(
    slide: Dict,
    slide_number: int,
    visual_style: str,
    screenshot_path: Optional[Path],
    output_folder: Path,
    skip_images: bool,
    batch_mode: bool,
    topic: str = '',
    client=None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if skip_images:
        return None, None, 'skipped'

    role_slug     = SLIDE_ROLE_SLUGS.get(slide_number, 'slide')
    filename      = f'slide-{slide_number:02d}-{role_slug}.png'
    refined_prompt: Optional[str] = None  # set by [X] rejection; cleared by [R]

    while True:
        # Use Claude-refined prompt if available, otherwise build fresh from template
        if refined_prompt:
            img_prompt = refined_prompt
        else:
            img_prompt = build_image_prompt(slide, slide_number, visual_style, bool(screenshot_path))

        print(f'  Generating image...', end='', flush=True)
        image_bytes, result = generate_image(img_prompt, screenshot_path)

        if not image_bytes:
            print(f' FAILED: {result}')
            if batch_mode:
                return None, None, result
            print('  [R] Retry  [S] Skip this slide')
            c = input('  > ').strip().upper()
            if c == 'S':
                return None, None, result
            refined_prompt = None  # reset on retry
            continue

        print(f' done [{result}]')
        filepath = output_folder / filename
        filepath.write_bytes(image_bytes)
        _open_file(filepath)

        if batch_mode:
            return filename, result, None

        print(f'  Saved: {filepath}')
        print('  [A] Approve  [R] Regenerate (new variant)  [X] Reject (Claude refines prompt)  [S] Skip')
        c = input('  > ').strip().upper()
        if c == 'R':
            refined_prompt = None  # discard any refined prompt, pick fresh layout variant
            filepath.unlink(missing_ok=True)
            continue
        if c == 'X':
            reason = input('  What was wrong with it? (press Enter to skip): ').strip()
            log_image_rejection(slide, slide_number, reason)
            if client:
                print('  Claude is rewriting the prompt...', end='', flush=True)
                try:
                    refined_prompt = refine_image_prompt(img_prompt, reason, slide, client)
                    print(' done.')
                except Exception as e:
                    print(f' failed ({e}). Falling back to template rebuild.')
                    refined_prompt = None
            else:
                refined_prompt = None
            filepath.unlink(missing_ok=True)
            continue
        return filename, result, None


# ── Output helpers ─────────────────────────────────────────────────────────────

def make_output_folder(topic: str, framework_key: str) -> Path:
    folder = BASE_DIR / f'{datetime.now().strftime("%Y-%m-%d")}_{framework_key}_{slugify(topic)}'
    folder.mkdir(parents=True, exist_ok=True)
    _open_folder(folder)
    return folder


def save_caption_file(folder: Path, slides: List[Dict], caption: str, audio_vibe: str) -> None:
    lines = [
        '=== TikTok Caption (copy-paste ready) ===',
        ascii_safe(caption),
        '',
        f'Suggested audio vibe: {ascii_safe(audio_vibe)}',
        '',
        '=== Slide Texts ===',
    ]
    for s in slides:
        lines.append(
            f'Slide {s["slide_number"]} ({ascii_safe(s.get("role", ""))}): '
            f'{ascii_safe(s.get("text", ""))}'
        )
        rh = s.get('retention_hook', '')
        if rh:
            lines.append(f'  Retention hook: {ascii_safe(rh)}')
    (folder / 'caption.txt').write_text('\n'.join(lines), encoding='utf-8')


def save_metadata_file(folder: Path, data: Dict) -> None:
    (folder / 'metadata.json').write_text(
        json.dumps(data, indent=2, ensure_ascii=True), encoding='utf-8'
    )


def append_to_index(folder_name: str, topic: str, framework_name: str, caption: str) -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    entry = (
        f'- **{datetime.now().strftime("%Y-%m-%d")}** | '
        f'{ascii_safe(topic)} | {framework_name} | `{folder_name}` | '
        f'{ascii_safe(caption.split(chr(10))[0][:120])}\n'
    )
    with open(INDEX_FILE, 'a', encoding='utf-8') as f:
        f.write(entry)


def open_command(path: Path) -> str:
    s = platform.system()
    if s == 'Darwin':  return f'open "{path}"'
    if s == 'Windows': return f'explorer "{path}"'
    return f'xdg-open "{path}"'


def _open_file(path: Path) -> None:
    """Open a file immediately with the OS default viewer (silent, non-blocking)."""
    import subprocess
    try:
        s = platform.system()
        if s == 'Darwin':
            subprocess.Popen(['open', str(path)])
        elif s == 'Windows':
            os.startfile(str(path))
        else:
            subprocess.Popen(['xdg-open', str(path)])
    except Exception:
        pass


def _open_folder(path: Path) -> None:
    """Open a folder in the OS file explorer (silent, non-blocking)."""
    import subprocess
    try:
        s = platform.system()
        if s == 'Darwin':
            subprocess.Popen(['open', str(path)])
        elif s == 'Windows':
            subprocess.Popen(['explorer', str(path)])
        else:
            subprocess.Popen(['xdg-open', str(path)])
    except Exception:
        pass


# ── Interactive prompts (framework / visual) ───────────────────────────────────

def prompt_framework(recommended: Optional[str] = None) -> str:
    print('\nChoose a marketing framework:')
    keys = list(FRAMEWORKS.keys())
    for i, k in enumerate(keys, 1):
        fw     = FRAMEWORKS[k]
        marker = ' <- recommended by research' if k == recommended else ''
        print(f'  {i}. {fw["name"]:<16s}  {fw["description"][:60]}{marker}')
    while True:
        prompt_text = f'\nEnter number (1-5)'
        if recommended and recommended in keys:
            prompt_text += f' or press Enter for {FRAMEWORKS[recommended]["name"]}'
        raw = input(prompt_text + ': ').strip()
        if not raw and recommended:
            return recommended
        if raw.isdigit() and 1 <= int(raw) <= 5:
            return keys[int(raw) - 1]
        r = normalize_framework(raw)
        if r:
            return r
        print('  Please enter a number 1-5.')


def prompt_visual() -> str:
    print('\nChoose device / layout style:')
    print('  All styles use: off-white matte (#F5F2EE), DM Sans only, charcoal text, 1px rule.')
    print('  1. Typography    - No device. Pure text. Left-aligned or centered depending on hook.')
    print('  2. Phone         - Single phone floating on off-white. Upright or 8-10 deg tilt.')
    print('  3. Laptop        - Single laptop floating on off-white. Perspective tilt 8-10 deg.')
    print('  4. Overhead      - Bird\'s eye flat lay of phone or laptop on off-white.')
    while True:
        raw = input('\nEnter number (1-4) or press Enter for Phone: ').strip()
        if not raw:                             return 'mockup'
        if raw in ('1', 'typography'):          return 'typography'
        if raw in ('2', 'mockup', 'phone'):     return 'mockup'
        if raw in ('3', 'hybrid', 'laptop'):    return 'hybrid'
        if raw in ('4', 'screenshot-focus', 'overhead'): return 'screenshot-focus'
        print('  Please enter 1, 2, 3, or 4.')


# ── Interactive slide-by-slide mode ───────────────────────────────────────────

def run_interactive(
    topic: str,
    framework_key: str,
    visual_style: str,
    client,
    skip_images: bool,
    research_brief: Optional[Dict],
    session_config: Optional[Dict] = None,
) -> None:
    fw            = FRAMEWORKS[framework_key]
    output_folder = make_output_folder(topic, framework_key)
    print(f'\nOutput folder: {output_folder}')

    slides_written: List[Dict]  = []  # grows as slides are approved
    slide_metadata: List[Dict]  = []  # final ordered list
    slide_metadata_map: Dict[int, Dict] = {}  # keyed by slide_number
    previous_slide_visuals: List[str] = []  # text descriptors for similarity check

    # Process slides 2-5 first, then slide 1 (hook written last)
    slide_order = list(range(1, len(fw['slides']))) + [0]  # [1,2,3,4,0]

    for idx in slide_order:
        slide_def    = fw['slides'][idx]
        slide_number = idx + 1
        role         = slide_def['role']
        slide_type   = slide_def['type']
        is_hook      = idx == 0

        print(f'\n{"=" * 62}')
        if is_hook:
            print(f'  SLIDE 1 / 5   [{role}]  <- HOOK (written based on slides 2-5)')
        else:
            print(f'  SLIDE {slide_number} / 5   [{role}]')
        print(f'{"=" * 62}')

        tip = SLIDE_TIPS.get(slide_type, '')
        if tip:
            print(f'  {tip}')

        questions = SLIDE_QUESTIONS.get(slide_type, [])
        answers: Dict[str, str] = {}
        for q_text, q_key, required in questions:
            suffix = '' if required else '  (press Enter to let Claude decide)'
            print(f'\n  {q_text}{suffix}')
            raw = input('  > ').strip()
            if raw:
                answers[q_key] = ascii_safe(raw)

        # Generate + approve copy loop
        slide_copy: Optional[Dict] = None
        while slide_copy is None:
            label = 'hook (slide 1)' if is_hook else f'slide {slide_number}'
            print(f'\n  Writing {label} with Claude...', end='', flush=True)
            try:
                draft = generate_single_slide(
                    topic, framework_key, idx, answers, slides_written, client,
                    research_brief, session_config, is_hook_written_last=True,
                )
                print(' done.')
                slide_copy = approve_copy(draft, slide_type, topic)
                if slide_copy is None:
                    extra = input(
                        '\n  Extra direction for the rewrite? (press Enter to skip)\n  > '
                    ).strip()
                    if extra:
                        answers['extra_direction'] = ascii_safe(extra)
            except json.JSONDecodeError as e:
                print(f' JSON parse error: {e}')
                print('  Retrying...')
            except Exception as e:
                print(f' ERROR: {e}')
                print('  [R] Retry  [Q] Quit')
                if input('  > ').strip().upper() == 'Q':
                    sys.exit(1)

        slides_written.append(slide_copy)

        # Screenshot picker
        screenshot_path: Optional[Path] = None
        if not skip_images:
            if is_hook:
                print(f'\n  Hook slide - text-only imagery recommended.')
                if input('  Use a real screenshot anyway? [y/N] ').strip().lower() == 'y':
                    screenshot_path = pick_screenshot_interactive(slide_number, slide_type)
            else:
                screenshot_path = pick_screenshot_interactive(slide_number, slide_type)

        if not skip_images:
            print()
        filename, model_used, critique = run_image_approval_loop(
            slide_copy, slide_number, visual_style,
            screenshot_path, output_folder,
            framework_key=framework_key,
            previous_slide_visuals=previous_slide_visuals,
            topic=topic,
            client=client,
            skip_images=skip_images,
        )
        error = None

        visual_desc = (
            f"Slide {slide_number} [{ascii_safe(slide_copy.get('role', ''))}]: "
            f"{ascii_safe(slide_copy.get('visual_direction', ''))}"
        )
        if filename:
            previous_slide_visuals.append(visual_desc)

        slide_metadata_map[slide_number] = {
            'slide_number':     slide_number,
            'role':             slide_copy.get('role', ''),
            'text':             slide_copy.get('text', ''),
            'subtext':          slide_copy.get('subtext', ''),
            'visual_direction': slide_copy.get('visual_direction', ''),
            'retention_hook':   slide_copy.get('retention_hook', ''),
            'content_pillar':   slide_copy.get('content_pillar', ''),
            'animation':        slide_copy.get('animation', ''),
            'hook_score':       slide_copy.get('hook_score'),
            'hook_score_reason':slide_copy.get('hook_score_reason', ''),
            'user_answers':     answers,
            'screenshot_used':  str(screenshot_path) if screenshot_path else None,
            'model_used':       model_used,
            'status':           'success' if filename else ('skipped' if skip_images else 'failed'),
            'filename':         filename,
            'auto_critique':    critique,
            'error':            error,
        }

    # Restore final order 1-5 for saving
    slide_metadata = [slide_metadata_map[i] for i in sorted(slide_metadata_map)]
    slides_for_caption = sorted(slides_written, key=lambda s: s.get('slide_number', 0))

    print(f'\n{"=" * 62}')
    print('  Generating caption...')
    caption, audio_vibe = generate_caption(topic, slides_for_caption, client)
    print(f'  Caption:    {caption}')
    print(f'  Audio vibe: {audio_vibe}')

    failed = [m['slide_number'] for m in slide_metadata if m['status'] == 'failed']
    pillars = list({m['content_pillar'] for m in slide_metadata if m.get('content_pillar')})
    save_caption_file(output_folder, slides_for_caption, caption, audio_vibe)
    save_metadata_file(output_folder, {
        'topic': topic, 'framework': framework_key,
        'framework_name': fw['name'], 'visual_style': visual_style,
        'date': datetime.now().isoformat(),
        'caption': caption, 'audio_vibe': audio_vibe,
        'content_pillars': pillars,
        'session_config': session_config,
        'research_brief': research_brief,
        'slides': slide_metadata, 'failed_slides': failed,
    })
    append_to_index(output_folder.name, topic, fw['name'], caption)

    ok = sum(1 for m in slide_metadata if m['status'] == 'success')
    print(f'\n{"=" * 62}')
    print(f'  Done: {ok}/5 images' + (f'  ({len(failed)} failed)' if failed else ''))
    print(f'{"=" * 62}')
    print(f'\nFolder:  {output_folder}')
    print(f'  {open_command(output_folder)}')


# ── Batch mode ─────────────────────────────────────────────────────────────────

def run_batch(
    topic: str,
    framework_key: str,
    visual_style: str,
    client,
    skip_images: bool,
    custom_copy_path: Optional[str],
    research_brief: Optional[Dict],
    session_config: Optional[Dict] = None,
) -> None:
    fw = FRAMEWORKS[framework_key]
    print(f'\n[1/2] Writing all 5 slides with Claude (hook written last)...')

    if custom_copy_path:
        with open(custom_copy_path, encoding='utf-8') as f:
            copy_data = json.load(f)
    else:
        copy_data = generate_all_slides(ascii_safe(topic), framework_key, client,
                                        research_brief, session_config)

    print('\n' + '-' * 62)
    print(f'SLIDE COPY  ({fw["name"].upper()})  |  visual: {visual_style}')
    print('-' * 62)
    save_bait = copy_data.get('save_bait_slide')
    for s in copy_data['slides']:
        wc      = len(s.get('text', '').split())
        text    = s.get('text', '')
        flag    = '  *** OVER 6W' if wc > 6 else ''
        banned  = check_banned_opener(text)
        bflag   = f'  *** BANNED OPENER: "{banned}"' if banned else ''
        star    = '  <- save-bait' if save_bait and s['slide_number'] == save_bait else ''
        pillar  = f'  [{s.get("content_pillar","")}]' if s.get('content_pillar') else ''
        hs      = f'  hook:{s["hook_score"]}/5' if s.get('hook_score') else ''
        print(f'Slide {s["slide_number"]}  [{s.get("role","")}]  ({wc}w){flag}{bflag}{star}{pillar}{hs}: "{text}"')
        print(f'  Context: {s.get("subtext","")}')
        if s.get('hook_score_reason'):
            print(f'  Hook reason: {s.get("hook_score_reason","")}')
        if s.get('retention_hook'):
            print(f'  Swipe trigger: {s.get("retention_hook","")}')
    print(f'\nCaption:    {copy_data.get("caption","")}')
    print(f'Audio vibe: {copy_data.get("audio_vibe","")}')
    print('-' * 62)

    output_folder = make_output_folder(topic, framework_key)
    print(f'\nOutput: {output_folder}')

    if not skip_images:
        print('\n[2/2] Generating images...')

    slide_metadata         = []
    failed                 = []
    previous_slide_visuals: List[str] = []

    for slide in copy_data['slides']:
        i           = slide['slide_number']
        slide_type  = fw['slides'][i - 1]['type']
        ss          = None if i == 1 else suggest_screenshot(slide_type)

        if not skip_images:
            ss_note = f'  [screenshot: {ss.name}]' if ss else '  [screenshot placeholder zone]'
            print(f'\n  Slide {i}/5  [{slide.get("role","")}]  {ss_note}', end='', flush=True)

        filename, model_used, critique = generate_with_auto_critique(
            slide, i, visual_style, ss, output_folder,
            framework_key=framework_key,
            previous_slide_visuals=previous_slide_visuals,
            topic=topic,
            client=client,
            skip_images=skip_images,
        )
        error = None
        if not filename and not skip_images:
            failed.append(i)

        visual_desc = (
            f"Slide {i} [{ascii_safe(slide.get('role', ''))}]: "
            f"{ascii_safe(slide.get('visual_direction', ''))}"
        )
        if filename:
            previous_slide_visuals.append(visual_desc)

        slide_metadata.append({
            'slide_number':     i,
            **{k: slide.get(k, '') for k in ['role', 'text', 'subtext', 'visual_direction', 'retention_hook']},
            'screenshot_used':  str(ss) if ss else None,
            'model_used':       model_used,
            'status':           'success' if filename else ('skipped' if skip_images else 'failed'),
            'filename':         filename,
            'auto_critique':    critique,
            'error':            error,
        })

    save_caption_file(
        output_folder, copy_data['slides'],
        copy_data.get('caption', ''), copy_data.get('audio_vibe', ''),
    )
    save_metadata_file(output_folder, {
        'topic': topic, 'framework': framework_key,
        'framework_name': fw['name'], 'visual_style': visual_style,
        'date': datetime.now().isoformat(),
        'caption': copy_data.get('caption', ''),
        'audio_vibe': copy_data.get('audio_vibe', ''),
        'research_brief': research_brief,
        'slides': slide_metadata, 'failed_slides': failed,
    })
    append_to_index(output_folder.name, topic, fw['name'], copy_data.get('caption', ''))

    ok = sum(1 for m in slide_metadata if m['status'] == 'success')
    print(f'\n{"=" * 62}')
    print(f'  Done: {ok}/5 images' + (f'  ({len(failed)} failed)' if failed else ''))
    print(f'{"=" * 62}')
    print(f'\nFolder:  {output_folder}')
    print(f'  {open_command(output_folder)}')


# ── Creative brief collection ─────────────────────────────────────────────────

def collect_session_config(args) -> Dict:
    """Collect target emotion, hook type, CTA type, audience. Uses CLI flags if set."""
    cfg: Dict[str, str] = {}

    # Helper: pick from list interactively or use CLI value
    def pick(label: str, options: List[str], default: str, cli_val: Optional[str]) -> str:
        if cli_val and cli_val.lower() in options:
            print(f'  {label}: {cli_val} (from CLI)')
            return cli_val.lower()
        print(f'\n  {label}:')
        for i, o in enumerate(options, 1):
            marker = ' (default)' if o == default else ''
            print(f'    {i}. {o}{marker}')
        raw = input(f'  Enter number or press Enter for [{default}]: ').strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        return default

    print('\n' + '─' * 62)
    print('  CREATIVE BRIEF')
    print('─' * 62)
    cfg['target_emotion'] = pick('Target emotion', TARGET_EMOTIONS, 'curiosity',
                                 getattr(args, 'emotion', None))
    cfg['hook_type']      = pick('Hook type',      HOOK_TYPES,      'contrarian',
                                 getattr(args, 'hook_type', None))
    cfg['cta_type']       = pick('CTA type',       CTA_TYPES,       'link-in-bio',
                                 getattr(args, 'cta_type', None))

    cli_audience = getattr(args, 'audience', None)
    if cli_audience:
        cfg['audience'] = cli_audience
        print(f'  Audience: {cli_audience} (from CLI)')
    else:
        print('\n  Audience specificity:')
        print('  (press Enter for default: pre-med undergrads applying to US medical schools)')
        raw = input('  > ').strip()
        cfg['audience'] = raw if raw else 'pre-med undergrads applying to US medical schools'

    print(f'\n  Brief: {cfg["target_emotion"]} | {cfg["hook_type"]} hook | '
          f'{cfg["cta_type"]} CTA | {cfg["audience"][:50]}')
    print('─' * 62)
    return cfg


# ── Topic history / dedup ─────────────────────────────────────────────────────

def check_topic_history(topic: str) -> List[str]:
    """Return previous carousel log entries that overlap with this topic."""
    if not INDEX_FILE.exists():
        return []
    topic_slug  = slugify(topic)
    topic_lower = topic.lower()
    matches: List[str] = []
    with open(INDEX_FILE, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            line_lower = line.lower()
            # Match on slug overlap or first 20 chars of topic
            if topic_slug in line_lower or topic_lower[:20] in line_lower:
                matches.append(line)
    return matches[:5]


# ── CLI args ───────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='ClinicalHours TikTok Slideshow Agent v3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent('''\
            Modes:
              Default (interactive)  Research -> slide-by-slide questions -> approve each image
              --batch                Research -> all-at-once generation
              --skip-images          Copy only: no Gemini calls (free, fast, great for testing)
              --no-research          Skip the research phase, go straight to slides
              --variations N         Batch: generate N variants with different hook angles
              --render               Pillow render pipeline: generates copy then renders PNGs via SLIDE_SPECS

            Frameworks:
              pain-hook, stat-drop, before-after, social-proof, tutorial, amcas-countdown

            Examples:
              python tiktok_agent.py
              python tiktok_agent.py --topic "premeds forget to log" --framework pain-hook
              python tiktok_agent.py --batch --topic "AMCAS deadline" --framework amcas-countdown
              python tiktok_agent.py --batch --topic "losing track of hours" --variations 3
              python tiktok_agent.py --skip-images --topic "test copy" --framework stat-drop
              python tiktok_agent.py --no-research --topic "quick test" --framework tutorial
              python tiktok_agent.py --render --topic "AMCAS deadline" --framework pain-hook
        '''),
    )
    p.add_argument('--topic',        help='Topic or angle for the slideshow')
    p.add_argument('--framework',    help='Framework: pain-hook, stat-drop, before-after, social-proof, tutorial, amcas-countdown')
    p.add_argument('--visual',       choices=['typography', 'mockup', 'hybrid', 'screenshot-focus'],
                   help='Visual style')
    p.add_argument('--batch',        action='store_true', help='All-at-once mode (no per-slide questions)')
    p.add_argument('--skip-images',  action='store_true', help='Copy only - skip Gemini entirely')
    p.add_argument('--no-research',  action='store_true', help='Skip the deep research phase')
    p.add_argument('--custom-copy',  metavar='FILE',      help='JSON with pre-written copy (batch mode only)')
    p.add_argument('--variations',   type=int, default=1, metavar='N',
                   help='Generate N carousel variants using different hook angles from the research brief (batch mode)')
    p.add_argument('--emotion',      choices=TARGET_EMOTIONS,
                   help='Target emotion: curiosity, urgency, validation, calm')
    p.add_argument('--hook-type',    choices=HOOK_TYPES, dest='hook_type',
                   help='Hook type: contrarian, stat, story-opener, question')
    p.add_argument('--cta-type',     choices=CTA_TYPES, dest='cta_type',
                   help='CTA type: link-in-bio, save, follow, comment')
    p.add_argument('--audience',     help='Audience description (default: pre-med undergrads)')
    p.add_argument('--render',       action='store_true',
                   help='Run the Pillow render pipeline: generate copy via Claude then render PNGs via SLIDE_SPECS')
    return p.parse_args()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    if getattr(args, 'render', False):
        check_copy_only_keys()
    elif args.skip_images:
        check_copy_only_keys()
    else:
        check_api_keys()

    import anthropic
    claude = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

    BASE_DIR.mkdir(parents=True, exist_ok=True)
    setup_screenshots_dir()

    mode_label = 'render' if getattr(args, 'render', False) else ('batch' if args.batch else ('copy-only' if args.skip_images else 'slide-by-slide'))
    print('=' * 62)
    print('  ClinicalHours TikTok Slideshow Agent v5')
    print(f'  Mode: {mode_label}')
    print('=' * 62)

    # Collect topic
    if args.topic:
        topic = args.topic.strip()
        print(f'\nTopic: {topic}')
    else:
        topic = input('\nEnter topic or angle: ').strip()
        if not topic:
            print('Error: topic is required.')
            sys.exit(1)

    # Topic dedup check
    prior = check_topic_history(topic)
    if prior:
        print(f'\n  Note: {len(prior)} previous carousel(s) found on a similar topic:')
        for entry in prior:
            print(f'    {entry[:110]}')
        print('  Proceed anyway? [Y/n]')
        if input('  > ').strip().lower() == 'n':
            sys.exit(0)

    # Deep research phase
    research_brief: Optional[Dict] = None
    if not args.no_research:
        print('\n  Deep research phase...')
        try:
            research_brief = research_topic(topic, claude)
            print_research_brief(research_brief)
            print('\n  Proceed with these findings? [Y/n]')
            if input('  > ').strip().lower() == 'n':
                research_brief = None
                print('  (Research discarded - proceeding without it)')
        except Exception as e:
            print(f'\n  Research failed ({e}). Proceeding without research brief.')
            research_brief = None
    else:
        print('\n  (Research phase skipped via --no-research)')

    # Collect framework
    recommended = research_brief.get('recommended_framework') if research_brief else None
    if args.framework:
        framework_key = normalize_framework(args.framework)
        if not framework_key:
            print(f"Error: Unknown framework '{args.framework}'.")
            print(f"Valid: {', '.join(FRAMEWORKS)}")
            sys.exit(1)
        print(f'Framework: {FRAMEWORKS[framework_key]["name"]}')
    else:
        framework_key = prompt_framework(recommended)

    # Collect visual style
    if args.visual:
        visual_style = args.visual
        print(f'Visual: {visual_style}')
    else:
        visual_style = prompt_visual()

    # Creative brief (emotion, hook type, CTA type, audience)
    session_config = collect_session_config(args)

    avail_ss = list_available_screenshots()
    ss_note  = f'{len(avail_ss)} screenshots available' if avail_ss else 'no screenshots (placeholder zones will be reserved)'
    print(f'\nConfig: {topic}  |  {FRAMEWORKS[framework_key]["name"]}  |  {visual_style}  |  {ss_note}')

    if getattr(args, 'render', False):
        # ── Render pipeline mode ───────────────────────────────────────────────
        # Generate copy via Claude then composite PNGs via SLIDE_SPECS + Pillow.
        print('\n[1/2] Generating copy with Claude...')
        copy_data   = generate_all_slides(ascii_safe(topic), framework_key, claude, research_brief, session_config)
        slides_copy = copy_data.get('slides', [])
        print(f'\n[2/2] Rendering {len(SLIDE_SPECS)} slides via Pillow...')
        output_folder = make_output_folder(topic, framework_key)
        run_render_pipeline(slides_copy, output_dir=output_folder)
        print(f'\nFolder: {output_folder}')
        return

    if args.batch or args.custom_copy:
        n_variations = getattr(args, 'variations', 1)
        hook_options = (research_brief or {}).get('hook_options', []) if n_variations > 1 else []

        if n_variations > 1 and hook_options:
            n_actual = min(n_variations, len(hook_options))
            print(f'\nGenerating {n_actual} carousel variants with different hook angles...')
            for i in range(n_actual):
                variant_brief = dict(research_brief) if research_brief else {}
                variant_brief['hook_override'] = hook_options[i]
                print(f'\n{"=" * 62}')
                print(f'  VARIANT {i + 1}/{n_actual}  Hook: {hook_options[i]}')
                print(f'{"=" * 62}')
                run_batch(topic, framework_key, visual_style, claude,
                          args.skip_images, args.custom_copy, variant_brief, session_config)
        else:
            run_batch(topic, framework_key, visual_style, claude,
                      args.skip_images, args.custom_copy, research_brief, session_config)
    else:
        run_interactive(topic, framework_key, visual_style, claude,
                        args.skip_images, research_brief, session_config)


if __name__ == '__main__':
    main()
