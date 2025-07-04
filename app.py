import streamlit as st
import pandas as pd
import os

# Get sheet URL from environment variable
SHEET_URL = os.getenv("GSHEET_URL")

# App title and intro
st.set_page_config(page_title="TNM Serviceability Checker", layout="centered")
st.markdown("## 📦 TNM Serviceability Checker")
st.markdown("Easily check if a pincode is serviceable by your selected service type.")

# Service type input
service_type = st.selectbox("🛠️ Service Type", ["4W_Tyre", "4W_Battery", "2W_Tyre", "2W_Battery"])
pincode_input = st.text_input("🏣 Enter Pincode")

# Button to trigger lookup
if st.button("🔍 Check Serviceability"):
    if not pincode_input.isdigit():
        st.error("🚫 Invalid pincode. Enter a number like 400001.")
    else:
        df = pd.read_csv(SHEET_URL)
        df['Pincode'] = df['Pincode'].astype(str)

        row = df[df['Pincode'] == pincode_input]

        if row.empty:
            st.error("❌ Not Serviceable")
        else:
            service_value = row.iloc[0][f"{service_type.replace('_', ' ')} Order"]
            vendor_column = None

            if service_type == "4W_Tyre":
                vendor_column = "4W Tyre (vendor fitment)"
            elif service_type == "4W_Battery":
                vendor_column = "Battery (vendor fitment)"
            elif service_type == "2W_Battery":
                vendor_column = "Battery (vendor fitment)"

            if service_value.strip().lower() == "yes":
                st.success("✅ Serviceable")

                # Vendor fitment logic (only for 4W_Tyre, 4W_Battery, 2W_Battery)
                if vendor_column:
                    vendor_fitment = row.iloc[0][vendor_column]
                    if vendor_fitment.strip().lower() == "yes":
                        st.info("🚚 Vendor Fitment Available")
                    else:
                        st.info("🚚 Vendor Fitment Not Available")

                # Extra fitment fees
                fee_col = [col for col in row.columns if "Extra fitment fees" in col and service_type.split("_")[0] in col and service_type.split("_")[1] in col]
                if fee_col:
                    fee = row.iloc[0][fee_col[0]]
                    if pd.notna(fee) and float(fee) > 0:
                        st.warning(f"💰 Fitment Fee: ₹{fee}")

                # Remark display logic
                remark = row.iloc[0]["Remark"]
                if service_type in ["4W_Tyre", "4W_Battery"] and pd.notna(remark):
                    st.info(f"📝 Remark: {remark}")

                # Additional condition for "only 4W Tyre available"
                if service_type == "4W_Tyre":
                    if (
                        row.iloc[0]["4W Tyre Order"].strip().lower() == "yes" and
                        row.iloc[0]["4W Battery Order"].strip().lower() != "yes" and
                        row.iloc[0]["2W Tyre Order"].strip().lower() != "yes" and
                        row.iloc[0]["2W Battery Order"].strip().lower() != "yes"
                    ):
                        st.info("🟡 Remark: Only 4W Tyre available — check with CM before confirming.")
            else:
                st.error("❌ Not Serviceable")
