#!/usr/bin/env python3
"""
ClinicalHours TikTok Agent — Streamlit Dashboard
Run with: streamlit run app.py
"""

import base64
import json
import os
import sys
from pathlib import Path

import streamlit as st

try:
    from streamlit_javascript import st_javascript as _st_js
    _HAS_ST_JS = True
except ImportError:
    _HAS_ST_JS = False

sys.path.insert(0, str(Path(__file__).parent))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
except ImportError:
    pass

import anthropic
import tiktok_agent as agent

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="ClinicalHours TikTok Agent", layout="wide", page_icon="🎬")

# ── Global styles ───────────────────────────────────────────────────────────────
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">

<style>
/* ── Variables ── */
:root {
  --coral:   #C6837A;
  --peach:   #D8A68E;
  --lavender:#BFC9D6;
  --slate:   #565D6D;
  --pearl:   #E8EBF2;
  --cream:   #F8F5F1;
  --charcoal:#1A1A1A;
  --sidebar-bg: #16202E;
  --sidebar-text: #E8EBF2;
  --card-bg: #FFFFFF;
  --radius:  10px;
  --shadow:  0 2px 12px rgba(0,0,0,0.07);
}

/* ── Global font ── */
html, body, [class*="css"] {
  font-family: 'DM Sans', sans-serif !important;
}

/* ── Main area background ── */
.stApp {
  background: var(--cream) !important;
}

/* ── Global dark text for main content ── */
[data-testid="stMain"] p,
[data-testid="stMain"] span,
[data-testid="stMain"] label,
[data-testid="stMain"] div,
[data-testid="stMain"] h1,
[data-testid="stMain"] h2,
[data-testid="stMain"] h3,
[data-testid="stMain"] input,
[data-testid="stMain"] textarea,
[data-testid="stMain"] [class*="st-"],
[data-testid="stMain"] [data-testid] {
  color: var(--charcoal) !important;
}

/* ── Sidebar: dark navy ── */
[data-testid="stSidebar"] {
  background: var(--sidebar-bg) !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] div,
