"""Returns the custom CSS block injected into the Streamlit app to move it
away from default Streamlit look-and-feel toward a premium SaaS aesthetic."""

CUSTOM_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">

<style>
:root {
  --bg: #0F1222;
  --card: #FFFFFF;
  --primary: #6D5AE0;
  --primary-dark: #4C3FBF;
  --secondary: #14B8A6;
  --accent: #F472B6;
  --success: #10B981;
  --success-bg: #ECFDF5;
  --warning: #F59E0B;
  --warning-bg: #FFFBEB;
  --danger: #EF4444;
  --danger-bg: #FEF2F2;
  --border: #E2E4EE;
  --text: #14162B;
  --text-muted: #6B7089;
  --radius: 14px;
  --radius-lg: 18px;
  --font: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --mono: 'JetBrains Mono', ui-monospace, monospace;
}

html, body, [class*="css"], .stMarkdown, .stTextInput input, .stSelectbox, .stButton, .stSlider {
  font-family: var(--font) !important;
}
code, pre, .stCode { font-family: var(--mono) !important; }

.stApp {
  background:
    radial-gradient(circle at 8% 0%, rgba(109,90,224,0.10), transparent 42%),
    radial-gradient(circle at 95% 8%, rgba(20,184,166,0.09), transparent 40%),
    linear-gradient(180deg, #EEF0FA 0%, #E7EAF7 55%, #E4E7F5 100%);
}

#MainMenu, footer, header {visibility: hidden;}

.app-hero { display:flex; align-items:center; justify-content:space-between; margin-bottom: 4px; }
.app-hero h1 {
  font-size: 30px !important; font-weight: 800 !important; letter-spacing: -0.03em !important;
  margin: 0 !important;
  background: linear-gradient(120deg, var(--primary-dark), var(--secondary) 60%, var(--accent));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  display: inline-block;
}
.app-hero-tag {
  font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
  color: var(--primary-dark); background: rgba(91,79,233,0.10);
  padding: 4px 12px; border-radius: 999px; display:inline-block; margin-bottom: 6px;
}

section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #FFFFFF 0%, #F7F7FE 100%);
  border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] .block-container { padding-top: 1.5rem; }

.brand-block {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 4px 20px 4px; border-bottom: 1px solid var(--border); margin-bottom: 18px;
}
.brand-logo {
  width: 42px; height: 42px; border-radius: 12px;
  background: linear-gradient(135deg, var(--primary), var(--secondary));
  display: flex; align-items: center; justify-content: center;
  color: white; font-weight: 800; font-size: 18px;
  box-shadow: 0 6px 16px rgba(91,79,233,0.35);
}
.brand-title { font-weight: 800; font-size: 16px; color: var(--text); line-height: 1.15; letter-spacing: -0.01em; }
.brand-subtitle { font-size: 12px; color: var(--text-muted); font-weight: 500; }

.glass-card {
  background: rgba(255,255,255,0.85);
  backdrop-filter: blur(10px);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 18px; margin-bottom: 14px;
  box-shadow: 0 4px 20px rgba(20,22,43,0.045);
}
.metric-row { display:flex; justify-content:space-between; align-items:center; margin: 7px 0; }
.metric-label { color: var(--text-muted); font-size: 12.5px; font-weight: 500; }
.metric-value { font-weight: 700; font-size: 12.5px; color: var(--text); }

