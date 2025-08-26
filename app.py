import os
import re
import requests
import pandas as pd
import streamlit as st
from io import StringIO

# =========================
# Page config (must be first)
# =========================
st.set_page_config(page_title="TNM Serviceability Checker", layout="centered")

# =========================
# Config (env / secrets)
# =========================
# Option A (recommended): set SHEET_ID and SHEET_GID in Render env (or .streamlit/secrets.toml)
# Option B: set SHEET_URL to a published CSV link (may rotate / rate-limit)
DEFAULT_PUBLISH_URL = (
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vTC7eGFDO4cthDWrY91NA5O97zFMeNREoy_wE5qDqCY6BcI__tBjsLJuZxAvaUyV48ZMZRJSQP1W-5G"
    "/pub?gid=0&single=true&output=csv"
)

SHEET_URL = st.secrets.get("SHEET_URL") or os.environ.get("SHEET_URL") or DEFAULT_PUBLISH_URL
SHEET_ID = st.secrets.get("SHEET_ID") or os.environ.get("SHEET_ID")  # from URL /d/<SHEET_ID>/
SHEET_GID = str(st.secrets.get("SHEET_GID") or os.environ.get("SHEET_GID") or "0")

USER_AGENT = {"User-Agent": "Mozilla/5.0 (compatible; ServiceabilityBot/1.0)"}

# Canonical service keys we expose in UI
SERVICE_CANONICAL = {
    "4W_Tyre": "4w tyre order",
    "4W_Battery": "4w battery order",
    "2W_Tyre": "2w tyre order",
    "2W_Battery": "2w battery order",
}

PINCODE_SYNONYMS = ["pincode", "pin code", "pin", "postal code", "postcode", "zip", "zip code"]

# =========================
# Helpers
# =========================
def _normalize_header(col: str) -> str:
    col = (col or "").strip().lower().replace("\ufeff", "")
    col = col.replace("_", " ")
    col = re.sub(r"\s+", " ", col)
    col = re.sub(r"[^a-z0-9 ]+", "", col)
    return col

def _guess_col(cols, targets, fuzzy_tokens=None):
    # exact match first
    for t in targets:
        if t in cols:
            return t
    # fuzzy: contains all tokens
    if fuzzy_tokens:
        for c in cols:
            if all(tok in c for tok in fuzzy_tokens):
                return c
    return None

def _resolve_pincode_col(cols):
    col = _guess_col(cols, PINCODE_SYNONYMS)
    if col:
        return col
    return _guess_col(cols, [], ["pin", "code"])

def _resolve_service_col(cols, canonical_text):
    exact = _guess_col(cols, [canonical_text])
    if exact:
        return exact
    return _guess_col(cols, [], canonical_text.split())

def _digits_only(s: str) -> str:
    return re.sub(r"\D", "", s or "")

def _looks_like_csv(text: str) -> bool:
    if not text:
        return False
    lower = text.lower()
    if "<html" in lower or "<!doctype html" in lower:
        return False
    return ("," in text or "\t" in text) and ("\n" in text)

