import streamlit as st
import requests
import pandas as pd
import datetime
import re
from streamlit_qrcode_scanner import qrcode_scanner  # pip install streamlit-qrcode-scanner

# ── CONFIG ──
PASSWORD = "Y0uareappreciated!"  # CHANGE THIS
GCD_BASE_URL = "https://www.comics.org/api/"
UPC_LOOKUP_URL = "https://api.barcodelookup.com/v3/products?barcode={upc}&key=your_key_here"  # Get free key at barcodelookup.com

# For demo, use a free public endpoint or mock; replace with real API key
# Alternative free-ish: https://go-upc.com/api (limited)

# ── Session State ──
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'scanned_upcs' not in st.session_state:
    st.session_state.scanned_upcs = []

# Password check (unchanged)
def check_password():
    if st.session_state.authenticated:
        return True
    pwd = st.text_input("Enter password:", type="password", key="pwd")
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
st.set_page_config(page_title="Comic Intake with Barcode Scan", layout="wide")
st.title("Comic Book Intake Tool with Barcode Scanning (GCD + UPC)")
st.markdown("""
Scan UPC barcodes from comic covers using your camera, or paste identifiers manually.  
Scanned UPCs → lookup title → try GCD enrichment.  
Note: UPC lookup is general (not comic-specific); results may need manual correction.
""")

vendor_id = st.text_input("Vendor / Store ID", placeholder="e.g. WEEKLY-BATCH")
condition = st.selectbox("Condition (batch)", options=[...], index=0)  # copy your options

# ── BARCODE SCANNER SECTION ──
st.subheader("Live Barcode Scanner (UPC on comic covers)")
qr_code = qrcode_scanner(key='scanner', camera_facing_mode="environment")  # back camera default on mobile

if qr_code:
    if qr_code not in st.session_state.scanned_upcs:
        st.session_state.scanned_upcs.append(qr_code)
        st.success(f"Scanned: {qr_code}")
    else:
        st.info("Already scanned this one.")

# Show scanned list
if st.session_state.scanned_upcs:
    st.write("Scanned UPCs:", ", ".join(st.session_state.scanned_upcs))

# Manual input fallback
comic_text = st.text_area("Manual: Series Issue [Year] or paste UPCs (one per line)", height=150,
                          placeholder="Batman 125\n754322345678\n...")

# Combine inputs
all_inputs = st.session_state.scanned_upcs + [line.strip() for line in comic_text.splitlines() if line.strip()]

def is_upc(s: str) -> bool:
    return s.isdigit() and len(s) in (12, 13)  # UPC-A 12, EAN-13 13

def lookup_upc(upc: str):
    # Replace with your API key or use go-upc.com free tier
    try:
        # Example using barcodelookup (sign up for free key)
        url = f"https://api.barcodelookup.com/v3/products?barcode={upc}&key=YOUR_FREE_KEY"
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            product = data.get("products", [{}])[0]
            title = product.get("title", "")
            # Try to parse comic-like title e.g. "Batman (2016) #125"
            match = re.search(r'([A-Za-z\s\-]+)\s*#?(\d+)', title)
            if match:
                series = match.group(1).strip()
                issue = match.group(2)
                return series, issue, None  # year unknown
            return None, None, title  # fallback to title search later
    except:
        pass
    return None, None, None

# Fetch function (enhanced with UPC parse)
def fetch_comic(identifier: str):
    if is_upc(identifier):
        series, issue, fallback_title = lookup_upc(identifier)
        if series and issue:
            return fetch_gcd_comic(series, issue)  # your existing function
        else:
            # Could search GCD by fallback_title, but skip for simplicity
            return None, f"UPC {identifier} → no comic parse"
    else:
        # Manual series issue parse (your existing logic)
        series, issue, year = parse_comic_input(identifier)
        if series and issue:
            return fetch_gcd_comic(series, issue, year)
        return None, "Parse error"

# Button to process all
if st.button("Process / Fetch Details"):
    results = []
    missing = []
    for inp in set(all_inputs):  # dedupe
        data, err = fetch_comic(inp)
        if data:
            # Add pricing/condition (your logic here)
            row = {**data, "Condition": condition, "Suggested Price": "..."}
            results.append(row)
        else:
            missing.append(f"{inp} ({err})")

    # Display DF, CSV download, covers (same as before)

# Clear scanned
if st.button("Clear Scanned UPCs"):
    st.session_state.scanned_upcs = []
    st.rerun()
