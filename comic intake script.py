import streamlit as st
import requests
import pandas as pd
import datetime
from urllib.parse import quote
import time

# ── CONFIG ──
COMICVINE_KEY = st.secrets["COMICVINE_KEY"]
GOUPC_KEY = st.secrets.get("GOUPC_KEY", "")  # Add your Go-UPC trial key here in secrets!
UPC_BASE_URL = "https://go-upc.com/api/v1/code/"  # New endpoint
COMICVINE_BASE_URL = "https://comicvine.gamespot.com/api/"
PASSWORD = "Y0uareappreciated!"  # CHANGE THIS

# ── Session State ──
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

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
st.markdown("Now using Go-UPC for initial barcode lookup (request free trial key at https://go-upc.com/plans/api/trial). Enriches via Comic Vine.")

vendor_id = st.text_input("Vendor ID / Customer ID", placeholder="Enter Vendor or Customer ID Number", help="...")
condition = st.selectbox("Comic Condition...", options=["New", "Used", "Vintage", "Rescue", "Artisan Supply"], index=0, help="...")
barcodes_text = st.text_area("Barcodes (one per line, dashes/spaces OK):", height=180, placeholder="72513025474003041\n...")

if st.button("Fetch Comic Details", type="primary"):
    if not barcodes_text.strip():
        st.warning("Please enter at least one barcode.")
    elif not GOUPC_KEY:
        st.error("GOUPC_KEY not set in Streamlit secrets! Request free trial at https://go-upc.com/plans/api/trial, then add key.")
    else:
        with st.spinner("Querying Go-UPC → Comic Vine..."):
            barcode_tuples = []
            for line in barcodes_text.splitlines():
                cleaned = line.strip().replace("-", "").replace(" ", "")
                if not cleaned or not cleaned.isdigit():
                    continue
                original = cleaned
                base_upc = cleaned[:12] if len(cleaned) >= 12 else cleaned
                supplement = cleaned[12:] if len(cleaned) > 12 else ""
                barcode_tuples.append((original, base_upc, supplement))

            results = []
            missing = []
            headers_cv = {"User-Agent": "StreamlitComicApp/1.0"}
            headers_goupc = {"Authorization": f"Bearer {GOUPC_KEY}"}

            for full_barcode, base_upc, supplement in barcode_tuples:
                try:
                    issue_num = ""
                    variant = "Main"
                    print_num = "1"
                    if len(supplement) == 5 and supplement.isdigit():
                        issue_raw = supplement[:3]
                        issue_num = str(int(issue_raw)) if issue_raw != "000" else ""
                        var_digit = supplement[3]
                        if var_digit != "0" and var_digit != "1":
                            variant = f"Cover {var_digit}"
                        print_num = supplement[4]

                    # Go-UPC lookup: try full, then base
                    upc_to_use = full_barcode if len(full_barcode) > 12 else base_upc
                    upc_url = f"{UPC_BASE_URL}{upc_to_use}"
                    resp_upc = requests.get(upc_url, headers=headers_goupc, timeout=10)
                    time.sleep(1)  # Polite rate

                    if resp_upc.status_code != 200:
                        upc_url = f"{UPC_BASE_URL}{base_upc}"
                        resp_upc = requests.get(upc_url, headers=headers_goupc, timeout=10)
                        time.sleep(1)

                    resp_upc.raise_for_status()
                    data_upc = resp_upc.json()

                    if "error" in data_upc:
                        missing.append(f"{full_barcode} (Go-UPC: {data_upc.get('error', 'No data')})")
                        continue

                    title_from_upc = data_upc.get("name", "") or data_upc.get("description", "") or "Unknown Title"
                    desc_upc = data_upc.get("description", "")
                    image_upc = data_upc.get("image_url", "") or ""  # Confirm field name after test

                    msrp = float(data_upc.get("price", 0) or 0)  # May vary; fallback 0

                    # Comic Vine enrichment (unchanged)
                    search_query = title_from_upc.strip()
                    if issue_num:
                        search_query += f" #{issue_num}"
                    if variant != "Main":
                        search_query += f" {variant.lower()}"
                    query_encoded = quote(search_query)

                    cv_search_url = f"{COMICVINE_BASE_URL}search/?api_key={COMICVINE_KEY}&format=json&query={query_encoded}&resources=issue&limit=3"
                    resp_cv_search = requests.get(cv_search_url, headers=headers_cv, timeout=10)
                    resp_cv_search.raise_for_status()
                    data_cv = resp_cv_search.json()

                    if data_cv.get("number_of_total_results", 0) == 0:
                        missing.append(f"{full_barcode} (no Comic Vine match)")
                        continue

                    result = data_cv["results"][0]
                    detail_url = f"{result['api_detail_url']}?api_key={COMICVINE_KEY}&format=json"
                    resp_detail = requests.get(detail_url, headers=headers_cv, timeout=10)
                    resp_detail.raise_for_status()
                    detail = resp_detail.json()["results"]

                    series_name = detail.get("volume", {}).get("name", "").strip()
                    issue_num_cv = detail.get("issue_number", "")
                    subtitle = detail.get("name", "").strip()
                    cover_date = detail.get("cover_date", "")

                    if subtitle and subtitle.lower() != series_name.lower() and subtitle.lower() != "one-shot":
                        full_title = f"{series_name} #{issue_num_cv} - {subtitle}" if issue_num_cv else f"{series_name} - {subtitle}"
                    elif series_name and issue_num_cv:
                        full_title = f"{series_name} #{issue_num_cv}"
                    else:
                        full_title = series_name or title_from_upc or "Unknown Title"

                    person_credits = detail.get("person_credits", [])
                    writers = []
                    artists = []
                    for credit in person_credits:
                        name = credit.get("person", {}).get("name", "").strip()
                        role = credit.get("role", "").lower().strip()
                        if name:
                            if any(kw in role for kw in ["writer", "story", "script"]):
                                writers.append(name)
                            elif any(kw in role for kw in ["art", "penciler", "inker", "artist", "pencils", "colors", "letterer", "cover"]):
                                artists.append(name)

                    image_url = (
                        image_upc or
                        detail.get("image", {}).get("original_url") or
                        detail.get("image", {}).get("medium_url") or
                        detail.get("image", {}).get("small_url") or
                        ""
                    )

                    publisher = detail.get("volume", {}).get("publisher", {}).get("name", data_upc.get("brand", ""))

                    row = {
                        "Full Title": full_title,
                        "Barcode": full_barcode,
                        "Series": series_name,
                        "Issue Number": issue_num_cv or issue_num,
                        "Publisher": publisher,
                        "Release Date": cover_date,
                        "Writer(s)": "; ".join(set(writers)) if writers else "",
                        "Artist(s)": "; ".join(set(artists)) if artists else "",
                        "Description": (detail.get("description") or desc_upc or "").strip(),
                        "Image URL": image_url,
                        "Extracted Issue #": issue_num,
                        "Variant": variant,
                        "Print #": print_num,
                        "Condition": condition,
                        "Recorded Price (UPC)": f"${msrp:.2f}" if msrp > 0 else "",
                    }

                    suggested_price = ""
                    if condition == "New":
                        suggested_price = msrp
                    elif condition == "Used":
                        suggested_price = msrp * 0.5
                    elif condition == "Rescue":
                        suggested_price = 1.00
                    row["Suggested Selling Price"] = f"${suggested_price:.2f}" if suggested_price else ""

                    results.append(row)

                except Exception as e:
                    missing.append(f"{full_barcode} (error: {str(e)})")

            if results:
                df = pd.DataFrame(results)
                st.success(f"Found details for {len(results)} comics")
                st.dataframe(df, use_container_width=True, hide_index=True)

                now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                vendor_part = vendor_id.strip() if vendor_id.strip() else "batch"
                filename = f"{vendor_part}_comics_{now}.csv"
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button("↓ Download CSV", csv, filename, "text/csv")

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

if st.button("Clear Form for Next Batch"):
    st.rerun()