[data-testid="stSidebar"] a {
  color: var(--sidebar-text) !important;
}
[data-testid="stSidebar"] .stButton > button {
  background: rgba(255,255,255,0.06) !important;
  border: 1px solid rgba(255,255,255,0.12) !important;
  color: var(--sidebar-text) !important;
  border-radius: 8px !important;
  font-weight: 500 !important;
  transition: background 0.2s !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: rgba(198,131,122,0.25) !important;
  border-color: var(--coral) !important;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: var(--coral) !important;
  border-color: var(--coral) !important;
  color: #fff !important;
}
[data-testid="stSidebar"] [data-testid="stTextInput"] input,
[data-testid="stSidebar"] [data-testid="stSelectbox"] div,
[data-testid="stSidebar"] [data-testid="stSelectbox"] select {
  background: rgba(255,255,255,0.07) !important;
  border-color: rgba(255,255,255,0.15) !important;
  color: var(--sidebar-text) !important;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stRadio label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span {
  color: rgba(232,235,242,0.85) !important;
}
[data-testid="stSidebar"] hr {
  border-color: rgba(255,255,255,0.1) !important;
}
[data-testid="stSidebar"] .stProgress > div > div > div > div {
  background: var(--coral) !important;
}
[data-testid="stSidebar"] .stProgress > div > div {
  background: rgba(255,255,255,0.1) !important;
}

/* ── Main buttons ── */
.stButton > button {
  border-radius: 8px !important;
  font-family: 'DM Sans', sans-serif !important;
  font-weight: 600 !important;
  font-size: 14px !important;
  padding: 10px 20px !important;
  border: 1.5px solid transparent !important;
  transition: all 0.18s ease !important;
  letter-spacing: 0.01em !important;
}
.stButton > button[kind="primary"] {
  background: var(--coral) !important;
  border-color: var(--coral) !important;
  color: #fff !important;
  box-shadow: 0 2px 8px rgba(198,131,122,0.35) !important;
}
.stButton > button[kind="primary"]:hover {
  background: #B8726A !important;
  box-shadow: 0 4px 16px rgba(198,131,122,0.45) !important;
  transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"] {
  background: transparent !important;
  border-color: var(--slate) !important;
  color: var(--charcoal) !important;
}
.stButton > button[kind="secondary"]:hover {
  border-color: var(--coral) !important;
  color: var(--coral) !important;
  background: rgba(198,131,122,0.05) !important;
}

/* ── Text inputs & selects ── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea {
  border-radius: 8px !important;
  border: 1.5px solid #DDD8D2 !important;
  font-family: 'DM Sans', sans-serif !important;
  font-size: 14px !important;
  background: #fff !important;
  transition: border-color 0.15s !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
  border-color: var(--coral) !important;
  box-shadow: 0 0 0 3px rgba(198,131,122,0.12) !important;
}

/* ── Headers ── */
h1 {
  font-family: 'Instrument Serif', Georgia, serif !important;
  font-size: 2rem !important;
  font-weight: 400 !important;
  color: var(--charcoal) !important;
  letter-spacing: -0.01em !important;
}
h2 {
  font-family: 'DM Sans', sans-serif !important;
  font-size: 1.1rem !important;
  font-weight: 700 !important;
  color: var(--charcoal) !important;
  text-transform: uppercase !important;
  letter-spacing: 0.08em !important;
}
h3 {
  font-family: 'Instrument Serif', Georgia, serif !important;
  font-weight: 400 !important;
  font-size: 1.3rem !important;
}

/* ── Progress bar ── */
.stProgress > div > div > div > div {
  background: var(--coral) !important;
  border-radius: 99px !important;
}
.stProgress > div > div {
  border-radius: 99px !important;
}

/* ── Metric cards ── */
[data-testid="metric-container"] {
  background: var(--card-bg) !important;
  border: 1px solid #EDE9E3 !important;
  border-radius: var(--radius) !important;
  padding: 16px !important;
  box-shadow: var(--shadow) !important;
}
[data-testid="metric-container"] label {
  font-size: 11px !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.1em !important;
  color: var(--slate) !important;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
  font-family: 'Instrument Serif', serif !important;
  font-size: 2rem !important;
  color: var(--coral) !important;
}

/* ── Expanders ── */
[data-testid="stExpander"] {
  border: 1px solid #EDE9E3 !important;
  border-radius: var(--radius) !important;
  background: var(--card-bg) !important;
  box-shadow: var(--shadow) !important;
  margin-bottom: 8px !important;
}
[data-testid="stExpander"] summary {
  font-weight: 600 !important;
  padding: 14px 16px !important;
}

/* ── Info / success / warning banners ── */
[data-testid="stAlert"] {
  border-radius: var(--radius) !important;
  border-left-width: 4px !important;
}

/* ── Divider ── */
hr {
  border-color: #EDE9E3 !important;
  margin: 20px 0 !important;
}

/* ── Code blocks (captions) ── */
[data-testid="stCode"] {
  border-radius: var(--radius) !important;
  font-size: 13px !important;
}

/* ── Spinner ── */
.stSpinner > div {
  border-top-color: var(--coral) !important;
}

/* ── Image containers ── */
[data-testid="stImage"] img {
  border-radius: var(--radius) !important;
  box-shadow: var(--shadow) !important;
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--lavender); border-radius: 99px; }
::-webkit-scrollbar-thumb:hover { background: var(--slate); }
</style>
""", unsafe_allow_html=True)

# ── Password gate ───────────────────────────────────────────────────────────────
def check_password():
    try:
        correct = st.secrets.get("APP_PASSWORD") or os.environ.get("APP_PASSWORD", "")
    except Exception:
        correct = os.environ.get("APP_PASSWORD", "")
    if not correct:
        return True  # No password configured — open access
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
    'page': 'agent', 'phase': 'setup',
    'topic': '', 'framework_key': 'pain-hook', 'visual_style': 'mockup',
    'skip_images': False, 'no_research': False, 'platform': 'tiktok', 'session_config': {},
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

# ── Tier 1 style rules — localStorage + file fallback ─────────────────────────
# Primary:  browser localStorage via streamlit-javascript (private per-browser)
# Fallback: style_rules_personal.json in project dir (used when package not installed)
# Session-state is the source of truth after initial load; backends are write-through.
_LS_KEY           = 'clinicalhours_style_rules'
_RULES_FILE       = Path(__file__).parent / 'style_rules_personal.json'

def _file_load_rules() -> list:
    try:
        if _RULES_FILE.exists():
            return json.loads(_RULES_FILE.read_text(encoding='utf-8'))
    except Exception:
        pass
    return []

def _file_save_rules(rules: list) -> None:
    try:
        _RULES_FILE.write_text(json.dumps(rules, indent=2), encoding='utf-8')
    except Exception:
        pass

if 'personal_rules' not in st.session_state:
    st.session_state.personal_rules = []
if '_ls_loaded' not in st.session_state:
    st.session_state._ls_loaded = False

# File fallback: load immediately on first run (synchronous, no async needed)
if not _HAS_ST_JS and not st.session_state._ls_loaded:
    st.session_state.personal_rules = _file_load_rules()
    st.session_state._ls_loaded = True

# localStorage: render read component once; returns 0 first call, value on next rerun
if _HAS_ST_JS and not st.session_state._ls_loaded:
    _rules_raw = _st_js(f"localStorage.getItem('{_LS_KEY}') || '[]'", key='_ls_read_rules')
    if isinstance(_rules_raw, str) and _rules_raw:
        try:
            _loaded = json.loads(_rules_raw)
            if isinstance(_loaded, list):
                st.session_state.personal_rules = _loaded
                st.session_state._ls_loaded = True
        except Exception:
            st.session_state._ls_loaded = True


def _save_personal_rules(rules: list) -> None:
    """Write-through: update session_state, localStorage (if available), and file fallback."""
    st.session_state.personal_rules = rules
    st.session_state._ls_loaded = True
    st.session_state['_ls_write_ctr'] = st.session_state.get('_ls_write_ctr', 0) + 1
    if _HAS_ST_JS:
        _st_js(f"localStorage.setItem('{_LS_KEY}', {json.dumps(json.dumps(rules))})",
               key=f'_ls_write_{st.session_state["_ls_write_ctr"]}')
    else:
        _file_save_rules(rules)


# ── UI helpers ─────────────────────────────────────────────────────────────────
def phase_bar(current: str):
    """Render a horizontal step tracker for the generation flow."""
    steps = [
        ('setup',            '1', 'Setup'),
        ('research',         '2', 'Research'),
        ('slide_copy',       '3', 'Copy'),
        ('slide_screenshot', '4', 'Screenshot'),
        ('slide_image',      '5', 'Image'),
        ('caption',          '6', 'Caption'),
        ('done',             '✓', 'Done'),
    ]
    phase_order = [s[0] for s in steps]
    try:
        cur_pos = phase_order.index(current)
    except ValueError:
        cur_pos = 0

    items_html = ''
    for i, (phase, num, label) in enumerate(steps):
        if i < cur_pos:
            cls = 'done'
        elif i == cur_pos:
            cls = 'active'
        else:
            cls = 'upcoming'
        dot = '✓' if i < cur_pos else num
        items_html += f'<div class="step {cls}"><span class="dot">{dot}</span><span class="lbl">{label}</span></div>'
        if i < len(steps) - 1:
            line_cls = 'line-done' if i < cur_pos else 'line'
            items_html += f'<div class="{line_cls}"></div>'

    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:0;margin:0 0 28px;padding:18px 24px;
                background:#fff;border-radius:12px;border:1px solid #EDE9E3;
                box-shadow:0 1px 6px rgba(0,0,0,0.05);">
      {items_html}
    </div>
    <style>
    .step {{display:flex;flex-direction:column;align-items:center;gap:4px;min-width:52px;}}
    .step .dot {{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;
                 justify-content:center;font-size:12px;font-weight:700;transition:all .2s;}}
    .step .lbl {{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;white-space:nowrap;}}
    .step.done .dot  {{background:#C6837A;color:#fff;}}
    .step.done .lbl  {{color:#C6837A;}}
    .step.active .dot{{background:#1A1A1A;color:#fff;box-shadow:0 2px 8px rgba(26,26,26,.25);}}
    .step.active .lbl{{color:#1A1A1A;}}
    .step.upcoming .dot{{background:#F0ECE8;color:#999;}}
    .step.upcoming .lbl{{color:#BBB;}}
    .line      {{flex:1;height:2px;background:#EDE9E3;margin-bottom:16px;min-width:8px;}}
    .line-done {{flex:1;height:2px;background:#C6837A;margin-bottom:16px;min-width:8px;}}
    </style>
    """, unsafe_allow_html=True)


