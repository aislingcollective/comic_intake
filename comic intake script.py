import streamlit as st
import requests
import pandas as pd
import datetime
from urllib.parse import quote

# ── CONFIG ──
COMICVINE_KEY = st.secrets["COMICVINE_KEY"]  # Set this in Streamlit Cloud secrets
UPC_BASE_URL = "https://api.upcitemdb.com/prod/trial/"
COMICVINE_BASE_URL = "https://comicvine.gamespot.com/api/"
PASSWORD = "Y0uareappreciated!"  # CHANGE THIS to something only your team knows!

# ── Session State (only keeping authenticated) ──
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# Simple password protection
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
st.set_page_config(page_title="Barcode Retrieval for Comics Intake", layout="wide")
st.title("Barcode Retrieval for Comics Intake")
st.markdown("Internal use only. Paste barcodes (one per line) to get title, series, issue, description, etc. — now with comic covers!")

# Inputs — NO value= or key= on text_input and text_area so they clear properly
vendor_id = st.text_input(
    "Vendor ID / Customer ID",
    placeholder="Enter Vendor or Customer ID Number",
    help="This will be part of the downloaded CSV filename"
)
condition = st.selectbox(
    "Comic Condition (applies to all in this batch)",
    options=["New", "Used", "Vintage", "Rescue", "Artisan Supply"],
    index=0,  # defaults to "New"
    help="This will appear in a new 'Condition' column for every comic"
)
barcodes_text = st.text_area(
    "Barcodes (one per line, dashes/spaces OK):",
    height=180,
    placeholder="761941306407\n759606089369\n..."
)

def get_cover_url_from_upc(item: dict) -> str:
    """Get cover from UPC item if available."""
    images = item.get("images", [])
    if images:
        return images[0]
    return ""

if st.button("Fetch Comic Details", type="primary"):
    if not barcodes_text.strip():
        st.warning("Please enter at least one barcode.")
    else:
        with st.spinner("Querying UPC database and Comic Vine (one by one for best detail)..."):
            barcodes = [
                line.strip().replace("-", "").replace(" ", "")
                for line in barcodes_text.splitlines()
                if line.strip()
            ]
            results = []
            missing = []
            headers_cv = {"User-Agent": "StreamlitComicApp/1.0"}
            for barcode in barcodes:
                try:
                    # First, query UPC database for basic info
                    upc_url = f"{UPC_BASE_URL}lookup?upc={barcode}"
                    resp_upc = requests.get(upc_url, timeout=10)
                    resp_upc.raise_for_status()
                    data_upc = resp_upc.json()
                    items = data_upc.get("items", [])
                    if not items:
                        missing.append(barcode)
                        continue
                    item = items[0]
                    title = item.get("title", "") or item.get("description", "")
                    desc_upc = item.get("description", "")
                    image_upc = get_cover_url_from_upc(item)
                    msrp = 0.0
                    offers = item.get("offers", [])
                    if offers:
                        msrp = offers[0].get("price", 0.0)
                    if msrp == 0.0:
                        msrp = item.get("lowest_recorded_price", 0.0)

                    # Now, use title to search Comic Vine
                    if not title:
                        missing.append(f"{barcode} (no title from UPC)")
                        continue
                    query = quote(title)
                    cv_search_url = f"{COMICVINE_BASE_URL}search/?api_key={COMICVINE_KEY}&format=json&query={query}&resources=issue&limit=1"
                    resp_cv_search = requests.get(cv_search_url, headers=headers_cv, timeout=10)
                    resp_cv_search.raise_for_status()
                    data_cv_search = resp_cv_search.json()
                    if data_cv_search.get("number_of_total_results", 0) == 0:
                        missing.append(f"{barcode} (no Comic Vine match)")
                        continue
                    result = data_cv_search["results"][0]
                    detail_url = f"{result['api_detail_url']}?api_key={COMICVINE_KEY}&format=json"
                    resp_detail = requests.get(detail_url, headers=headers_cv, timeout=10)
                    resp_detail.raise_for_status()
                    detail = resp_detail.json()["results"]

                    # Extract data from Comic Vine
                    full_title = detail.get("name", title)
                    series = detail["volume"].get("name", "")
                    issue_num = detail.get("issue_number", "")
                    publish_date = detail.get("cover_date", "")
                    description = detail.get("description", desc_upc)
                    image_url = detail["image"].get("original_url", image_upc)
                    creators_list = [c["name"] for c in detail.get("person_credits", [])]
                    creators = "; ".join(creators_list)
                    publisher = detail["volume"].get("publisher", {}).get("name", item.get("brand", ""))

                    row = {
                        "Full Title": full_title,
                        "Barcode": barcode,
                        "Series": series,
                        "Issue Number": issue_num,
                        "Publisher": publisher,
                        "Publish Date": publish_date,
                        "Creators": creators,
                        "Description": description,
                        "Image URL": image_url,
                        "Condition": condition,
                    }

                    # Suggested price logic (adapted from book app)
                    suggested_price = ""
                    if condition == "New":
                        suggested_price = msrp
                    elif condition == "Used":
                        suggested_price = msrp * 0.5
                    elif condition == "Rescue":
                        suggested_price = 1.00
                    elif condition in ["Vintage", "Artisan Supply"]:
                        suggested_price = ""
                    row["Suggested Selling Price"] = f"${suggested_price:.2f}" if suggested_price != "" else ""

                    results.append(row)
                except Exception as e:
                    missing.append(f"{barcode} (error: {str(e)})")
            if results:
                df = pd.DataFrame(results)
                st.success(f"Found details for {len(results)} comics")
                st.dataframe(df, use_container_width=True, hide_index=True)
                now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                vendor_part = vendor_id.strip() if vendor_id.strip() else "batch"
                filename = f"{vendor_part}_{now}.csv"
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "↓ Download CSV",
                    csv,
                    filename,
                    "text/csv"
                )
                has_images = df["Image URL"].str.strip().astype(bool).any()
                if has_images:
                    st.subheader("Comic Covers (Large previews)")
                    cols = st.columns(5)
                    for idx, row in df.iterrows():
                        img_url = row["Image URL"]
                        if img_url:
                            with cols[idx % 5]:
                                st.image(img_url, use_column_width=True, caption=row["Full Title"][:30] + "...")
                        else:
                            with cols[idx % 5]:
                                st.caption(f"No cover\n{row['Full Title'][:30]}...")
                else:
                    st.info("No comic covers were found for this batch.")
            if missing:
                st.warning(f"Skipped/missing for {len(missing)} barcodes: {', '.join(missing)}")

# Clear button — just rerun to refresh with empty widgets
if st.button("Clear Form for Next Batch"):
    st.rerun()
