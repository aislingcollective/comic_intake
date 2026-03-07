import streamlit as st
import requests
import pandas as pd
import datetime

# ── CONFIG ──
API_KEY = st.secrets["ISBNDB_KEY"]  # Still using ISBNdb — consider Comic Vine / Metron in future
BASE_URL = "https://api2.isbndb.com/books"
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
st.set_page_config(page_title="Comic Book Intake Tool", layout="wide")
st.title("Comic Book Intake & Metadata Retrieval")
st.markdown(
    "Internal tool for comic book batches. Paste ISBNs (graphic novels & trades mostly) or identifiers. "
    "**Note**: Many single-issue comics **lack ISBNs** — data quality from ISBNdb can be spotty. "
    "Consider Comic Vine / Metron API migration in the future."
)

# Inputs
vendor_id = st.text_input(
    "Vendor / Customer / Store ID",
    placeholder="e.g. GA-2026-003 or COMICCON-ATL",
    help="Used in CSV filename"
)

condition = st.selectbox(
    "Comic Condition (applies to whole batch)",
    options=[
        "New / Sealed", "Near Mint", "Very Fine", "Fine", "Very Good", 
        "Good", "Fair", "Poor", "Graded (CGC)", "Key / High Grade", 
        "Reader Copy", "Bulk / Rescue", "Vintage (Pre-1980)"
    ],
    index=0,
    help="Comic-specific grading terms"
)

isbns_text = st.text_area(
    "ISBNs / Identifiers (one per line — dashes/spaces OK):",
    height=180,
    placeholder="9781302921569\n9781779511232\n..."
)

def get_cover_url(isbn: str, book_data: dict = None) -> str:
    """Try ISBNdb → Open Library fallback. Comic Vine/GCD would be better long-term."""
    if book_data:
        cover = book_data.get("CoverLinkOriginal") or book_data.get("image") or ""
        if cover and "http" in cover:
            return cover
    
    ol_url = f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
    try:
        head = requests.head(ol_url, timeout=4, allow_redirects=True)
        if head.status_code == 200:
            return ol_url
    except:
        pass
    return ""

if st.button("Fetch Comic Details", type="primary"):
    if not isbns_text.strip():
        st.warning("Please enter at least one ISBN / identifier.")
    else:
        with st.spinner("Querying ISBNdb (comic data may be incomplete)..."):
            identifiers = [
                line.strip().replace("-", "").replace(" ", "")
                for line in isbns_text.splitlines()
                if line.strip()
            ]
            results = []
            missing = []

            for ident in identifiers:
                try:
                    url = f"{BASE_URL}/{ident}"
                    headers = {
                        "Authorization": API_KEY,
                        "Accept": "application/json"
                    }
                    resp = requests.get(url, headers=headers, timeout=10)
                    resp.raise_for_status()
                    data = resp.json()
                    books_list = data.get("books", [])
                    if not books_list:
                        missing.append(ident)
                        continue
                    
                    book = books_list[0]
                    
                    description = (
                        book.get("overview") or
                        book.get("synopsis") or
                        book.get("excerpt") or
                        ""
                    )

                    image_url = get_cover_url(ident, book)

                    # Comic-attuned fields
                    row = {
                        "Series / Volume": book.get("title", "") or book.get("title_long", ""),
                        "Issue / Story Title": book.get("subtitle") or "",
                        "ISBN-13": book.get("isbn13", ""),
                        "ISBN-10": book.get("isbn10", ""),
                        "Cover Price / SRP": f"${book.get('msrp', 0):.2f}" if book.get("msrp") else "",
                        "Creators (W/A/P)": "; ".join([a for a in book.get("authors", []) if a]),
                        "Publisher": book.get("publisher", ""),
                        "Cover Date / Pub Date": book.get("date_published", ""),
                        "Page Count": book.get("pages", ""),
                        "Description / Synopsis": description[:800] + "..." if len(description) > 800 else description,
                        "Genres / Subjects": "; ".join([s for s in book.get("subjects", []) if s]),
                        "Characters / Teams (if known)": "",  # ISBNdb rarely has this — future Comic Vine field
                        "Image URL": image_url,
                        "Condition": condition,
                    }

                    msrp = book.get("msrp") or 0.0
                    try:
                        msrp = float(msrp)
                    except:
                        msrp = 0.0

                    # Comic-market pricing logic (very rough — adjust to your business)
                    if "New" in condition or "Sealed" in condition or "Graded" in condition:
                        suggested = msrp * 1.0
                    elif "Near Mint" in condition or "Very Fine" in condition or "Key" in condition:
                        suggested = msrp * 0.8
                    elif "Fine" in condition or "Very Good" in condition:
                        suggested = msrp * 0.4
                    elif "Bulk" in condition or "Rescue" in condition:
                        suggested = 1.00
                    elif "Vintage" in condition:
                        suggested = msrp * 1.2 if msrp > 0 else ""  # keys/vintage often appreciate
                    else:
                        suggested = msrp * 0.3

                    row["Suggested Selling Price"] = f"${suggested:.2f}" if suggested else ""

                    results.append(row)

                except Exception as e:
                    missing.append(f"{ident} ({str(e)})")

            if results:
                df = pd.DataFrame(results)
                st.success(f"Retrieved data for {len(results)} comics")
                st.dataframe(df, use_container_width=True, hide_index=True)

                now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
                vendor_part = vendor_id.strip() if vendor_id.strip() else "comic_batch"
                filename = f"{vendor_part}_{now}.csv"

                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "↓ Download Comic CSV",
                    csv,
                    file_name=filename,
                    mime="text/csv"
                )

                has_images = df["Image URL"].str.strip().astype(bool).any()
                if has_images:
                    st.subheader("Comic Covers (previews)")
                    cols = st.columns(5)
                    for idx, row in df.iterrows():
                        url = row["Image URL"]
                        title = row["Series / Volume"][:35] + "..." if len(row["Series / Volume"]) > 35 else row["Series / Volume"]
                        if url:
                            with cols[idx % 5]:
                                st.image(url, use_column_width=True, caption=title)
                        else:
                            with cols[idx % 5]:
                                st.caption(f"No cover\n{title}")
                else:
                    st.info("No covers found in this batch.")

            if missing:
                st.warning(f"Could not find / error for {len(missing)} entries:\n{', '.join(missing)}")

# Reset
if st.button("Clear for Next Batch"):
    st.rerun()