def slide_headline(text: str, word_count: int, banned: str | None = None,
                   hook_score: int | None = None, hook_reason: str = ''):
    """Render the slide headline at editorial scale."""
    wc_color  = '#E05C52' if word_count > 6 else '#3AA66B'
    wc_label  = f'{word_count}w {"⚠ over" if word_count > 6 else "✓"}'
    score_html = ''
    if hook_score:
        stars = '★' * hook_score + '☆' * (5 - hook_score)
        score_html = f'<span style="font-size:13px;color:#C6837A;margin-left:12px;" title="{hook_reason}">{stars}</span>'
    banned_html = ''
    if banned:
        banned_html = f'<div style="margin-top:10px;padding:8px 14px;background:#FFF0EF;border-left:3px solid #E05C52;border-radius:6px;font-size:13px;color:#C23B31;">⚠ Banned opener: "{banned}"</div>'
    st.markdown(f"""
    <div style="padding:36px 40px;background:#fff;border-radius:14px;
                border:1px solid #EDE9E3;box-shadow:0 2px 16px rgba(0,0,0,0.07);
                margin-bottom:20px;">
      <div style="font-family:'Instrument Serif',Georgia,serif;font-size:2.6rem;
                  line-height:1.2;color:#1A1A1A;letter-spacing:-0.01em;margin-bottom:16px;">
        "{text}"
      </div>
      <div style="display:flex;align-items:center;gap:8px;">
        <span style="display:inline-flex;align-items:center;padding:3px 10px;
                     border-radius:99px;background:{wc_color}1A;border:1px solid {wc_color}40;
                     font-size:12px;font-weight:700;color:{wc_color};">{wc_label}</span>
        {score_html}
      </div>
      {banned_html}
    </div>
    """, unsafe_allow_html=True)