def _candidate_urls():
    urls = []
    if SHEET_URL:
        urls.append(SHEET_URL)
    if SHEET_ID:
        urls.append(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={SHEET_GID}")
        urls.append(f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid={SHEET_GID}")
    return urls

# =========================
# Data loader with fallbacks
# =========================
@st.cache_data(ttl=300)
def load_data_with_fallbacks():
    """
    Returns on success:
        (df, resolved_service_columns, attempts)
    Returns on failure (no exception):
        (None, None, attempts, error_message)
    """
    attempts = []
    last_err = None

    for url in _candidate_urls():
        try:
            r = requests.get(url, timeout=20, headers=USER_AGENT, allow_redirects=True)
            attempts.append((url, r.status_code))
            if r.status_code == 200 and _looks_like_csv(r.text):
                df = pd.read_csv(StringIO(r.text), dtype=str)

                # normalize headers
                df.columns = [_normalize_header(c) for c in df.columns]

                # pincode col
                pincode_col = _resolve_pincode_col(list(df.columns))
                if not pincode_col:
                    return None, None, attempts, f"No pincode-like column found. Columns: {list(df.columns)}"
                if pincode_col != "pincode":
                    df = df.rename(columns={pincode_col: "pincode"})
                df["pincode"] = df["pincode"].astype(str).map(_digits_only)

                # resolve service cols
                resolved = {}
                for key, canonical in SERVICE_CANONICAL.items():
                    col = _resolve_service_col(list(df.columns), canonical)
                    if col:
                        resolved[key] = col
                    else:
                        # create a default "no" column if missing
                        df[canonical] = "no"
                        resolved[key] = canonical

                # remark column (optional)
                remark_col = next((c for c in df.columns if "remark" in c or "note" in c), None)
                if remark_col and remark_col != "remark":
                    df = df.rename(columns={remark_col: "remark"})

                return df, resolved, attempts

        except requests.RequestException as e:
            last_err = e
            attempts.append((url, f"EXC:{type(e).__name__}"))

    msg = "Could not fetch CSV from Google Sheets."
    if last_err:
        msg += f" Last error: {last_err}"
    return None, None, attempts, msg

# =========================
# UI header
# =========================
st.markdown("<h1 style='text-align: center;'>📦 TNM Serviceability Checker</h1>", unsafe_allow_html=True)
st.markdown(
    "#### <div style='text-align: center;'>Check if a pincode is serviceable for your selected service type.</div>",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("⚙️ Data Source")
    st.caption("Set SHEET_ID + SHEET_GID (recommended) or SHEET_URL via Render env or .streamlit/secrets.toml.")
    show_debug = st.checkbox("Show debug info", value=False)

# =========================
# Load data safely
# =========================
loaded = load_data_with_fallbacks()
if len(loaded) == 3:
    # success path
    df, SERVICE_COLUMN, attempts = loaded
else:
    # failure path: (None, None, attempts, msg)
    df, SERVICE_COLUMN, attempts, err_msg = loaded

if df is None:
    st.error(
        "❌ Could not load the Google Sheet.\n\n"
        "**Quick fixes:**\n"
        "1) In Google Sheets, set **Share → Anyone with the link (Viewer)**.\n"
        "2) Prefer the stable export URL:\n"
        "   `https://docs.google.com/spreadsheets/d/<SHEET_ID>/export?format=csv&gid=<GID>`\n"
        "3) In Render, set env vars: `SHEET_ID` and `SHEET_GID` (or `SHEET_URL`).\n\n"
        f"Details: {err_msg}"
    )
    if attempts:
        with st.expander("Debug: fetch attempts"):
            for url, code in attempts:
                st.write(code, url)
    st.stop()

if show_debug:
    st.write("Attempted URLs/status:", attempts)
    st.write("Detected columns:", list(df.columns))
    st.write("Resolved service columns:", SERVICE_COLUMN)

# =========================
# Inputs
# =========================
service_type = st.selectbox("🛠️ Service Type", list(SERVICE_CANONICAL.keys()))
pincode_input = st.text_input("📍 Enter Pincode", max_chars=6)
check = st.button("🔍 Check Serviceability")

# =========================
# Check Logic
# =========================
if check:
    pin = _digits_only(pincode_input)

    if len(pin) != 6:
        st.error("🚫 Invalid pincode. Enter a 6-digit number like 400001.")
    else:
        row_df = df[df["pincode"] == pin]

        if row_df.empty:
            st.error("🚫 Pincode not found.")
        else:
            row = row_df.iloc[0]
            # column name already resolved for the chosen service
            service_col = SERVICE_COLUMN[service_type]
            val = str(row.get(service_col, "")).strip().lower()
            is_serviceable = val == "yes"

            # helper to evaluate yes/no across possibly varied headers
            def safe_yes(canonical_text):
                mapping = {
                    "4w tyre order": SERVICE_COLUMN.get("4W_Tyre"),
                    "4w battery order": SERVICE_COLUMN.get("4W_Battery"),
                    "2w tyre order": SERVICE_COLUMN.get("2W_Tyre"),
                    "2w battery order": SERVICE_COLUMN.get("2W_Battery"),
                }
                col = mapping.get(canonical_text, canonical_text)
                return str(row.get(col, "")).strip().lower() == "yes"

            is_4w_only = (
                safe_yes("4w tyre order")
                and not safe_yes("4w battery order")
                and not safe_yes("2w tyre order")
                and not safe_yes("2w battery order")
            )

            if is_serviceable:
                st.success(f"✅ {service_type.replace('_', ' ')} is serviceable in {pin}")
                if service_type == "4W_Tyre" and is_4w_only:
                    st.warning("🟡 Only 4W Tyre is serviceable — check with CM before confirming.")
                remark = str(row.get("remark", "") or "").strip()
                if remark and remark != "-":
                    st.info(f"📝 Remark: {remark}")
            else:
                st.error(f"❌ {service_type.replace('_', ' ')} is not serviceable in {pin}")
