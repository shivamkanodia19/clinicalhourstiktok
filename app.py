#!/usr/bin/env python3
"""
ClinicalHours TikTok Agent — Streamlit Dashboard
Run with: streamlit run app.py
"""

import base64
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:
    pass

import anthropic
import tiktok_agent as agent

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="ClinicalHours TikTok Agent", layout="wide")

# ── Password gate ───────────────────────────────────────────────────────────────
def check_password():
    correct = st.secrets.get("APP_PASSWORD", "shivam123")
    if st.session_state.get("authenticated"):
        return True
    with st.form("login"):
        st.markdown("### ClinicalHours TikTok Agent")
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Enter"):
            if pw == correct:
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Incorrect password")
    st.stop()

check_password()


# ── Claude client ──────────────────────────────────────────────────────────────
@st.cache_resource
def get_client():
    key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not key:
        st.error("ANTHROPIC_API_KEY not set in .env")
        st.stop()
    return anthropic.Anthropic(api_key=key)

client = get_client()


# ── Session state defaults ─────────────────────────────────────────────────────
_DEFAULTS = {
    'phase': 'setup',
    'topic': '', 'framework_key': 'pain-hook', 'visual_style': 'mockup',
    'skip_images': False, 'no_research': False, 'session_config': {},
    'research_brief': None,
    'slide_order': [1, 2, 3, 4, 0],  # indices into fw['slides']
    'order_idx': 0,
    'slides_written': [], 'previous_slide_visuals': [],
    'slide_metadata_map': {}, 'output_folder': None,
    # per-slide working state
    'draft': None, 'extra_dir': '',
    'screenshot': None,
    'p1_prompt': None, 'p1_bytes': None, 'p1_model': None,
    'critique': None,
    'p2_bytes': None, 'p2_model': None, 'saved_filename': None,
    # caption
    'caption': None, 'audio_vibe': None,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Helpers ────────────────────────────────────────────────────────────────────
def cur_idx():
    return st.session_state.slide_order[st.session_state.order_idx]

def cur_sn():
    return cur_idx() + 1

def cur_def():
    return agent.FRAMEWORKS[st.session_state.framework_key]['slides'][cur_idx()]

def reset_slide():
    for k in ['draft', 'extra_dir', 'screenshot', 'p1_prompt',
              'p1_bytes', 'p1_model', 'critique', 'p2_bytes', 'p2_model', 'saved_filename']:
        st.session_state[k] = _DEFAULTS[k]

def advance_slide():
    sn   = cur_sn()
    draft = st.session_state.draft
    ss   = st.session_state.screenshot

    st.session_state.slide_metadata_map[sn] = {
        'slide_number':      sn,
        'role':              draft.get('role', '') if draft else '',
        'text':              draft.get('text', '') if draft else '',
        'subtext':           draft.get('subtext', '') if draft else '',
        'visual_direction':  draft.get('visual_direction', '') if draft else '',
        'retention_hook':    draft.get('retention_hook', '') if draft else '',
        'content_pillar':    draft.get('content_pillar', '') if draft else '',
        'animation':         draft.get('animation', '') if draft else '',
        'hook_score':        draft.get('hook_score') if draft else None,
        'hook_score_reason': draft.get('hook_score_reason', '') if draft else '',
        'screenshot_used':   str(ss) if ss else None,
        'model_used':        st.session_state.p2_model,
        'status':            'success' if st.session_state.saved_filename else
                             ('skipped' if st.session_state.skip_images else 'failed'),
        'filename':          st.session_state.saved_filename,
        'auto_critique':     st.session_state.critique,
        'error':             None,
    }
    if draft and st.session_state.saved_filename:
        desc = (f"Slide {sn} [{agent.ascii_safe(draft.get('role', ''))}]: "
                f"{agent.ascii_safe(draft.get('visual_direction', ''))}")
        st.session_state.previous_slide_visuals.append(desc)

    st.session_state.order_idx += 1
    reset_slide()
    if st.session_state.order_idx >= len(st.session_state.slide_order):
        st.session_state.phase = 'caption'
    else:
        st.session_state.phase = 'slide_copy'

def full_reset():
    for k in list(st.session_state.keys()):
        del st.session_state[k]


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🎬 TikTok Agent")

    if st.session_state.phase == 'setup':
        with st.form("setup"):
            topic      = st.text_input("Topic *", placeholder="e.g. premeds forget to log hours")
            fw_key     = st.selectbox("Framework", list(agent.FRAMEWORKS),
                                      format_func=lambda k: agent.FRAMEWORKS[k]['name'])
            vis        = st.selectbox("Visual style", list(agent.VISUAL_STYLES))
            no_res     = st.checkbox("Skip research", value=False)
            skip_imgs  = st.checkbox("Copy only (no images)", value=False)
            st.markdown("**Creative brief**")
            emotion    = st.selectbox("Emotion",   agent.TARGET_EMOTIONS)
            hook_type  = st.selectbox("Hook type", agent.HOOK_TYPES)
            cta_type   = st.selectbox("CTA type",  agent.CTA_TYPES)
            audience   = st.text_input("Audience",
                                       value="pre-med undergrads applying to US medical schools")
            go = st.form_submit_button("▶ Generate", type="primary")
            if go and topic.strip():
                st.session_state.update({
                    'topic': topic.strip(), 'framework_key': fw_key,
                    'visual_style': vis, 'skip_images': skip_imgs, 'no_research': no_res,
                    'session_config': {'target_emotion': emotion, 'hook_type': hook_type,
                                       'cta_type': cta_type, 'audience': audience},
                    'output_folder': agent.make_output_folder(topic.strip(), fw_key),
                    'phase': 'research' if not no_res else 'slide_copy',
                })
                st.rerun()
    else:
        st.markdown(f"**{st.session_state.topic}**")
        st.markdown(f"*{agent.FRAMEWORKS[st.session_state.framework_key]['name']}* · "
                    f"{st.session_state.visual_style}")
        n_done  = st.session_state.order_idx if st.session_state.phase != 'done' else 5
        st.progress(min(n_done / 5, 1.0), text=f"Slides {n_done}/5")

        for sn, meta in sorted(st.session_state.slide_metadata_map.items()):
            icon = {"success": "✅", "skipped": "⏭", "failed": "❌"}.get(meta['status'], "•")
            st.markdown(f"{icon} **{sn}** {meta.get('text','')[:28]}")

        st.divider()
        if st.button("🔄 Start over"):
            full_reset(); st.rerun()


# ── Phases ─────────────────────────────────────────────────────────────────────

# SETUP ────────────────────────────────────────────────────────────────────────
if st.session_state.phase == 'setup':
    st.title("ClinicalHours TikTok Slideshow Agent")
    st.markdown("Configure in the sidebar and click **▶ Generate** to start.")

# RESEARCH ─────────────────────────────────────────────────────────────────────
elif st.session_state.phase == 'research':
    st.title(f"Research: {st.session_state.topic}")
    if st.session_state.research_brief is None:
        with st.spinner("Running deep research with Claude..."):
            try:
                st.session_state.research_brief = agent.research_topic(
                    st.session_state.topic, client)
            except Exception as e:
                st.warning(f"Research failed: {e}"); st.session_state.research_brief = {}
        st.rerun()

    b = st.session_state.research_brief or {}
    if b:
        c1, c2 = st.columns(2)
        with c1:
            st.write(f"**Recommended:** {b.get('recommended_framework','')}")
            st.write(f"**Why:** {b.get('framework_reason','')}")
            st.write(f"**Core pain:** {b.get('core_pain','')}")
            st.write(f"**Stat:** {b.get('surprising_stat','')}")
            st.write(f"**Save-bait:** {b.get('save_bait','')}")
        with c2:
            st.write(f"**Feature:** {b.get('feature_spotlight','')}")
            st.write(f"**Best CTA:** {b.get('best_cta','')}")
            st.write(f"**Arc:** {b.get('narrative_arc','')}")
            st.write("**Hook options:**")
            for h in b.get('hook_options', []):
                st.markdown(f"• {h}")

    if st.button("Continue to slides →", type="primary"):
        st.session_state.phase = 'slide_copy'; st.rerun()

# SLIDE COPY ───────────────────────────────────────────────────────────────────
elif st.session_state.phase == 'slide_copy':
    sd   = cur_def()
    sn   = cur_sn()
    sidx = cur_idx()
    is_hook = sidx == 0

    label = f"Slide {sn}/5 — {sd['role']}"
    if is_hook: label += "  ← Hook (written last)"
    st.title(label)

    tip = agent.SLIDE_TIPS.get(sd['type'], '')
    if tip: st.info(tip)

    if st.session_state.draft is None:
        answers = {}
        if st.session_state.extra_dir:
            answers['extra_direction'] = agent.ascii_safe(st.session_state.extra_dir)
        with st.spinner("Writing copy with Claude..."):
            try:
                st.session_state.draft = agent.generate_single_slide(
                    st.session_state.topic, st.session_state.framework_key,
                    sidx, answers, st.session_state.slides_written, client,
                    st.session_state.research_brief, st.session_state.session_config,
                    is_hook_written_last=True,
                )
            except Exception as e:
                st.error(f"Copy generation failed: {e}")
                if st.button("Retry"): st.rerun()
                st.stop()
        st.rerun()

    draft = st.session_state.draft
    text  = draft.get('text', '')
    wc    = len(text.split())

    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(f"## \"{text}\"")
        st.markdown(f":{'red' if wc > 6 else 'green'}[{wc} words{'  ⚠ over limit' if wc > 6 else ' ✓'}]")
        banned = agent.check_banned_opener(text)
        if banned: st.warning(f'Banned opener: "{banned}"')
        st.markdown(f"**Subtext:** {draft.get('subtext','')}")
        st.markdown(f"**Visual:** {draft.get('visual_direction','')}")
        st.markdown(f"**Retention hook:** {draft.get('retention_hook','')}")
    with c2:
        if draft.get('hook_score'):
            st.metric("Hook score", f"{draft['hook_score']}/5")
            st.caption(draft.get('hook_score_reason',''))
        st.write(f"**Pillar:** {draft.get('content_pillar','')}")
        st.write(f"**Animation:** {draft.get('animation','')}")

    st.divider()
    extra = st.text_input("Extra direction for rewrite (optional)")

    ca, cr = st.columns(2)
    with ca:
        if st.button("✓ Approve copy", type="primary", use_container_width=True):
            st.session_state.slides_written.append(draft)
            st.session_state.extra_dir = ''
            st.session_state.phase = 'slide_screenshot'
            st.rerun()
    with cr:
        if st.button("↺ Rewrite", use_container_width=True):
            agent.log_copy_rejection(draft, st.session_state.topic, extra)
            st.session_state.extra_dir = extra
            st.session_state.draft = None
            st.rerun()

# SCREENSHOT ───────────────────────────────────────────────────────────────────
elif st.session_state.phase == 'slide_screenshot':
    sd   = cur_def()
    sn   = cur_sn()
    sidx = cur_idx()

    st.title(f"Slide {sn}/5 — Screenshot")

    if st.session_state.skip_images:
        advance_slide(); st.rerun()

    if sidx == 0:
        st.info("Hook slide — text-only is recommended.")

    available = agent.list_available_screenshots()
    options   = [None] + available
    labels    = ["(none)"] + [p.name for p in available]

    suggested = agent.SCREENSHOT_SUGGESTIONS.get(sd['type'], [])
    default   = 0
    for name in suggested:
        p = agent.SCREENSHOTS_DIR / name
        if p in available:
            default = available.index(p) + 1; break

    sel = st.selectbox("Screenshot to composite",
                       range(len(options)), index=default,
                       format_func=lambda i: labels[i])
    st.session_state.screenshot = options[sel]

    if st.button("Continue →", type="primary"):
        st.session_state.phase = 'slide_image'; st.rerun()

# IMAGE GENERATION ─────────────────────────────────────────────────────────────
elif st.session_state.phase == 'slide_image':
    sd         = cur_def()
    sn         = cur_sn()
    sidx       = cur_idx()
    draft      = st.session_state.draft
    screenshot = st.session_state.screenshot

    st.title(f"Slide {sn}/5 — Image Generation")

    if st.session_state.skip_images:
        advance_slide(); st.rerun()

    col_p1, col_crit, col_p2 = st.columns(3)

    # ── Pass 1 ──────────────────────────────────────────────────────────────
    with col_p1:
        st.subheader("Pass 1")
        if st.session_state.p1_bytes is None:
            if st.session_state.p1_prompt is None:
                st.session_state.p1_prompt = agent.build_image_prompt(
                    draft, sn, st.session_state.visual_style, bool(screenshot))
            with st.spinner("Generating..."):
                b, m = agent.generate_image(st.session_state.p1_prompt, screenshot)
                if not b:
                    st.error(f"Pass 1 failed: {m}")
                    if st.button("Retry"): st.rerun()
                    st.stop()
                st.session_state.p1_bytes = b
                st.session_state.p1_model = m
            st.rerun()
        st.image(st.session_state.p1_bytes, use_container_width=True)
        st.caption(st.session_state.p1_model)

    # ── Critique (streaming) ─────────────────────────────────────────────────
    with col_crit:
        st.subheader("Claude critique")
        if st.session_state.critique is None and st.session_state.p1_bytes is not None:
            fw_def = agent.FRAMEWORKS[st.session_state.framework_key]['slides']
            sd_def = fw_def[sidx] if sidx < len(fw_def) else {}
            prev   = ''.join(f'  {d}\n' for d in st.session_state.previous_slide_visuals)

            brand_ctx = (
                'CLINICALHOURS BRAND PALETTE (mandatory in refined_prompt):\n'
                '  coral #C6837A, peach #D8A68E, lavender #BFC9D6, '
                'slate #565D6D, pearl #E8EBF2\n'
                'ALLOWED GRADIENTS (pick one, vary per slide):\n'
                '  coral top-left->pearl->off-white #F5F2EE | '
                'peach right->pearl->off-white | '
                'lavender top->pearl->off-white | '
                'slate vignette edges->pearl center (radial) | '
                'coral top->lavender bottom | peach top-left->lavender bottom-right\n'
                'FORBIDDEN: dark/gray/black/navy/teal backgrounds. '
                'Typography: DM Sans 700-800 charcoal #1A1A1A only.\n'
            )
            crit_prompt = agent.ascii_safe(
                f'You are a conversion-focused visual marketing director reviewing a '
                f'TikTok slide for ClinicalHours (pre-med SaaS).\n\n'
                f'SLIDE ROLE: {agent.ascii_safe(draft.get("role", sd_def.get("role","")))}\n'
                f'SLIDE TYPE: {agent.ascii_safe(sd_def.get("type","slide"))}\n'
                f'COPY TEXT: "{agent.ascii_safe(draft.get("text",""))}"\n'
                f'SUBTEXT: "{agent.ascii_safe(draft.get("subtext",""))}"\n\n'
                + (f'Previously completed slides:\n{prev}\n' if prev else '')
                + brand_ctx + '\n'
                + 'Think like a marketer first. Evaluate on 6 criteria:\n'
                '1. WORD COUNT: headline visible? exceeds 6 words?\n'
                '2. TEXT HIERARCHY: clutter? headline dominant?\n'
                '3. SCREENSHOT: should one exist? placement correct?\n'
                '4. MARKETING FIT: does visual viscerally serve the emotional goal? '
                'Would a pre-med stop scrolling?\n'
                '5. VISUAL SIMILARITY: too similar to previous slides?\n'
                '6. COLOR BRAND FIT: gradient uses brand palette? '
                'Dark/gray/off-brand = FAIL.\n\n'
                'Return JSON only (no markdown):\n'
                '{"issues":[],"similarity_flags":[],'
                '"marketing_verdict":"one sentence on pre-med conversion impact",'
                '"refined_prompt":"complete standalone prompt — MUST start with brand gradient spec, '
                'MUST use brand hex values, MUST include DM Sans charcoal typography, '
                'MUST think from marketing conversion standpoint"}'
            )

            img_b64 = base64.b64encode(st.session_state.p1_bytes).decode('ascii')
            mime    = agent._detect_mime(st.session_state.p1_bytes)
            holder  = st.empty()
            full    = ""

            with client.messages.stream(
                model=agent.CLAUDE_MODEL, max_tokens=1200,
                messages=[{'role': 'user', 'content': [
                    {'type': 'image', 'source': {'type': 'base64',
                                                  'media_type': mime, 'data': img_b64}},
                    {'type': 'text',  'text': crit_prompt},
                ]}],
            ) as stream:
                for chunk in stream.text_stream:
                    full += chunk
                    holder.code(full, language="json")

            try:
                st.session_state.critique = agent.parse_json_response(full)
            except Exception:
                st.session_state.critique = {
                    'issues': [], 'similarity_flags': [],
                    'marketing_verdict': 'parse failed', 'refined_prompt': '',
                }
            st.rerun()

        crit = st.session_state.critique
        if crit:
            issues = crit.get('issues', [])
            if issues:
                st.write("**Issues:**")
                for iss in issues: st.markdown(f"• {iss}")
            else:
                st.success("No issues ✓")
            for sf in crit.get('similarity_flags', []):
                st.warning(sf)
            if crit.get('marketing_verdict'):
                st.info(crit['marketing_verdict'])

    # ── Pass 2 ──────────────────────────────────────────────────────────────
    with col_p2:
        st.subheader("Pass 2")
        if st.session_state.p2_bytes is None and st.session_state.critique is not None:
            crit    = st.session_state.critique
            refined = agent.ascii_safe((crit.get('refined_prompt') or '').strip()) \
                      or st.session_state.p1_prompt
            with st.spinner("Regenerating..."):
                b2, m2 = agent.generate_image(refined, screenshot)
                if not b2:
                    b2, m2 = st.session_state.p1_bytes, (st.session_state.p1_model or '') + ' (p1 fallback)'
                st.session_state.p2_bytes = b2
                st.session_state.p2_model = m2
                role_slug = agent.SLIDE_ROLE_SLUGS.get(sn, 'slide')
                fname     = f'slide-{sn:02d}-{role_slug}.png'
                (st.session_state.output_folder / fname).write_bytes(b2)
                st.session_state.saved_filename = fname
            st.rerun()

        if st.session_state.p2_bytes is not None:
            st.image(st.session_state.p2_bytes, use_container_width=True)
            st.caption(st.session_state.p2_model)

    # ── Approve / Reject ────────────────────────────────────────────────────
    if st.session_state.p2_bytes is not None:
        st.divider()
        ca, cr = st.columns([1, 2])
        with ca:
            if st.button("✓ Approve — next slide", type="primary", use_container_width=True):
                advance_slide(); st.rerun()
        with cr:
            reason = st.text_input("Rejection reason", key=f"rej_{sn}")
            if st.button("✗ Reject — regenerate", use_container_width=True):
                agent.log_image_rejection(draft, sn, reason)
                base = st.session_state.p1_prompt or agent.build_image_prompt(
                    draft, sn, st.session_state.visual_style, bool(screenshot))
                with st.spinner("Claude amplifying rejection..."):
                    try:
                        st.session_state.p1_prompt = agent.amplify_user_rejection(
                            base, reason, st.session_state.critique or {}, draft, client)
                    except Exception:
                        st.session_state.p1_prompt = None
                # Reset image state
                for k in ['p1_bytes', 'p1_model', 'critique', 'p2_bytes', 'p2_model', 'saved_filename']:
                    st.session_state[k] = _DEFAULTS[k]
                st.rerun()

# CAPTION ──────────────────────────────────────────────────────────────────────
elif st.session_state.phase == 'caption':
    st.title("Generating caption...")
    if st.session_state.caption is None:
        slides_sorted = sorted(st.session_state.slides_written,
                                key=lambda s: s.get('slide_number', 0))
        with st.spinner("Writing caption with Claude..."):
            cap, vibe = agent.generate_caption(st.session_state.topic, slides_sorted, client)
            st.session_state.caption    = cap
            st.session_state.audio_vibe = vibe

        slide_meta = [st.session_state.slide_metadata_map[i]
                      for i in sorted(st.session_state.slide_metadata_map)]
        fw = agent.FRAMEWORKS[st.session_state.framework_key]
        failed = [m['slide_number'] for m in slide_meta if m['status'] == 'failed']

        agent.save_caption_file(st.session_state.output_folder, slides_sorted, cap, vibe)
        agent.save_metadata_file(st.session_state.output_folder, {
            'topic': st.session_state.topic,
            'framework': st.session_state.framework_key,
            'framework_name': fw['name'],
            'visual_style': st.session_state.visual_style,
            'session_config': st.session_state.session_config,
            'research_brief': st.session_state.research_brief,
            'caption': cap, 'audio_vibe': vibe,
            'slides': slide_meta, 'failed_slides': failed,
        })
        agent.append_to_index(st.session_state.output_folder.name,
                              st.session_state.topic, fw['name'], cap)
        st.session_state.phase = 'done'
        st.rerun()

# DONE ─────────────────────────────────────────────────────────────────────────
elif st.session_state.phase == 'done':
    st.title("✅ Deck complete!")
    st.success(f"Saved to: {st.session_state.output_folder}")

    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("Caption")
        st.code(st.session_state.caption or '', language=None)
    with c2:
        st.subheader("Audio vibe")
        st.write(st.session_state.audio_vibe or '')

    st.subheader("Slides")
    slide_meta = [st.session_state.slide_metadata_map[i]
                  for i in sorted(st.session_state.slide_metadata_map)]
    cols = st.columns(len(slide_meta))
    for i, meta in enumerate(slide_meta):
        with cols[i]:
            st.caption(f"**{meta['slide_number']}** — {meta.get('text','')[:22]}")
            if meta.get('filename'):
                fp = st.session_state.output_folder / meta['filename']
                if fp.exists():
                    st.image(str(fp), use_container_width=True)
                    crit = meta.get('auto_critique') or {}
                    if crit.get('marketing_verdict'):
                        st.caption(crit['marketing_verdict'][:60])
            else:
                st.write(f"*{meta['status']}*")

    if st.button("▶ Make another deck", type="primary"):
        full_reset(); st.rerun()