def field_card(fields: list[tuple[str, str]]):
    """Render a list of (label, value) pairs as a compact card."""
    rows = ''.join(
        f'<div style="display:flex;gap:12px;padding:9px 0;border-bottom:1px solid #F0EDE8;">'
        f'<span style="width:130px;font-size:11px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:.07em;color:#888;flex-shrink:0;">{lbl}</span>'
        f'<span style="font-size:14px;color:#1A1A1A;">{val}</span></div>'
        for lbl, val in fields
    )
    st.markdown(f"""
    <div style="background:#fff;border:1px solid #EDE9E3;border-radius:12px;
                padding:4px 18px 4px;box-shadow:0 1px 6px rgba(0,0,0,0.04);margin-bottom:16px;">
      {rows}
    </div>
    """, unsafe_allow_html=True)


# ── Helpers ─────────────────────────────────────────────────────────────────────
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
        save_partial_session()

def full_reset():
    for k in list(st.session_state.keys()):
        del st.session_state[k]


# ── Partial session persistence ─────────────────────────────────────────────────
import json as _json

_PARTIAL_FILE = 'session_partial.json'

def save_partial_session():
    """Write resumable state to output_folder/session_partial.json after each slide."""
    folder = st.session_state.get('output_folder')
    if not folder:
        return
    payload = {
        'topic':                 st.session_state.topic,
        'framework_key':         st.session_state.framework_key,
        'visual_style':          st.session_state.visual_style,
        'platform':              st.session_state.platform,
        'skip_images':           st.session_state.skip_images,
        'no_research':           st.session_state.no_research,
        'session_config':        st.session_state.session_config,
        'research_brief':        st.session_state.research_brief,
        'slides_written':        st.session_state.slides_written,
        'previous_slide_visuals': st.session_state.previous_slide_visuals,
        'slide_metadata_map':    {str(k): v for k, v in st.session_state.slide_metadata_map.items()},
        'order_idx':             st.session_state.order_idx,
        'slide_order':           st.session_state.slide_order,
        'output_folder':         str(folder),
    }
    (folder / _PARTIAL_FILE).write_text(
        _json.dumps(payload, indent=2, ensure_ascii=True), encoding='utf-8')


def resume_session(folder: Path):
    """Restore session state from a partial session file and return True on success."""
    partial_path = folder / _PARTIAL_FILE
    if not partial_path.exists():
        return False
    try:
        data = _json.loads(partial_path.read_text(encoding='utf-8'))
    except Exception:
        return False

    full_reset()
    for k, v in _DEFAULTS.items():
        st.session_state[k] = v

    st.session_state.update({
        'topic':                  data['topic'],
        'framework_key':          data['framework_key'],
        'visual_style':           data['visual_style'],
        'platform':               data.get('platform', 'tiktok'),
        'skip_images':            data.get('skip_images', False),
        'no_research':            data.get('no_research', False),
        'session_config':         data.get('session_config', {}),
        'research_brief':         data.get('research_brief'),
        'slides_written':         data.get('slides_written', []),
        'previous_slide_visuals': data.get('previous_slide_visuals', []),
        'slide_metadata_map':     {int(k): v for k, v in data.get('slide_metadata_map', {}).items()},
        'order_idx':              data.get('order_idx', 0),
        'slide_order':            data.get('slide_order', [1, 2, 3, 4, 0]),
        'output_folder':          Path(data['output_folder']),
        'phase':                  'slide_copy',
        'page':                   'agent',
        'authenticated':          True,
    })
    return True


