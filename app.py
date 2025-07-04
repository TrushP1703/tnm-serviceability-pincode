import streamlit as st
import pandas as pd
import os

# Set page config
st.set_page_config(
    page_title="TNM Serviceability Checker",
    layout="centered",
    page_icon="📦"
)

# Title
st.markdown("<h1 style='text-align: left;'>📦 TNM Serviceability Checker</h1>", unsafe_allow_html=True)
st.markdown("Easily check if a pincode is serviceable by your selected service type.")

# Service selection
service_type = st.selectbox("🛠️ Service Type", ["4W_Tyre", "4W_Battery", "2W_Tyre", "2W_Battery"])

# Pincode input
pincode = st.text_input("📍 Enter Pincode")

# Button to trigger check
check = st.button("🔍 Check Serviceability")

if check:
    # Validate pincode
    if not pincode.isdigit() or len(pincode) != 6:
        st.error("🚫 Invalid pincode. Enter a number like 400001.")
    else:
        try:
            # Load sheet securely from environment
            sheet_url = os.getenv("GOOGLE_SHEET_URL")
            df = pd.read_csv(sheet_url)

            # Convert pincode to int
            pincode = int(pincode)

            # Filter row
            row = df[df["Pincode"] == pincode]

            if row.empty:
                st.error("❌ Not Serviceable")
            else:
                row = row.iloc[0]
                serviceable = row[f"{service_type.replace('_', ' ')} Order"].strip().lower() == "yes"

                if serviceable:
                    st.success("✅ Serviceable")

                    # 🚚 Vendor fitment logic
                    if service_type == "4W_Tyre":
                        fitment = row["4W Tyre (vendor fitment)"].strip().lower()
                        fee = row["Extra fitment fees 4W Tyre if applicable in Rs."]
                    elif service_type == "4W_Battery":
                        fitment = row["Battery (vendor fitment)"].strip().lower()
                        fee = row["Extra fitment fees 4W Battery if applicable in Rs."]
                    elif service_type == "2W_Battery":
                        fitment = row["Battery (vendor fitment)"].strip().lower()
                        fee = row["Extra fitment fees 2W Battery if applicable in Rs."]
                    elif service_type == "2W_Tyre":
                        fitment = ""  # Not shown
                        fee = 0

                    if service_type in ["4W_Tyre", "4W_Battery", "2W_Battery"]:
                        if fitment == "yes":
                            st.info("🚚 Vendor Fitment Available")
                        else:
                            st.info("🚚 Vendor Fitment Not Available")

                    if isinstance(fee, (int, float)) and fee > 0:
                        st.warning(f"💰 Fitment Fee: ₹{fee}")

                    # Remark logic
                    if service_type == "4W_Tyre":
                        other_services = [
                            row["4W Battery Order"].strip().lower(),
                            row["2W Tyre Order"].strip().lower(),
                            row["2W Battery Order"].strip().lower()
                        ]
                        if all(s == "no" for s in other_services):
                            st.info("📝 Remark: Only 4W Tyre available — check with CM before confirming.")
                        elif row["Remark"].strip():
                            st.info(f"📝 Remark: {row['Remark'].strip()}")

                    elif service_type == "4W_Battery":
                        if row["Remark"].strip():
                            st.info(f"📝 Remark: {row['Remark'].strip()}")

                else:
                    st.error("❌ Not Serviceable")

        except Exception as e:
            st.error("❌ Something went wrong while checking serviceability.")