.status-chip { display:inline-flex; align-items:center; gap:6px; padding: 4px 11px; border-radius: 999px; font-size: 11.5px; font-weight: 700; }
.chip-green { background: var(--success-bg); color: #067A57; }
.chip-red { background: var(--danger-bg); color: #B91C1C; }
.chip-amber { background: var(--warning-bg); color: #92610A; }
.chip-indigo { background: rgba(91,79,233,0.12); color: var(--primary-dark); }

.chat-bubble-user {
  background: linear-gradient(135deg, var(--primary), var(--secondary));
  color: white; padding: 14px 18px; border-radius: 18px 18px 4px 18px;
  max-width: 78%; margin-left: auto; margin-bottom: 4px;
  box-shadow: 0 6px 18px rgba(91,79,233,0.28);
  font-size: 14.5px; line-height: 1.55; font-weight: 500;
}
.chat-bubble-assistant {
  background: var(--card); border: 1px solid var(--border); color: var(--text);
  padding: 17px 19px; border-radius: 18px 18px 18px 4px;
  max-width: 82%; margin-bottom: 4px;
  box-shadow: 0 3px 14px rgba(20,22,43,0.05);
  font-size: 14.5px; line-height: 1.65;
}
.chat-bubble-assistant.refused {
  border-left: 3px solid var(--warning);
  background: linear-gradient(90deg, rgba(245,158,11,0.05), transparent 30%);
}

.citation-card {
  display: inline-flex; flex-direction: column;
  background: rgba(91,79,233,0.06); border: 1px solid rgba(91,79,233,0.18);
  border-radius: 10px; padding: 8px 12px; margin: 4px 6px 4px 0;
  font-size: 12px; min-width: 140px;
}
.citation-title { font-weight: 800; color: var(--primary-dark); font-size: 12px; }
.citation-section { color: var(--text-muted); font-size: 11px; }

.badge-row { display:flex; gap: 8px; flex-wrap: wrap; margin-top: 9px; }
.badge { font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 999px; background: #F1F2FA; color: var(--text-muted); border: 1px solid var(--border); }

.suggested-pill {
  display:inline-block; background: white; border: 1px solid var(--border); border-radius: 999px;
  padding: 8px 16px; font-size: 13px; margin: 4px 6px 4px 0; color: var(--primary-dark);
  font-weight: 600; transition: all 0.15s ease;
}

.summary-card {
  background: linear-gradient(135deg, rgba(91,79,233,0.07), rgba(6,182,212,0.04));
  border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px 22px;
}
.summary-number { font-size: 30px; font-weight: 800; color: var(--primary-dark); letter-spacing: -0.02em; }
.summary-label { font-size: 12.5px; color: var(--text-muted); margin-top: 3px; font-weight: 600; }

.dim-card {
  background: white; border: 1px solid var(--border); border-radius: var(--radius);
  padding: 16px 14px; text-align: center;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.dim-card:hover { transform: translateY(-2px); box-shadow: 0 8px 20px rgba(20,22,43,0.08); }
.dim-score { font-size: 24px; font-weight: 800; letter-spacing: -0.02em; }

.weakest-banner {
  background: linear-gradient(90deg, rgba(239,68,68,0.08), rgba(245,158,11,0.05));
  border: 1px solid rgba(239,68,68,0.2); border-radius: var(--radius);
  padding: 14px 18px; font-size: 13.5px; color: var(--text); margin: 6px 0 18px 0;
}
.weakest-banner b { color: #B91C1C; }

h1, h2, h3 { color: var(--text); font-weight: 800; letter-spacing: -0.02em; }
h3 { font-size: 18px !important; margin-top: 8px !important; }
p, span, div { color: var(--text); }
.muted { color: var(--text-muted) !important; font-weight: 500; }

.stButton>button {
  border-radius: 10px !important; border: 1px solid var(--border) !important;
  font-weight: 700 !important; color: var(--text) !important; transition: all 0.15s ease;
}
.stButton>button:hover {
  border-color: var(--primary) !important; color: var(--primary-dark) !important;
  box-shadow: 0 3px 12px rgba(91,79,233,0.18);
}
.stDownloadButton>button { border-radius: 10px !important; font-weight: 700 !important; }
.stTextInput input, .stSelectbox div[data-baseweb="select"] { border-radius: 10px !important; }

.stat-pill-row { display:flex; gap:8px; flex-wrap:wrap; }
.stat-pill { flex: 1; min-width: 70px; background: white; border: 1px solid var(--border); border-radius: 10px; padding: 9px 10px; text-align: center; }
.stat-pill-value { font-size: 16px; font-weight: 800; color: var(--primary-dark); }
.stat-pill-label { font-size: 10.5px; color: var(--text-muted); margin-top: 1px; font-weight: 600; }

.conf-track { width: 100%; height: 6px; border-radius: 999px; background: #EEF0F5; margin-top: 9px; overflow: hidden; }
.conf-fill { height: 100%; border-radius: 999px; transition: width 0.3s ease; }

.msg-timestamp { font-size: 10.5px; color: var(--text-muted); margin: 3px 4px 10px 4px; font-weight: 500; }

.filter-chip {
  display:inline-block; padding: 4px 12px; border-radius: 999px; border: 1px solid var(--border);
  font-size: 12px; margin: 2px 4px 2px 0; background: white; color: var(--text-muted); font-weight: 600;
}

.source-badge {
  display:inline-flex; align-items:center; gap:6px; font-size: 11.5px; font-weight: 700;
  padding: 5px 13px; border-radius: 999px; border: 1px solid var(--border);
}
</style>
"""