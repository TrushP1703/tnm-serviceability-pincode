import streamlit as st
import pandas as pd
import requests
from io import StringIO

# Google Sheet CSV URL
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTC7eGFDO4cthDWrY91NA5O97zFMeNREoy_wE5qDqCY6BcI__tBjsLJuZxAvaUyV48ZMZRJSQP1W-5G/pub?gid=0&single=true&output=csv"

# Load Data
@st.cache_data
def load_data():
    response = requests.get(SHEET_URL)
    df = pd.read_csv(StringIO(response.text), dtype={'Pincode': str})
    return df

df = load_data()

# UI Header
st.set_page_config(page_title="TNM Serviceability Checker", layout="centered")
st.markdown("<h1 style='text-align: center;'>📦 TNM Serviceability Checker</h1>", unsafe_allow_html=True)
st.markdown("#### <div style='text-align: center;'>Check if a pincode is serviceable for your selected service type.</div>", unsafe_allow_html=True)

# Inputs
service_type = st.selectbox("🛠️ Service Type", ["4W_Tyre", "4W_Battery", "2W_Tyre", "2W_Battery"])
pincode = st.text_input("📍 Enter Pincode", max_chars=6)
check = st.button("🔍 Check Serviceability")

# Column map
SERVICE_COLUMN = {
    "4W_Tyre": "4W Tyre Order",
    "4W_Battery": "4W Battery Order",
    "2W_Tyre": "2W Tyre Order",
    "2W_Battery": "2W Battery Order"
}

# Check Logic
if check:
    if not pincode.isdigit():
        st.error("🚫 Invalid pincode. Enter a number like 400001.")
    else:
        row = df[df['Pincode'] == pincode]
        if row.empty:
            st.error("🚫 Pincode not found.")
        else:
            row = row.iloc[0]
            is_serviceable = row[SERVICE_COLUMN[service_type]].strip().lower() == "yes"

            # Check if only 4W Tyre is available
            is_4w_only = (
                row["4W Tyre Order"].strip().lower() == "yes" and
                row["4W Battery Order"].strip().lower() == "no" and
                row["2W Tyre Order"].strip().lower() == "no" and
                row["2W Battery Order"].strip().lower() == "no"
            )

            if is_serviceable:
                st.success(f"✅ {service_type.replace('_', ' ')} is serviceable in {pincode}")

                # Add special warning if only 4W Tyre is serviceable
                if service_type == "4W_Tyre" and is_4w_only:
                    st.warning("🟡 Only 4W Tyre is serviceable — check with CM before confirming.")

                # Show remark if present
                remark = row.get("Remark", "")
                if pd.notna(remark) and remark.strip() and remark.strip() != "-":
                    st.info(f"📝 Remark: {remark.strip()}")

            else:
                st.error(f"❌ {service_type.replace('_', ' ')} is not serviceable in {pincode}")
