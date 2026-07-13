"""Streamlit login gate for the College FAQ Assistant.

Reads valid credentials from the LOGIN_USERS env variable:
    LOGIN_USERS=admin:admin123,student:student@2026,demo:demo

Call render_login_gate() at the very top of app.py (before any other UI).
It will st.stop() until the user is authenticated, so the rest of the app
is never rendered for unauthenticated users.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv
import streamlit as st

load_dotenv()


# ── Credential loader ────────────────────────────────────────────────────────

def _load_users() -> dict[str, str]:
    """Parse LOGIN_USERS from .env into {username: password}."""
    raw = os.getenv("LOGIN_USERS", "")
    users: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            username, _, password = entry.partition(":")
            users[username.strip()] = password.strip()
    return users


# ── Login form renderer ──────────────────────────────────────────────────────

def render_login_gate() -> None:
    """Show the login form if the user is not authenticated.

    Sets st.session_state.logged_in = True and
         st.session_state.current_user = username on success.
    Calls st.stop() so the rest of app.py is blocked until login succeeds.
    """
    # Already logged in — nothing to do
    if st.session_state.get("logged_in"):
        return

    # ── Custom CSS for the login card ────────────────────────────────────────
    st.markdown(
        """
        <style>
        /* Hide default Streamlit header/footer on login screen */
        [data-testid="stToolbar"] { display: none !important; }
        footer { display: none !important; }

        .login-wrapper {
            display: flex;
            justify-content: center;
            align-items: center;
            padding-top: 80px;
        }
        .login-card {
            background: #1e293b;
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 16px;
            padding: 40px 36px 32px;
            max-width: 420px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.4);
            margin: 0 auto;
        }
        .login-logo {
            text-align: center;
            margin-bottom: 24px;
        }
        .login-logo .icon { font-size: 3rem; display: block; margin-bottom: 8px; }
        .login-logo h2 {
            color: #f1f5f9;
            font-size: 1.35rem;
            font-weight: 700;
            margin: 0;
        }
        .login-logo p { color: #64748b; font-size: 0.85rem; margin-top: 4px; }
        .login-tag {
            display: inline-block;
            background: rgba(99,102,241,0.15);
            color: #818cf8;
            font-size: 0.7rem;
            font-weight: 600;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            padding: 3px 10px;
            border-radius: 999px;
            border: 1px solid rgba(99,102,241,0.25);
            margin-bottom: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── Logo / header ────────────────────────────────────────────────────────
    st.markdown(
        """
        <div class="login-wrapper">
          <div class="login-card">
            <div class="login-logo">
              <span class="icon">🎓</span>
              <span class="login-tag">RAG-powered · Grounded answers</span>
              <h2>College FAQ Assistant</h2>
              <p>Sign in to continue</p>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Form ─────────────────────────────────────────────────────────────────
    # Centre the form with blank columns
    _, col, _ = st.columns([1, 2, 1])
    with col:
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)

        if submitted:
            users = _load_users()
            if not username or not password:
                st.error("Please enter both username and password.")
            elif username in users and users[username] == password:
                st.session_state.logged_in = True
                st.session_state.current_user = username
                st.rerun()
            else:
                st.error("Invalid username or password. Please try again.")

        st.markdown(
            "<p style='text-align:center;color:#334155;font-size:0.78rem;margin-top:16px;'>"
            "BVRIT College · Admissions &amp; FAQ Portal</p>",
            unsafe_allow_html=True,
        )

    # Block the rest of app.py
    st.stop()
