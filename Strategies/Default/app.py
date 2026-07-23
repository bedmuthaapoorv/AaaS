import os
import re
import subprocess
import sys
from datetime import datetime

import pandas as pd
import streamlit as st

import backtest

APP_DIR = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(APP_DIR, "rules.md")
REPORT_PATH = os.path.join(APP_DIR, "stock_report.csv")
BACKUP_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "Rules_backup"))
BACKTEST_TRADES_PATH = os.path.join(APP_DIR, "backtest_trades.csv")
BACKTEST_SUMMARY_PATH = os.path.join(APP_DIR, "backtest_summary.csv")
BACKTEST_LOG_PATH = os.path.join(APP_DIR, "backtest_run.log")


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

tab_rules, tab_run, tab_results, tab_backtest = st.tabs(["Rules", "Run", "Results", "Backtest"])


def run_script(script_name, args=None):
    """Run a script in Default/ and stream its output."""
    process = subprocess.Popen(
        [sys.executable, script_name, *(args or [])],
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

@st.fragment(run_every=2)
def show_backtest_progress():
    """Polls the running backtest's log file and process status every 2s,
    without blocking the rest of the page (so the Stop button stays clickable)."""
    process = st.session_state.get("backtest_process")
    if process is None:
        return

    if os.path.exists(BACKTEST_LOG_PATH):
        with open(BACKTEST_LOG_PATH, "r") as f:
            log_content = f.read()
        st.code(log_content[-3000:] or "Starting...")

    if process.poll() is not None:
        st.session_state.backtest_running = False
        if process.returncode == 0:
            st.success("Backtest complete. See results below.")
        else:
            st.error(f"backtest.py exited with code {process.returncode}.")
        st.rerun()


with tab_backtest:
    st.subheader("Backtest the current strategy")
    st.caption(
        "Simulates generated_rules.py over a historical date range. On each signal, "
        "opens a flat Rs.100 trade at the next trading day's open, holds until your "
        "stop-loss or take-profit hits (checked on daily closes only), or force-exits "
        "at the range's last close if neither is hit."
    )

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start date")
    with col2:
        end_date = st.date_input("End date")

    col3, col4 = st.columns(2)
    with col3:
        sl_pct = st.number_input("Stop-loss %", min_value=0.1, value=5.0, step=0.5)
    with col4:
        tp_pct = st.number_input("Take-profit %", min_value=0.1, value=10.0, step=0.5)

    st.caption(
        "First run for a given date range fetches history from NSE and caches it in "
        "backtest_cache/; later runs over the same range (even with different "
        "SL/TP) reuse that cache."
    )

    is_running = st.session_state.get("backtest_running", False)

    if start_date < end_date and not is_running:
        try:
            est = backtest.estimate_runtime(start_date, end_date)
            if est["to_fetch_stocks"] == 0:
                st.info(f"All {est['total_stocks']} stocks already cached for this range — should finish in well under a minute.")
            else:
                low_min = est["estimated_low_seconds"] / 60
                high_min = est["estimated_high_seconds"] / 60
                st.info(
                    f"{est['to_fetch_stocks']} of {est['total_stocks']} stocks need fetching from NSE "
                    f"for this range — estimated **{low_min:.1f}-{high_min:.1f} min**. "
                    f"({est['cached_stocks']} already cached.)"
                )
        except Exception:
            pass

    run_col, stop_col = st.columns([1, 1])
    with run_col:
        run_clicked = st.button("Run backtest", disabled=is_running)
    with stop_col:
        stop_clicked = st.button("Stop backtest", disabled=not is_running)

    if run_clicked:
        if start_date >= end_date:
            st.error("Start date must be before end date.")
        else:
            args = [
                "--start", start_date.isoformat(),
                "--end", end_date.isoformat(),
                "--sl", str(sl_pct),
                "--tp", str(tp_pct),
            ]
            log_file = open(BACKTEST_LOG_PATH, "w")
            process = subprocess.Popen(
                [sys.executable, "backtest.py", *args],
                cwd=APP_DIR,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            st.session_state.backtest_process = process
            st.session_state.backtest_running = True
            st.rerun()

    if stop_clicked:
        process = st.session_state.get("backtest_process")
        if process is not None and process.poll() is None:
            process.terminate()
        st.session_state.backtest_running = False
        st.warning("Backtest stopped. Partial progress is lost — results/CSVs are only written when a run finishes.")

    if is_running:
        show_backtest_progress()

    if os.path.exists(BACKTEST_SUMMARY_PATH):
        st.divider()
        st.subheader("Summary by ClosenessScore bucket")
        st.dataframe(pd.read_csv(BACKTEST_SUMMARY_PATH), use_container_width=True)

    if os.path.exists(BACKTEST_TRADES_PATH):
        st.subheader("Individual trades")
        st.dataframe(pd.read_csv(BACKTEST_TRADES_PATH), use_container_width=True)