# ── History helpers ────────────────────────────────────────────────────────────
def load_history():
    """Scan output/ and return list of deck dicts sorted newest first."""
    out_dir = Path(__file__).parent / 'output'
    decks = []
    if not out_dir.exists():
        return decks
    for folder in sorted(out_dir.iterdir(), reverse=True):
        if not folder.is_dir():
            continue
        slides = sorted(folder.glob('slide-*.png'))
        if not slides:
            continue
        caption = ''
        cap_file = folder / 'caption.txt'
        if cap_file.exists():
            caption = cap_file.read_text(encoding='utf-8', errors='ignore')
        meta = {}
        meta_file = folder / 'metadata.json'
        if meta_file.exists():
            import json
            try:
                meta = json.loads(meta_file.read_text(encoding='utf-8', errors='ignore'))
            except Exception:
                pass
        partial = (folder / _PARTIAL_FILE).exists() and not meta_file.exists()
        parts = folder.name.split('_', 2)
        date  = parts[0] if len(parts) > 0 else ''
        fw    = parts[1] if len(parts) > 1 else ''
        topic = parts[2].replace('-', ' ') if len(parts) > 2 else folder.name
        decks.append({
            'folder': folder,
            'name': folder.name,
            'date': date,
            'framework': fw,
            'topic': topic,
            'slides': slides,
            'caption': caption,
            'meta': meta,
            'resumable': partial,
        })
    return decks


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:4px 0 20px;">
      <div style="font-family:'Instrument Serif',Georgia,serif;font-size:1.35rem;
                  color:#E8EBF2;letter-spacing:-0.01em;line-height:1.2;">
        ClinicalHours
      </div>
      <div style="font-size:10px;font-weight:700;text-transform:uppercase;
                  letter-spacing:.14em;color:#C6837A;margin-top:2px;">
        TikTok Studio
      </div>
    </div>
    """, unsafe_allow_html=True)
    col_a, col_h = st.columns(2)
    with col_a:
        if st.button("Generate", use_container_width=True,
                     type="primary" if st.session_state.get('page') == 'agent' else "secondary"):
            st.session_state['page'] = 'agent'; st.rerun()
    with col_h:
        if st.button("History", use_container_width=True,
                     type="primary" if st.session_state.get('page') == 'history' else "secondary"):
            st.session_state['page'] = 'history'; st.rerun()
    st.divider()

    if st.session_state.phase != 'setup':
        # ── Session progress (active session only) ──
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

    # ── Style memory panel (always shown) ──────────────────────────────────────
    _rules = st.session_state.get('personal_rules', [])
    if _rules:
        st.divider()
        st.markdown('<div style="font-size:10px;font-weight:700;text-transform:uppercase;'
                    'letter-spacing:.12em;color:#C6837A;margin-bottom:8px;">Style Memory</div>',
                    unsafe_allow_html=True)
        for _i, _rule in enumerate(_rules):
            st.markdown(
                f'<div style="font-size:12px;color:#E8EBF2;padding:5px 0 2px;'
                f'border-bottom:1px solid rgba(255,255,255,0.07);">{_rule}</div>',
                unsafe_allow_html=True,
            )
            _pc, _dc = st.columns([3, 1])
            with _pc:
                if st.button("↑ Agent", key=f"promote_{_i}", use_container_width=True,
                             help="Bake this rule into tiktok_agent.py for everyone"):
                    _err = agent.promote_rule_to_agent(_rule)
                    if _err:
                        st.session_state['_promote_msg'] = ('error', _err)
                    else:
                        st.session_state['_promote_msg'] = ('ok', _rule)
                    st.rerun()
            if st.session_state.get('_promote_msg') and st.session_state['_promote_msg'][1] == _rule:
                _kind, _msg = st.session_state.pop('_promote_msg')
                if _kind == 'ok':
                    st.success(f"Promoted to agent: \"{_msg[:40]}\"")
                else:
                    st.error(_msg)
            with _dc:
                if st.button("✕", key=f"del_rule_{_i}", use_container_width=True):
                    _new = [r for j, r in enumerate(_rules) if j != _i]
                    _save_personal_rules(_new)
                    st.rerun()


# ── History page ───────────────────────────────────────────────────────────────
if st.session_state.get('page') == 'history':
    st.title("Past Decks")
    decks = load_history()
    if not decks:
        st.info("No completed decks found in the output folder yet.")
    else:
        n_resumable = sum(1 for d in decks if d['resumable'])
        st.caption(f"{len(decks)} deck(s) found" + (f" · {n_resumable} resumable" if n_resumable else ""))
        for deck in decks:
            status_badge = " ⏸ *in progress*" if deck['resumable'] else ""
            label = f"**{deck['date']}** · {deck['framework']} · {deck['topic'][:60]}{status_badge}"
            with st.expander(label, expanded=deck['resumable']):
                if deck['resumable']:
                    n_done = len(deck['slides'])
                    st.info(f"{n_done}/5 slides generated — session paused mid-way.")
                    if st.button("▶ Resume this session", key=f"resume_{deck['name']}", type="primary"):
                        if resume_session(deck['folder']):
                            st.rerun()
                        else:
                            st.error("Could not load session data.")
                    st.divider()
                if deck['slides']:
                    cols = st.columns(len(deck['slides']))
                    for i, slide_path in enumerate(deck['slides']):
                        with cols[i]:
                            st.image(str(slide_path), use_container_width=True)
                            st.caption(slide_path.stem)
                else:
                    st.write("*No slide images found*")
                if deck['caption']:
                    st.divider()
                    st.subheader("Caption")
                    st.code(deck['caption'], language=None)
    st.stop()


# ── Phases ─────────────────────────────────────────────────────────────────────

# SETUP ────────────────────────────────────────────────────────────────────────
if st.session_state.phase == 'setup':
    phase_bar('setup')
    st.markdown("""
    <div style="font-family:'Instrument Serif',Georgia,serif;font-size:2.4rem;
                line-height:1.15;color:#1A1A1A;margin-bottom:28px;">
      New Deck
    </div>
    """, unsafe_allow_html=True)

    _labels = {'tiktok': 'TikTok (9:16)', 'instagram': 'IG Landscape (4:3)', 'instagram_45': 'IG Portrait (4:5)'}

    with st.form("setup"):
        # ── Row 1: Topic (full width) ──
        topic = st.text_input("Topic *", placeholder="e.g. premeds forget to log hours — be specific")

        # ── Row 2: Framework · Visual style · Platform ──
        c1, c2, c3 = st.columns([2, 1, 2])
        with c1:
            fw_key = st.selectbox("Framework", list(agent.FRAMEWORKS),
                                  format_func=lambda k: agent.FRAMEWORKS[k]['name'])
        with c2:
            vis = st.selectbox("Visual style", list(agent.VISUAL_STYLES))
        with c3:
            platform = st.radio("Platform", list(_labels),
                                format_func=lambda p: _labels[p], horizontal=True)

        st.markdown("""
        <div style="margin:20px 0 12px;padding-top:18px;border-top:1px solid #EDE9E3;
                    font-size:11px;font-weight:700;text-transform:uppercase;
                    letter-spacing:.1em;color:#888;">Creative Brief</div>
        """, unsafe_allow_html=True)

        # ── Row 3: Emotion · Hook · CTA ──
        cb1, cb2, cb3 = st.columns(3)
        with cb1:
            emotion   = st.selectbox("Target emotion", agent.TARGET_EMOTIONS)
        with cb2:
            hook_type = st.selectbox("Hook type", agent.HOOK_TYPES)
        with cb3:
            cta_type  = st.selectbox("CTA type", agent.CTA_TYPES)

        # ── Row 4: Audience ──
        audience = st.text_input("Audience",
                                 value="pre-med undergrads applying to US medical schools")

        # ── Row 5: Toggles ──
        tc1, tc2, _ = st.columns([1, 1, 4])
        with tc1:
            no_res    = st.checkbox("Skip research", value=False)
        with tc2:
            skip_imgs = st.checkbox("Copy only (no images)", value=False)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        go = st.form_submit_button("Generate deck →", type="primary", use_container_width=False)
        if go and topic.strip():
            st.session_state.update({
                'topic': topic.strip(), 'framework_key': fw_key,
                'visual_style': vis, 'platform': platform,
                'skip_images': skip_imgs, 'no_research': no_res,
                'session_config': {'target_emotion': emotion, 'hook_type': hook_type,
                                   'cta_type': cta_type, 'audience': audience},
                'output_folder': agent.make_output_folder(topic.strip(), fw_key),
                'phase': 'research' if not no_res else 'slide_copy',
            })
            st.rerun()
        elif go and not topic.strip():
            st.error("Topic is required.")

# RESEARCH ─────────────────────────────────────────────────────────────────────
elif st.session_state.phase == 'research':
    phase_bar('research')
    st.title(f"Research")
    st.caption(f'Topic: {st.session_state.topic}')

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
            field_card([
                ('Framework',  b.get('recommended_framework', '')),
                ('Why',        b.get('framework_reason', '')),
                ('Core pain',  b.get('core_pain', '')),
                ('Stat',       b.get('surprising_stat', '')),
                ('Save-bait',  b.get('save_bait', '')),
            ])
        with c2:
            field_card([
                ('Feature',   b.get('feature_spotlight', '')),
                ('Best CTA',  b.get('best_cta', '')),
                ('Arc',       b.get('narrative_arc', '')),
            ])
            hooks = b.get('hook_options', [])
            if hooks:
                hooks_html = ''.join(
                    f'<div style="padding:7px 0;border-bottom:1px solid #F0EDE8;font-size:14px;">'
                    f'<span style="color:#C6837A;margin-right:6px;">→</span>{h}</div>'
                    for h in hooks)
                st.markdown(f"""
                <div style="background:#fff;border:1px solid #EDE9E3;border-radius:12px;
                            padding:4px 18px 4px;box-shadow:0 1px 6px rgba(0,0,0,0.04);">
                  <div style="font-size:11px;font-weight:700;text-transform:uppercase;
                              letter-spacing:.07em;color:#888;padding:10px 0 4px;">Hook options</div>
                  {hooks_html}
                </div>
                """, unsafe_allow_html=True)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    if st.button("Continue to slides →", type="primary"):
        st.session_state.phase = 'slide_copy'; st.rerun()

# SLIDE COPY ───────────────────────────────────────────────────────────────────
elif st.session_state.phase == 'slide_copy':
    phase_bar('slide_copy')
    sd   = cur_def()
    sn   = cur_sn()
    sidx = cur_idx()
    is_hook = sidx == 0

    hook_note = ' — Hook (written last)' if is_hook else ''
    st.markdown(f"""
    <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:6px;">
      <span style="font-family:'Instrument Serif',serif;font-size:1.9rem;color:#1A1A1A;">
        Slide {sn}/5
      </span>
      <span style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
                   color:#888;">{sd['role']}{hook_note}</span>
    </div>
    """, unsafe_allow_html=True)

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
                    personal_rules=st.session_state.get('personal_rules', []),
                )
            except Exception as e:
                st.error(f"Copy generation failed: {e}")
                if st.button("Retry"): st.rerun()
                st.stop()
        st.rerun()

    draft = st.session_state.draft
    text  = draft.get('text', '')
    wc    = len(text.split())
    banned = agent.check_banned_opener(text)

    # Big headline display
    slide_headline(text, wc, banned,
                   draft.get('hook_score'), draft.get('hook_score_reason', ''))

    # Metadata fields card
    field_card([
        ('Subtext',         draft.get('subtext', '')),
        ('Visual',          draft.get('visual_direction', '')),
        ('Retention hook',  draft.get('retention_hook', '')),
        ('Content pillar',  draft.get('content_pillar', '')),
        ('Animation',       draft.get('animation', '')),
    ])

    extra = st.text_input("Direction for rewrite (optional)",
                          placeholder="e.g. make it more urgent, mention AMCAS deadline")

    ca, cr = st.columns([2, 1])
    with ca:
        if st.button("Approve copy — next step →", type="primary", use_container_width=True):
            st.session_state.slides_written.append(draft)
            st.session_state.extra_dir = ''
            st.session_state.phase = 'slide_screenshot'
            st.rerun()
    with cr:
        if st.button("Rewrite", use_container_width=True):
            agent.log_copy_rejection(draft, st.session_state.topic, extra)
            with st.spinner("Extracting style rule..."):
                try:
                    _rule = agent.extract_style_rule_from_rejection(draft, extra, 'copy', client)
                    _updated = st.session_state.personal_rules + [_rule]
                    _seen = set(); _deduped = []
                    for r in _updated:
                        if r not in _seen:
                            _seen.add(r); _deduped.append(r)
                    _save_personal_rules(_deduped[-20:])
                except Exception:
                    pass
            st.session_state.extra_dir = extra
            st.session_state.draft = None
            st.rerun()

# SCREENSHOT ───────────────────────────────────────────────────────────────────
elif st.session_state.phase == 'slide_screenshot':
    phase_bar('slide_screenshot')
    sd   = cur_def()
    sn   = cur_sn()
    sidx = cur_idx()

    st.markdown(f"""
    <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:6px;">
      <span style="font-family:'Instrument Serif',serif;font-size:1.9rem;color:#1A1A1A;">
        Slide {sn}/5
      </span>
      <span style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
                   color:#888;">Screenshot</span>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.skip_images:
        advance_slide(); st.rerun()

    if sidx == 0:
        st.info("Hook slide — text-only is usually stronger here.")

    available = agent.list_available_screenshots()
    options   = [None] + available
    labels    = ["(none — text only)"] + [p.name for p in available]

    suggested = agent.SCREENSHOT_SUGGESTIONS.get(sd['type'], [])
    default   = 0
    for name in suggested:
        p = agent.SCREENSHOTS_DIR / name
        if p in available:
            default = available.index(p) + 1; break

    col_sel, col_prev = st.columns([1, 1])
    with col_sel:
        sel = st.selectbox("App screenshot to composite",
                           range(len(options)), index=default,
                           format_func=lambda i: labels[i])
        st.session_state.screenshot = options[sel]
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        if st.button("Continue to image generation →", type="primary", use_container_width=True):
            st.session_state.phase = 'slide_image'; st.rerun()
    with col_prev:
        chosen = options[sel]
        if chosen:
            st.image(str(chosen), caption=chosen.name, use_container_width=True)
        else:
            st.markdown("""
            <div style="height:200px;background:#F5F2EE;border-radius:12px;border:1px dashed #DDD8D2;
                        display:flex;align-items:center;justify-content:center;color:#AAA;font-size:13px;">
              No screenshot selected
            </div>""", unsafe_allow_html=True)

