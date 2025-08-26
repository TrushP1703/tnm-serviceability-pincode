import os
import re
import requests
import pandas as pd
import streamlit as st
from io import StringIO
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

# =========================
# Page config (must be first)
# =========================
st.set_page_config(page_title="TNM Serviceability Checker", layout="centered")

# =========================
# Config (ONLY SHEET_URL)
# =========================
DEFAULT_SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vTC7eGFDO4cthDWrY91NA5O97zFMeNREoy_wE5qDqCY6BcI__tBjsLJuZxAvaUyV48ZMZRJSQP1W-5G/pub?gid=0&single=true&output=csv"
)

def get_config_value(key: str, default: str):
    """Prefer env var, then secrets (if present), else default.
    Never access st.secrets unless wrapped in try/except."""
    # 1) ENV
    v = os.environ.get(key)
    if v:
        return v, "env"
    # 2) SECRETS (optional)
    try:
        v = st.secrets.get(key)  # may raise if no secrets.toml
        if v:
            return v, "secrets"
    except Exception:
        pass
    # 3) DEFAULT
    return default, "default"

SHEET_URL, SHEET_URL_SRC = get_config_value("SHEET_URL", DEFAULT_SHEET_URL)

USER_AGENT = {"User-Agent": "Mozilla/5.0 (compatible; ServiceabilityBot/1.0)"}

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
    for t in targets:
        if t in cols:
            return t
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

def _variants_of_sheet_url(u: str):
    """Generate a few safe variants of the same published CSV URL."""
    variants = []
    if not u:
        return variants

    variants.append(u)  # as-is

    try:
        p = urlparse(u)
        q = dict(parse_qsl(p.query, keep_blank_values=True))

        # force CSV
        q2 = dict(q); q2["output"] = "csv"
        v2 = urlunparse(p._replace(query=urlencode(q2, doseq=True)))
        variants.append(v2)

        # drop 'single' if present
        q3 = dict(q2); q3.pop("single", None)
        v3 = urlunparse(p._replace(query=urlencode(q3, doseq=True)))
        variants.append(v3)

        # cache-bust
        variants.append(v2 + ("&" if "?" in v2 else "?") + "cachebust=1")
    except Exception:
        pass

    # de-dup, preserve order
    out, seen = [], set()
    for v in variants:
        if v not in seen:
            out.append(v); seen.add(v)
    return out

# =========================
# Data loader with fallbacks
# =========================
@st.cache_data(ttl=300)
def load_data_with_fallbacks():
    """
    Success -> (df, resolved_service_columns, attempts)
    Failure -> (None, None, attempts, error_message)
    """
    attempts = []
    last_err = None

    for url in _variants_of_sheet_url(SHEET_URL):
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

                # service cols
                resolved = {}
                for key, canonical in SERVICE_CANONICAL.items():
                    col = _resolve_service_col(list(df.columns), canonical)
                    if col:
                        resolved[key] = col
                    else:
                        df[canonical] = "no"
                        resolved[key] = canonical

                # optional remark/notes
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
    st.caption("Using only SHEET_URL (env → secrets → default).")
    st.write("Source:", SHEET_URL_SRC)
    # Show URL if not from secrets (to avoid leaking secrets accidentally)
    if SHEET_URL_SRC != "secrets":
        st.code(f"SHEET_URL = {SHEET_URL}", language="bash")
    show_debug = st.checkbox("Show debug info", value=False)

# =========================
# Load data safely
# =========================
loaded = load_data_with_fallbacks()
if len(loaded) == 3:
    df, SERVICE_COLUMN, attempts = loaded
else:
    df, SERVICE_COLUMN, attempts, err_msg = loaded

if df is None:
    st.error(
        "❌ Could not load the Google Sheet via SHEET_URL.\n\n"
        "**Checks:**\n"
        "1) In Google Sheets: **File → Share → Publish to the web → Entire sheet → CSV** (republish after changes).\n"
        "2) Ensure the link ends with `output=csv`.\n"
        "3) If it still fails sometimes, re-copy the Publish link — Google rotates tokens occasionally.\n\n"
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
            service_col = SERVICE_COLUMN[service_type]
            val = str(row.get(service_col, "")).strip().lower()
            is_serviceable = val == "yes"

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
