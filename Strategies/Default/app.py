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
EXIT_RULES_PATH = os.path.join(APP_DIR, "exit_rules.md")
EXIT_BACKUP_DIR = os.path.normpath(os.path.join(APP_DIR, "..", "ExitRules_backup"))
BACKTEST_TRADES_PATH = os.path.join(APP_DIR, "backtest_trades.csv")
BACKTEST_SUMMARY_PATH = os.path.join(APP_DIR, "backtest_summary.csv")
BACKTEST_LOG_PATH = os.path.join(APP_DIR, "backtest_run.log")


def strategy_slug(content, name_field="Strategy Name"):
    """Derive a filesystem-safe slug from a '<name_field>: ...' line, falling
    back to a timestamp if the content doesn't declare one."""
    match = re.search(rf"{re.escape(name_field)}:\s*(.+)", content)
    name = match.group(1).strip() if match else ""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_markdown(content, backup_dir, suffix, name_field="Strategy Name"):
    """Save the given markdown content into backup_dir, keyed by the name
    declared in name_field."""
    os.makedirs(backup_dir, exist_ok=True)
    filename = f"{strategy_slug(content, name_field=name_field)}_{suffix}.md"
    with open(os.path.join(backup_dir, filename), "w", encoding="utf-8") as f:
        f.write(content)
    return filename


