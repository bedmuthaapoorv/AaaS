import os
import re
import subprocess
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

APP_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(APP_DIR, "rules.md")
REPORT_PATH = os.path.join(APP_DIR, "stock_report.csv")
BACKUP_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "Rules_backup"))


def strategy_slug(content):
    """Derive a filesystem-safe slug from the 'Strategy Name:' line, falling
    back to a timestamp if the content doesn't declare one."""
    match = re.search(r"Strategy Name:\s*(.+)", content)
    name = match.group(1).strip() if match else ""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_rules(content):
    """Save the given rules.md content into Rules_backup, keyed by strategy name."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    filename = f"{strategy_slug(content)}_rules.md"
    with open(os.path.join(BACKUP_DIR, filename), "w") as f:
        f.write(content)
    return filename


def list_backups():
    if not os.path.isdir(BACKUP_DIR):
        return []
    return sorted(f for f in os.listdir(BACKUP_DIR) if f.endswith(".md"))

st.set_page_config(page_title="Stock Screener", layout="wide")
st.title("Stock Screener")

tab_rules, tab_run, tab_results = st.tabs(["Rules", "Run", "Results"])


def run_script(script_name):
    """Run a script in Default/ and stream its output."""
    process = subprocess.Popen(
        [sys.executable, script_name],
        cwd=APP_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    output_box = st.empty()
    lines = []
    for line in process.stdout:
        lines.append(line.rstrip())
        output_box.code("\n".join(lines[-200:]))
    process.wait()
    return process.returncode


with tab_rules:
    st.subheader("Edit rules.md")

    guide_path = os.path.join(APP_DIR, "RULES_GUIDE.md")
    if os.path.exists(guide_path):
        with st.expander("New to rules.md? Read the guide"):
            with open(guide_path, "r") as f:
                st.markdown(f.read())

    if "rules_content" not in st.session_state:
        with open(RULES_PATH, "r") as f:
            st.session_state.rules_content = f.read()

    edited = st.text_area(
        "Strategy rules",
        value=st.session_state.rules_content,
        height=600,
        label_visibility="collapsed",
    )

    if st.button("Save rules.md"):
        with open(RULES_PATH, "r") as f:
            previous_content = f.read()
        if previous_content.strip() and previous_content != edited:
            backup_name = backup_rules(previous_content)
            st.info(f"Backed up previous rules.md to Rules_backup/{backup_name}")

        with open(RULES_PATH, "w") as f:
            f.write(edited)
        st.session_state.rules_content = edited
        st.success("Saved rules.md")

    st.divider()

    st.subheader("Load a previous strategy")
    backups = list_backups()
    if not backups:
        st.caption("No backups yet. Backups are created automatically whenever you save a changed rules.md.")
    else:
        selected_backup = st.selectbox("Choose a backed-up strategy", backups)
        backup_path = os.path.join(BACKUP_DIR, selected_backup)
        with open(backup_path, "r") as f:
            backup_content = f.read()

        with st.expander(f"Preview {selected_backup}"):
            st.code(backup_content, language="markdown")

        if st.button(f"Overwrite rules.md with {selected_backup}"):
            with open(RULES_PATH, "r") as f:
                current_content = f.read()
            if current_content.strip() and current_content != backup_content:
                backup_name = backup_rules(current_content)
                st.info(f"Backed up previous rules.md to Rules_backup/{backup_name}")

            with open(RULES_PATH, "w") as f:
                f.write(backup_content)
            st.session_state.rules_content = backup_content
            st.success(f"rules.md overwritten with {selected_backup}")
            st.rerun()

with tab_run:
    st.subheader("Generate screening logic")
    st.caption("Reads rules.md, calls Gemini, writes generated_rules.py. Requires GEMINI_API_KEY in .env.")
    if st.button("Run generate_screener.py"):
        with st.spinner("Generating screening logic..."):
            code = run_script("generate_screener.py")
        if code == 0:
            st.success("generated_rules.py updated.")
        else:
            st.error(f"generate_screener.py exited with code {code}.")

    st.divider()

    st.subheader("Run the screener")
    st.caption("Fetches the stock universe and price history, scores each stock, writes stock_report.csv.")
    if st.button("Run stock_screener.py"):
        with st.spinner("Running screener..."):
            code = run_script("stock_screener.py")
        if code == 0:
            st.success("stock_report.csv updated. See the Results tab.")
        else:
            st.error(f"stock_screener.py exited with code {code}.")

with tab_results:
    st.subheader("stock_report.csv")
    if not os.path.exists(REPORT_PATH):
        st.info("No report yet. Run the screener from the Run tab first.")
    else:
        df = pd.read_csv(REPORT_PATH)
        if "Passed" in df.columns:
            passed_only = st.checkbox("Show only stocks that passed all filters")
            if passed_only:
                df = df[df["Passed"] == True]
        st.dataframe(df, use_container_width=True)
        st.caption(f"{len(df)} rows")
