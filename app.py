import streamlit as st
import pandas as pd
import requests
from io import StringIO

# Read the Google Sheet CSV
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vTC7eGFDO4cthDWrY91NA5O97zFMeNREoy_wE5qDqCY6BcI__tBjsLJuZxAvaUyV48ZMZRJSQP1W-5G/pub?gid=0&single=true&output=csv"

# Load data from Google Sheet
@st.cache_data
def load_data():
    response = requests.get(SHEET_URL)
    df = pd.read_csv(StringIO(response.text), dtype={'Pincode': str})
    return df

df = load_data()

# Set page config
st.set_page_config(page_title="TNM Serviceability Checker", layout="centered")
st.markdown("<h1 style='text-align: center;'>📦 TNM Serviceability Checker</h1>", unsafe_allow_html=True)
st.markdown("#### <div style='text-align: center;'>Easily check if a pincode is serviceable by your selected service type.</div>", unsafe_allow_html=True)

# UI Inputs
service_type = st.selectbox("🛠️ Service Type", ["4W_Tyre", "4W_Battery", "2W_Tyre", "2W_Battery"])
pincode = st.text_input("📍 Enter Pincode", max_chars=6)

# Button
check = st.button("🔍 Check Serviceability")

# Mapping
SERVICE_COLUMN = {
    "4W_Tyre": "4W Tyre Order",
    "4W_Battery": "4W Battery Order",
    "2W_Tyre": "2W Tyre Order",
    "2W_Battery": "2W Battery Order"
}
VENDOR_COLUMN = {
    "4W_Tyre": "4W Tyre (vendor fitment)",
    "4W_Battery": "Battery (vendor fitment)",
    "2W_Battery": "Battery (vendor fitment)",  # Shared column
}
FEE_COLUMN = {
    "4W_Tyre": "Extra fitment fees 4W Tyre if applicable in Rs.",
    "4W_Battery": "Extra fitment fees 4W Battery if applicable in Rs.",
    "2W_Tyre": "Extra fitment fees 2W Tyre if applicable in Rs.",
    "2W_Battery": "Extra fitment fees 2W Battery if applicable in Rs.",
}

# Logic
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

            # Check for special case: only 4W Tyre = Yes, rest = No
            is_4w_only = (
                row["4W Tyre Order"].strip().lower() == "yes" and
                row["4W Battery Order"].strip().lower() == "no" and
                row["2W Tyre Order"].strip().lower() == "no" and
                row["2W Battery Order"].strip().lower() == "no"
            )

            if is_serviceable:
                st.success("✅ Serviceable")

                # Vendor Fitment
                if service_type in VENDOR_COLUMN:
                    vendor_val = row.get(VENDOR_COLUMN[service_type], "").strip().lower()
                    if vendor_val == "yes":
                        st.info("🚚 Vendor Fitment Available")
                    else:
                        st.info("🚚 Vendor Fitment Not Available")

                # Fitment Fee
                fee = row.get(FEE_COLUMN[service_type], "")
                try:
                    if pd.notna(fee) and float(fee) > 0:
                        st.info(f"💰 Fitment Fee: ₹{int(float(fee))}")
                except ValueError:
                    pass  # Handle unexpected values like '-'

                # Remarks logic (updated)
                remark = row.get("Remark", "")
                if service_type == "4W_Tyre" and is_4w_only:
                    st.warning("🟡 Remark: Only 4W Tyre available — check with CM before confirming.")
                elif pd.notna(remark) and remark.strip() and remark.strip() != "-":
                    st.info(f"📝 Remark: {remark.strip()}")

            else:
                st.error("❌ Not Serviceable")
