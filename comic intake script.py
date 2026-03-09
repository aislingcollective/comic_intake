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

# ── Session State ──
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
st.markdown("Internal use only. Paste barcodes (one per line) — supports 12-digit or 17-digit (with 5-digit supplement). Pulls series/title from UPC, parses issue/variant/print from supplement, then enriches via Comic Vine.")

vendor_id = st.text_input(
    "Vendor ID / Customer ID",
    placeholder="Enter Vendor or Customer ID Number",
    help="This will be part of the downloaded CSV filename"
)

condition = st.selectbox(
    "Comic Condition (applies to all in this batch)",
    options=["New", "Used", "Vintage", "Rescue", "Artisan Supply"],
    index=0,
    help="This will appear in a new 'Condition' column for every comic"
)

barcodes_text = st.text_area(
    "Barcodes (one per line, dashes/spaces OK):",
    height=180,
    placeholder="72513025474003041\n76194134274005021\n..."
)

def get_cover_url_from_upc(item: dict) -> str:
    images = item.get("images", [])
    for img in images:
        if isinstance(img, str) and img.strip():  # skip None, empty, or non-string
            return img.strip()
    return ""

if st.button("Fetch Comic Details", type="primary"):
    if not barcodes_text.strip():
        st.warning("Please enter at least one barcode.")
    else:
        with st.spinner("Querying UPC (base + supplement-aware) → Comic Vine..."):
            # Process barcodes: handle 12 or 17 digits
            barcode_tuples = []
            for line in barcodes_text.splitlines():
                cleaned = line.strip().replace("-", "").replace(" ", "")
                if not cleaned or not cleaned.isdigit():
                    continue
                original = cleaned
                if len(cleaned) == 17:
                    base_upc = cleaned[:12]
                    supplement = cleaned[12:]
                elif len(cleaned) == 12:
                    base_upc = cleaned
                    supplement = ""
                else:
                    continue  # skip invalid lengths
                barcode_tuples.append((original, base_upc, supplement))

            results = []
            missing = []
            headers_cv = {"User-Agent": "StreamlitComicApp/1.0"}

            for full_barcode, base_upc, supplement in barcode_tuples:
                try:
                    # Parse supplement first (independent of UPC success)
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

                    # Try UPC lookup: full first, then base
                    upc_url = f"{UPC_BASE_URL}lookup?upc={full_barcode}"
                    resp_upc = requests.get(upc_url, timeout=10)
                    if resp_upc.status_code != 200:
                        upc_url = f"{UPC_BASE_URL}lookup?upc={base_upc}"
                        resp_upc = requests.get(upc_url, timeout=10)
                    resp_upc.raise_for_status()
                    data_upc = resp_upc.json()
                    items = data_upc.get("items", [])
                    if not items:
                        missing.append(full_barcode)
                        continue
                    item = items[0]

                    title_from_upc = item.get("title", "") or item.get("description", "") or "Unknown Title"
                    desc_upc = item.get("description", "")
                    image_upc = get_cover_url_from_upc(item)

                    msrp = 0.0
                    offers = item.get("offers", [])
                    if offers:
                        msrp = float(offers[0].get("price", 0.0) or 0)
                    if msrp == 0:
                        msrp = float(item.get("lowest_recorded_price", 0) or 0)

                    # Build precise Comic Vine search query
                    search_query = title_from_upc.strip()
                    if issue_num:
                        search_query += f" #{issue_num}"
                    if variant != "Main":
                        search_query += f" {variant.lower()}"
                    if not search_query.strip():
                        search_query = title_from_upc
                    query_encoded = quote(search_query)

                    cv_search_url = f"{COMICVINE_BASE_URL}search/?api_key={COMICVINE_KEY}&format=json&query={query_encoded}&resources=issue&limit=3"
                    resp_cv_search = requests.get(cv_search_url, headers=headers_cv, timeout=10)
                    resp_cv_search.raise_for_status()
                    data_cv = resp_cv_search.json()

                    if data_cv.get("number_of_total_results", 0) == 0:
                        missing.append(f"{full_barcode} (no Comic Vine match)")
                        continue

                    # Take first result
                    result = data_cv["results"][0]
                    detail_url = f"{result['api_detail_url']}?api_key={COMICVINE_KEY}&format=json"
                    resp_detail = requests.get(detail_url, headers=headers_cv, timeout=10)
                    resp_detail.raise_for_status()
                    detail = resp_detail.json()["results"]

                    # ── Extract & construct better fields ──
                    series_name = detail.get("volume", {}).get("name", "").strip()
                    issue_num_cv = detail.get("issue_number", "")
                    subtitle = detail.get("name", "").strip()
                    cover_date = detail.get("cover_date", "")

                    # Construct full title
                    if subtitle and subtitle.lower() != series_name.lower() and subtitle.lower() != "one-shot":
                        full_title = f"{series_name} #{issue_num_cv} - {subtitle}" if issue_num_cv else f"{series_name} - {subtitle}"
                    elif series_name and issue_num_cv:
                        full_title = f"{series_name} #{issue_num_cv}"
                    else:
                        full_title = series_name or title_from_upc or "Unknown Title"

                    # Split creators by role
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

                    # Image: UPC first (better for website), then Comic Vine
                    image_url = (
                        image_upc or
                        detail.get("image", {}).get("original_url") or
                        detail.get("image", {}).get("medium_url") or
                        detail.get("image", {}).get("small_url") or
                        ""
                    )

                    publisher = detail.get("volume", {}).get("publisher", {}).get("name", item.get("brand", ""))

                    row = {
                        "Full Title": full_title,
                        "Barcode": full_barcode,
                        "Series": series_name,
                        "Issue Number": issue_num_cv or issue_num,
                        "Publisher": publisher,
                        "Release Date": cover_date,  # renamed
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

                    # Suggested price logic
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

if st.button("Clear Form for Next Batch"):
    st.rerun()
