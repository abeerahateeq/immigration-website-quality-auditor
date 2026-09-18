"""
Streamlit front-end for the Immigration Consultancy Website Quality Auditor.

Put this file in the SAME folder as main.py, then run:
    pip install streamlit pandas
    streamlit run app.py

How it works: the app doesn't re-implement anything. It builds a sites CSV from
the table you edit, runs `python main.py --input <csv>` as a subprocess (so your
authorization gate, robots.txt check, rate limiting, and LLM judge all run
exactly as they do on the command line), streams the logs live, and then
displays whatever report files main.py produced.
"""

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).parent.resolve()
TEMPLATE = ROOT / "sites_template.csv"
INPUT_CSV = ROOT / "sites_streamlit.csv"  # written by this app, ignored when scanning for reports

SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "env", "node_modules", "sample_data", ".streamlit"}
REPORT_EXTS = {".html", ".md", ".csv", ".json"}
IGNORE_FILES = {INPUT_CSV.name, "sites.csv", "sites_template.csv", "demo_sites.csv", "requirements.txt"}

st.set_page_config(page_title="Website Quality Auditor", page_icon="🔍", layout="wide")


# ---------- helpers ----------
def snapshot() -> dict:
    """Map of report-like files under ROOT -> modification time."""
    found = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            if p.suffix.lower() in REPORT_EXTS and fn not in IGNORE_FILES and fn.lower() != "readme.md":
                try:
                    found[p] = p.stat().st_mtime
                except OSError:
                    pass
    return found


def get_default_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        try:
            key = st.secrets.get("ANTHROPIC_API_KEY", "")
        except Exception:
            key = ""
    return key


def load_template() -> pd.DataFrame:
    try:
        df = pd.read_csv(TEMPLATE, dtype=str).fillna("")
        if len(df.columns) > 0:
            return df
    except Exception:
        pass
    return pd.DataFrame({"url": [""]})


def url_column(df: pd.DataFrame):
    for c in df.columns:
        if "url" in c.lower() or "site" in c.lower():
            return c
    return None


def show_file(path: Path):
    ext = path.suffix.lower()
    try:
        if ext == ".html":
            html = path.read_text(encoding="utf-8", errors="replace")
            components.html(html, height=800, scrolling=True)
        elif ext == ".md":
            st.markdown(path.read_text(encoding="utf-8", errors="replace"))
        elif ext == ".csv":
            st.dataframe(pd.read_csv(path), use_container_width=True)
        elif ext == ".json":
            st.json(path.read_text(encoding="utf-8", errors="replace"))
        st.download_button(
            f"Download {path.name}",
            data=path.read_bytes(),
            file_name=path.name,
            key=f"dl-{path}-{path.stat().st_mtime}",
        )
    except Exception as e:
        st.error(f"Couldn't display {path.name}: {e}")


def run_main(args: list, api_key: str, log_box):
    env = os.environ.copy()
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    cmd = [sys.executable, "-u", "main.py", *args]
    proc = subprocess.Popen(
        cmd, cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    lines = []
    for line in proc.stdout:
        lines.append(line.rstrip())
        log_box.code("\n".join(lines[-200:]), language="text")
    proc.wait()
    return proc.returncode, "\n".join(lines)


# ---------- sidebar ----------
with st.sidebar:
    st.header("Settings")
    key_input = st.text_input(
        "Anthropic API key",
        value="",
        type="password",
        placeholder="Leave blank to use ANTHROPIC_API_KEY from your environment",
    )
    api_key = key_input.strip() or get_default_key()
    if api_key:
        st.success("API key found")
    else:
        st.error("No API key found. Paste one above or set ANTHROPIC_API_KEY before launching Streamlit.")

    extra = st.text_input("Extra main.py arguments (optional)", placeholder="e.g. --delay 3")
    if st.button("Show `main.py --help`"):
        r = subprocess.run(
            [sys.executable, "main.py", "--help"], cwd=ROOT,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        st.code((r.stdout or "") + (r.stderr or ""), language="text")

    st.caption("Only audit sites you own or are permitted to review. The tool's robots.txt check and rate limiting stay active.")

# ---------- main ----------
st.title("🔍 Website Quality Auditor")
st.caption("Immigration Consultancy sector · rule-based facts + AI-generated judgments")

tab_run, tab_reports = st.tabs(["Run an audit", "Reports"])

with tab_run:
    st.subheader("1. Sites to audit (5–8 authorized sites)")
    st.caption("Columns come from sites_template.csv. Fill in every column, including any authorization column your tool expects.")
    edited = st.data_editor(
        load_template(), num_rows="dynamic", use_container_width=True, key="sites_editor"
    )

    confirm = st.checkbox("I confirm I own or have permission to audit every site listed above.")

    ucol = url_column(edited)
    clean = edited.copy()
    if ucol:
        clean = clean[clean[ucol].astype(str).str.strip() != ""]
    else:
        clean = clean.dropna(how="all")

    st.write(f"**{len(clean)}** site(s) ready.")
    if len(clean) > 8:
        st.warning("The assignment calls for 5–8 sites; more than that is fine to run but keep requests gentle.")

    can_run = bool(api_key) and confirm and len(clean) > 0
    if st.button("▶ Run audit", type="primary", disabled=not can_run):
        clean.to_csv(INPUT_CSV, index=False)
        before = snapshot()

        st.subheader("2. Live log")
        log_box = st.empty()
        args = ["--input", INPUT_CSV.name, *shlex.split(extra or "")]
        started = time.time()
        with st.spinner("Auditing... this can take a few minutes (rate limiting + LLM calls)."):
            code, output = run_main(args, api_key, log_box)
        st.write(f"Finished in {time.time() - started:.0f}s with exit code **{code}**.")

        if code != 0:
            st.error("main.py exited with an error. Read the log above; common causes: invalid API key, missing package (`pip install -r requirements.txt`), or an unrecognised argument (use the `--help` button).")

        after = snapshot()
        new_files = sorted(
            [p for p, m in after.items() if p not in before or m > before[p]],
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        st.session_state["latest_files"] = [str(p) for p in new_files]

        st.subheader("3. Results")
        if not new_files:
            st.warning("No new report files were detected. Check the log for where main.py saved its output, or check the Reports tab.")
        else:
            names = [str(p.relative_to(ROOT)) for p in new_files]
            tabs = st.tabs(names)
            for t, p in zip(tabs, new_files):
                with t:
                    show_file(p)

with tab_reports:
    st.subheader("Browse existing reports")
    all_files = sorted(snapshot().items(), key=lambda kv: kv[1], reverse=True)
    if not all_files:
        st.info("No report files found yet. Run an audit first (or check demo_output/).")
    else:
        options = {str(p.relative_to(ROOT)): p for p, _ in all_files}
        choice = st.selectbox("Report file", list(options.keys()))
        show_file(options[choice])
