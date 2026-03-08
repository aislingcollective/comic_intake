import streamlit as st
import requests
import pandas as pd
import datetime
import re

# ── CONFIG ──
PASSWORD = "Y0uareappreciated!"  # CHANGE THIS
GCD_BASE_URL = "https://www.comics.org/api/"

# Optional: Sign up for a free/low-cost key at https://www.barcodelookup.com/api or https://go-upc.com
# BARCODE_API_KEY = st.secrets.get("BARCODE_API_KEY", None)  # Add to Streamlit secrets if using paid API

# ── Session State ──
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'scanned_barcodes' not in st.session_state:
    st.session_state.scanned_barcodes = []  # list of processed results
if 'current_scan' not in st.session_state:
    st.session_state.current_scan = ""

# Password protection (unchanged)
def check_password():
    if st.session_state.authenticated:
        return True
    pwd = st.text_input("Enter password:", type="password", key="pwd_unique")
    if st.button("Login"):
        if pwd == PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False

if not check_password():
    st.stop()

# ── MAIN APP ──
st.set_page_config(page_title="Comic Intake - Barcode Ready", layout="wide")
st.title("Comic Book Intake Tool – Barcode Scanner Support")
st.markdown("""
**How to use your scanner:**
1. Click into the **Scan / Paste Barcode** field below (it should get focus).
2. Scan a comic's UPC barcode — the scanner will type the number + Enter automatically.
3. The app will process it right away, clear the field, and ready for the next scan.
4. Results appear in the table below.

Tip: Most comic UPCs are 12 digits (UPC-A) or 17 digits (with supplement). If your scanner adds a prefix/suffix, adjust the parsing logic.
""")

vendor_id = st.text_input("Vendor / Store ID", placeholder="e.g. WEEKLY-BATCH-03")
condition = st.selectbox(
    "Condition (applies to batch)",
    options=[
        "New / Sealed", "Near Mint", "Very Fine", "Fine", "Very Good", 
        "Good", "Fair", "Poor", "Graded (CGC)", "Key / High Grade", 
        "Reader Copy", "Bulk / Rescue", "Vintage (Pre-1980)"
    ],
    index=0
)

# Focused scan input – use unique key to avoid conflicts
scan_input = st.text_input(
    "Scan / Paste Barcode Here (scanner auto-enters)",
    value=st.session_state.current_scan,
    key="scan_input_unique",
    placeholder="UPC will appear here automatically...",
    help="Click here first, then scan. Field clears after processing."
)

# Auto-process on change (when scanner "submits" via Enter)
if scan_input and scan_input != st.session_state.current_scan:
    barcode = scan_input.strip()
    st.session_state.current_scan = ""
    
    # Quick validation (comic UPCs often 12-17 digits)
    if re.match(r'^\d{8,20}$', barcode):  # flexible for supplements/prefixes
        with st.spinner(f"Processing barcode: {barcode}"):
            # Step 1: Optional general UPC lookup (uncomment if you have API key)
            title, series, issue = None, None, None
            # if BARCODE_API_KEY:
            #     try:
            #         resp = requests.get(f"https://api.barcodelookup.com/v3/products?barcode={barcode}&key={BARCODE_API_KEY}")
            #         if resp.ok:
            #             prod = resp.json().get("products", [{}])[0]
            #             title = prod.get("title", "")
            #             # Rough parse: "Batman #125 (2024)" → series="Batman", issue="125"
            #             m = re.search(r'([\w\s\-]+?)\s*#?(\d+)', title, re.I)
            #             if m:
            #                 series = m.group(1).strip()
            #                 issue = m.group(2)
            #     except:
            #         pass
            
            # Step 2: If no parse, or fallback – use GCD with manual input or skip to note
            data, error = None, None
            if series and issue:
                data, error = fetch_gcd_comic(series, issue)  # your GCD function from before
            else:
                error = "No comic parse from UPC – enter series/issue manually or check scanner output"
            
            if data:
                # Pricing logic (customize!)
                msrp = 0.0
                suggested = ""  # or compute based on condition/msrp
                row = {
                    **data,
                    "UPC": barcode,
                    "Condition": condition,
                    "Suggested Selling Price": f"${suggested:.2f}" if suggested else "Manual",
                }
                st.session_state.scanned_barcodes.append(row)
                st.success(f"Added: {data.get('Series', '')} #{data.get('Issue #', '')}")
            else:
                st.warning(f"Failed: {barcode} – {error}")
                # Optionally add raw UPC for manual later
                st.session_state.scanned_barcodes.append({"UPC": barcode, "Status": "Failed – manual needed"})
    else:
        st.info("Waiting for valid barcode...")

# Display accumulated results
if st.session_state.scanned_barcodes:
    df = pd.DataFrame(st.session_state.scanned_barcodes)
    st.subheader("Scanned Comics")
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    csv = df.to_csv(index=False).encode("utf-8")
    now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
    vendor_part = vendor_id.strip() or "batch"
    st.download_button(
        "Download CSV",
        csv,
        f"{vendor_part}_scans_{now}.csv",
        "text/csv"
    )

# Clear button
if st.button("Clear All Scans & Start New Batch"):
    st.session_state.scanned_barcodes = []
    st.session_state.current_scan = ""
    st.rerun()

# Your existing GCD fetch / parse / cover functions go here (copy from previous version)
def parse_comic_input(...): ...  # etc.
def fetch_gcd_comic(...): ...
def get_cover_url(...): ...

# Optional: Auto-focus JS hack (paste in st.markdown with unsafe_allow_html=True)
st.markdown(
    """
    <script>
    document.addEventListener('DOMContentLoaded', function() {
        const inputs = parent.document.querySelectorAll('input[type="text"]');
        for (let input of inputs) {
            if (input.placeholder.includes('Scan')) {
                input.focus();
                break;
            }
        }
    });
    </script>
    """,
    unsafe_allow_html=True
)