def list_backups(backup_dir):
    if not os.path.isdir(backup_dir):
        return []
    return sorted(f for f in os.listdir(backup_dir) if f.endswith(".md"))

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
            with open(guide_path, "r", encoding="utf-8") as f:
                st.markdown(f.read())

    if "rules_content" not in st.session_state:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            st.session_state.rules_content = f.read()

    edited = st.text_area(
        "Strategy rules",
        value=st.session_state.rules_content,
        height=600,
        label_visibility="collapsed",
    )

    if st.button("Save rules.md"):
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            previous_content = f.read()
        if previous_content.strip() and previous_content != edited:
            backup_name = backup_markdown(previous_content, BACKUP_DIR, "rules")
            st.info(f"Backed up previous rules.md to Rules_backup/{backup_name}")

        with open(RULES_PATH, "w", encoding="utf-8") as f:
            f.write(edited)
        st.session_state.rules_content = edited
        st.success("Saved rules.md")

    st.divider()

    st.subheader("Load a previous strategy")
    backups = list_backups(BACKUP_DIR)
    if not backups:
        st.caption("No backups yet. Backups are created automatically whenever you save a changed rules.md.")
    else:
        selected_backup = st.selectbox("Choose a backed-up strategy", backups)
        backup_path = os.path.join(BACKUP_DIR, selected_backup)
        with open(backup_path, "r", encoding="utf-8") as f:
            backup_content = f.read()

        with st.expander(f"Preview {selected_backup}"):
            st.code(backup_content, language="markdown")

        if st.button(f"Overwrite rules.md with {selected_backup}"):
            with open(RULES_PATH, "r", encoding="utf-8") as f:
                current_content = f.read()
            if current_content.strip() and current_content != backup_content:
                backup_name = backup_markdown(current_content, BACKUP_DIR, "rules")
                st.info(f"Backed up previous rules.md to Rules_backup/{backup_name}")

            with open(RULES_PATH, "w", encoding="utf-8") as f:
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
        with open(BACKTEST_LOG_PATH, "r", encoding="utf-8") as f:
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
        "Simulates generated_rules.py over a historical date range using the exit "
        "logic in generated_exit_strategy.py. On each signal, opens a flat Rs.100 "
        "trade at the next trading day's open, holds until your exit strategy "
        "triggers, or force-exits at the range's last close if it never does."
    )

    backtest_guide_path = os.path.join(APP_DIR, "BACKTEST_GUIDE.md")
    if os.path.exists(backtest_guide_path):
        with st.expander("New to backtesting? Read the guide"):
            with open(backtest_guide_path, "r", encoding="utf-8") as f:
                st.markdown(f.read())

    st.subheader("Exit strategy")
    st.caption(
        "Define your exit strategy in exit_rules.md, then generate it - the same "
        "way rules.md drives generated_rules.py. Write your own logic here (fixed "
        "SL/TP, trailing ATR, time-based, anything computable from OHLCV) instead "
        "of picking from a fixed list of built-in options."
    )

    if "exit_rules_content" not in st.session_state:
        with open(EXIT_RULES_PATH, "r", encoding="utf-8") as f:
            st.session_state.exit_rules_content = f.read()

    edited_exit_rules = st.text_area(
        "Exit strategy rules",
        value=st.session_state.exit_rules_content,
        height=300,
        label_visibility="collapsed",
    )

    exit_save_col, exit_gen_col = st.columns(2)
    with exit_save_col:
        if st.button("Save exit_rules.md"):
            with open(EXIT_RULES_PATH, "r", encoding="utf-8") as f:
                previous_content = f.read()
            if previous_content.strip() and previous_content != edited_exit_rules:
                backup_name = backup_markdown(previous_content, EXIT_BACKUP_DIR, "exit_rules")
                st.info(f"Backed up previous exit_rules.md to ExitRules_backup/{backup_name}")

            with open(EXIT_RULES_PATH, "w", encoding="utf-8") as f:
                f.write(edited_exit_rules)
            st.session_state.exit_rules_content = edited_exit_rules
            st.success("Saved exit_rules.md")

    with exit_gen_col:
        if st.button("Generate exit strategy"):
            with st.spinner("Generating exit logic..."):
                code = run_script("generate_exit_strategy.py")
            if code == 0:
                st.success("generated_exit_strategy.py updated.")
            else:
                st.error(f"generate_exit_strategy.py exited with code {code}.")

    with st.expander("Load a previous exit strategy"):
        exit_backups = list_backups(EXIT_BACKUP_DIR)
        if not exit_backups:
            st.caption("No backups yet. Backups are created automatically whenever you save a changed exit_rules.md.")
        else:
            selected_exit_backup = st.selectbox("Choose a backed-up exit strategy", exit_backups)
            exit_backup_path = os.path.join(EXIT_BACKUP_DIR, selected_exit_backup)
            with open(exit_backup_path, "r", encoding="utf-8") as f:
                exit_backup_content = f.read()

            st.code(exit_backup_content, language="markdown")

            if st.button(f"Overwrite exit_rules.md with {selected_exit_backup}"):
                with open(EXIT_RULES_PATH, "r", encoding="utf-8") as f:
                    current_content = f.read()
                if current_content.strip() and current_content != exit_backup_content:
                    backup_name = backup_markdown(current_content, EXIT_BACKUP_DIR, "exit_rules")
                    st.info(f"Backed up previous exit_rules.md to ExitRules_backup/{backup_name}")

                with open(EXIT_RULES_PATH, "w", encoding="utf-8") as f:
                    f.write(exit_backup_content)
                st.session_state.exit_rules_content = exit_backup_content
                st.success(f"exit_rules.md overwritten with {selected_exit_backup}")
                st.rerun()

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start date")
    with col2:
        end_date = st.date_input("End date")

    st.caption(
        "First run for a given date range fetches history from NSE and caches it in "
        "backtest_cache/; later runs over the same range reuse that cache regardless "
        "of exit strategy changes."
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
                    f"(~{est['months_per_stock']} monthly requests each for this range) — "
                    f"estimated **{low_min:.1f}-{high_min:.1f} min**. "
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

    if os.path.exists(BACKTEST_SUMMARY_PATH) and os.path.getsize(BACKTEST_SUMMARY_PATH) > 0:
        st.divider()
        st.subheader("Summary by ClosenessScore bucket")
        try:
            st.dataframe(pd.read_csv(BACKTEST_SUMMARY_PATH), use_container_width=True)
        except pd.errors.EmptyDataError:
            st.caption("No trades were simulated in the last run, so there's no summary to bucket.")

    if os.path.exists(BACKTEST_TRADES_PATH) and os.path.getsize(BACKTEST_TRADES_PATH) > 0:
        st.subheader("Individual trades")
        try:
            st.dataframe(pd.read_csv(BACKTEST_TRADES_PATH), use_container_width=True)
        except pd.errors.EmptyDataError:
            st.caption("No trades were simulated in the last run.")