# IMAGE GENERATION ─────────────────────────────────────────────────────────────
elif st.session_state.phase == 'slide_image':
    sd         = cur_def()
    sn         = cur_sn()
    sidx       = cur_idx()
    draft      = st.session_state.draft
    screenshot = st.session_state.screenshot

    phase_bar('slide_image')
    st.markdown(f"""
    <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:20px;">
      <span style="font-family:'Instrument Serif',serif;font-size:1.9rem;color:#1A1A1A;">
        Slide {sn}/5
      </span>
      <span style="font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
                   color:#888;">Image Generation</span>
      <span style="margin-left:auto;font-size:12px;color:#AAA;font-style:italic;">
        Pass 1 → Critique → Pass 2
      </span>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.skip_images:
        advance_slide(); st.rerun()

    col_p1, col_crit, col_p2 = st.columns(3)

    # ── Pass 1 ──────────────────────────────────────────────────────────────
    with col_p1:
        st.markdown('<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#888;margin-bottom:8px;">Pass 1 — Draft</div>', unsafe_allow_html=True)
        if st.session_state.p1_bytes is None:
            if st.session_state.p1_prompt is None:
                st.session_state.p1_prompt = agent.build_image_prompt(
                    draft, sn, st.session_state.visual_style, bool(screenshot),
                    st.session_state.get('platform', 'tiktok'),
                    st.session_state.get('personal_rules', []))
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
        st.markdown('<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#888;margin-bottom:8px;">Claude Critique</div>', unsafe_allow_html=True)
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
        st.markdown('<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#888;margin-bottom:8px;">Pass 2 — Refined</div>', unsafe_allow_html=True)
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
        ca, _, cr = st.columns([2, 1, 3])
        with ca:
            if st.button("Approve — next slide →", type="primary", use_container_width=True):
                advance_slide(); st.rerun()
        with cr:
            reason = st.text_input("Rejection reason (optional)", key=f"rej_{sn}",
                                   placeholder="e.g. background too dark, text too small")
            if st.button("✗ Reject — regenerate", use_container_width=True):
                agent.log_image_rejection(draft, sn, reason)
                try:
                    _img_rule = agent.extract_style_rule_from_rejection(draft, reason, 'image', client)
                    _upd = st.session_state.personal_rules + [_img_rule]
                    _seen2 = set(); _deduped2 = []
                    for r in _upd:
                        if r not in _seen2:
                            _seen2.add(r); _deduped2.append(r)
                    _save_personal_rules(_deduped2[-20:])
                except Exception:
                    pass
                base = st.session_state.p1_prompt or agent.build_image_prompt(
                    draft, sn, st.session_state.visual_style, bool(screenshot),
                    st.session_state.get('platform', 'tiktok'),
                    st.session_state.get('personal_rules', []))
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
        partial = st.session_state.output_folder / _PARTIAL_FILE
        if partial.exists():
            partial.unlink()
        st.session_state.phase = 'done'
        st.rerun()

# DONE ─────────────────────────────────────────────────────────────────────────
elif st.session_state.phase == 'done':
    phase_bar('done')
    st.markdown("""
    <div style="font-family:'Instrument Serif',Georgia,serif;font-size:2.4rem;
                color:#1A1A1A;margin-bottom:4px;">Deck complete</div>
    """, unsafe_allow_html=True)
    folder_str = str(st.session_state.output_folder)
    st.caption(f"Saved to {folder_str}")

    # Slides strip
    slide_meta = [st.session_state.slide_metadata_map[i]
                  for i in sorted(st.session_state.slide_metadata_map)]
    cols = st.columns(len(slide_meta))
    for i, meta in enumerate(slide_meta):
        with cols[i]:
            status_color = {'success': '#3AA66B', 'skipped': '#888', 'failed': '#E05C52'}.get(meta['status'], '#888')
            st.markdown(f'<div style="font-size:11px;font-weight:700;text-transform:uppercase;'
                        f'letter-spacing:.08em;color:{status_color};margin-bottom:4px;">'
                        f'Slide {meta["slide_number"]}</div>', unsafe_allow_html=True)
            if meta.get('filename'):
                fp = st.session_state.output_folder / meta['filename']
                if fp.exists():
                    st.image(str(fp), use_container_width=True)
                    crit = meta.get('auto_critique') or {}
                    if crit.get('marketing_verdict'):
                        st.caption(crit['marketing_verdict'][:70])
                    with open(str(fp), 'rb') as f:
                        st.download_button(f"Download", f.read(),
                                           file_name=meta['filename'], mime='image/png',
                                           key=f"dl_{i}", use_container_width=True)
            else:
                st.markdown(f'<div style="color:#AAA;font-size:13px;">{meta["status"]}</div>',
                            unsafe_allow_html=True)

    st.divider()
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown('<div style="font-size:11px;font-weight:700;text-transform:uppercase;'
                    'letter-spacing:.08em;color:#888;margin-bottom:8px;">Caption</div>',
                    unsafe_allow_html=True)
        st.code(st.session_state.caption or '', language=None)
    with c2:
        st.markdown('<div style="font-size:11px;font-weight:700;text-transform:uppercase;'
                    'letter-spacing:.08em;color:#888;margin-bottom:8px;">Audio vibe</div>',
                    unsafe_allow_html=True)
        st.markdown(f'<div style="background:#fff;border:1px solid #EDE9E3;border-radius:10px;'
                    f'padding:14px 16px;font-size:14px;color:#1A1A1A;line-height:1.5;">'
                    f'{st.session_state.audio_vibe or ""}</div>', unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    if st.button("Make another deck →", type="primary"):
        full_reset(); st.rerun()
