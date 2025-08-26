import re
import requests
import pandas as pd
import streamlit as st
from io import StringIO

# ----------------------------
# Page config (should be first)
# ----------------------------
st.set_page_config(page_title="TNM Serviceability Checker", layout="centered")

# ----------------------------
# Config
# ----------------------------
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTC7eGFDO4cthDWrY91NA5O97zFMeNREoy_wE5qDqCY6BcI__tBjsLJuZxAvaUyV48ZMZRJSQP1W-5G/pub?gid=0&single=true&output=csv"

# Canonical service columns we expect (we'll resolve these against the actual headers)
SERVICE_CANONICAL = {
    "4W_Tyre": "4w tyre order",
    "4W_Battery": "4w battery order",
    "2W_Tyre": "2w tyre order",
    "2W_Battery": "2w battery order",
}

PINCODE_SYNONYMS = [
    "pincode", "pin code", "pin", "postal code", "postcode", "zip", "zip code"
]

# ----------------------------
# Helpers
# ----------------------------
def _normalize_header(col: str) -> str:
    col = (col or "").strip().lower().replace("\ufeff", "")
    # unify separators/spaces, drop extra punctuation
    col = col.replace("_", " ")
    col = re.sub(r"\s+", " ", col)
    col = re.sub(r"[^a-z0-9 ]+", "", col)
    return col

def _guess_col(cols, targets, fuzzy_tokens=None):
    # exact match
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
    # exact synonyms first
    col = _guess_col(cols, PINCODE_SYNONYMS)
    if col:
        return col
    # fuzzy tokens like ["pin","code"]
    return _guess_col(cols, [], ["pin", "code"])

def _resolve_service_col(cols, canonical_text):
    # try exact
    exact = _guess_col(cols, [canonical_text])
    if exact:
        return exact
    # fuzzy: all words must appear (e.g., "4w", "tyre", "order")
    tokens = canonical_text.split()
    return _guess_col(cols, [], tokens)

def _digits_only(s: str) -> str:
    return re.sub(r"\D", "", s or "")

# ----------------------------
# Data Load
# ----------------------------
@st.cache_data(ttl=300)
def load_data():
    r = requests.get(SHEET_URL, timeout=20)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text), dtype=str)

    # normalize headers
    df.columns = [_normalize_header(c) for c in df.columns]

    # find/standardize pincode column
    pincode_col = _resolve_pincode_col(list(df.columns))
    if not pincode_col:
        raise KeyError(
            f"No pincode-like column found. Got columns: {list(df.columns)}. "
            f"Expected one of: {PINCODE_SYNONYMS}"
        )
    if pincode_col != "pincode":
        df = df.rename(columns={pincode_col: "pincode"})

    # normalize pincode values to digits only
    df["pincode"] = df["pincode"].astype(str).map(_digits_only)

    # resolve service columns and rename to canonical keys for stable access
    resolved = {}
    for key, canonical in SERVICE_CANONICAL.items():
        resolved_col = _resolve_service_col(list(df.columns), canonical)
        if resolved_col:
            resolved[key] = resolved_col
        else:
            # if missing, still create a column of "no" to avoid KeyError
            df[canonical] = "no"
            resolved[key] = canonical

    # also try to resolve remark/remarks/notes
    remark_col = None
    for c in df.columns:
        if "remark" in c or "note" in c:
            remark_col = c
            break
    if remark_col and remark_col != "remark":
        df = df.rename(columns={remark_col: "remark"})

    return df, resolved

df, SERVICE_COLUMN = load_data()

# ----------------------------
# UI
# ----------------------------
st.markdown("<h1 style='text-align: center;'>📦 TNM Serviceability Checker</h1>", unsafe_allow_html=True)
st.markdown(
    "#### <div style='text-align: center;'>Check if a pincode is serviceable for your selected service type.</div>",
    unsafe_allow_html=True,
)

with st.sidebar:
    show_debug = st.checkbox("Show debug info", value=False)
    if show_debug:
        st.write("Detected columns:", list(df.columns))
        st.write("Resolved service columns:", SERVICE_COLUMN)

service_type = st.selectbox("🛠️ Service Type", list(SERVICE_CANONICAL.keys()))
pincode_input = st.text_input("📍 Enter Pincode", max_chars=6)
check = st.button("🔍 Check Serviceability")

# ----------------------------
# Check Logic
# ----------------------------
if check:
    pin = _digits_only(pincode_input)

    if len(pin) != 6:
        st.error("🚫 Invalid pincode. Enter a 6-digit number like 400001.")
    else:
        # match on normalized digits-only pincode
        row_df = df[df["pincode"] == pin]

        if row_df.empty:
            st.error("🚫 Pincode not found.")
        else:
            row = row_df.iloc[0]

            # resolve serviceability
            service_col = SERVICE_COLUMN[service_type]  # already resolved header name
            val = str(row.get(service_col, "")).strip().lower()
            is_serviceable = val == "yes"

            # compute 'only 4W Tyre' condition based on whatever headers exist
            def safe_yes(col_name_guess):
                # try exact canonical service column first by key mapping
                # then fall back to canonical text
                col = None
                # pick the resolved col for each canonical key
                mapping = {
                    "4w tyre order": SERVICE_COLUMN.get("4W_Tyre"),
                    "4w battery order": SERVICE_COLUMN.get("4W_Battery"),
                    "2w tyre order": SERVICE_COLUMN.get("2W_Tyre"),
                    "2w battery order": SERVICE_COLUMN.get("2W_Battery"),
                }
                col = mapping.get(col_name_guess, col_name_guess)
                v = str(row.get(col, "")).strip().lower()
                return v == "yes"

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
