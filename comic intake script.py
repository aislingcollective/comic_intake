import streamlit as st
import requests
import pandas as pd
import datetime
import re

# ── CONFIG ──
PASSWORD = "Y0uareappreciated!"  # CHANGE THIS to something only your team knows!
GCD_BASE_URL = "https://www.comics.org/api/"

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
st.set_page_config(page_title="Comic Intake Tool (GCD)", layout="wide")
st.title("Comic Book Intake & Metadata Retrieval (via Grand Comics Database)")
st.markdown("""
Internal tool for comic book batches.  
Enter comics as: **Series Name IssueNumber** (optional year) — one per line.  
Examples:  
- Batman 125  
- Amazing Spider-Man 300 1963  
- Spawn 1  

Note: Uses comics.org API — series name must match closely. Data quality is excellent for single issues but API is prototype (may change).
""")

# Inputs
vendor_id = st.text_input(
    "Vendor / Customer / Store ID",
    placeholder="e.g. GA-2026-003 or WEEKLY-BATCH",
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
    help="Comic-specific grading"
)

comic_text = st.text_area(
    "Comics (one per line — Series Issue [Year]):",
    height=180,
    placeholder="Batman 125\nAmazing Spider-Man 300 1963\nSpawn 1\n..."
)

def parse_comic_input(line: str):
    """Parse 'Series Name Issue [Year]' → series, issue, year"""
    line = line.strip()
    if not line:
        return None, None, None
    
    # Split on spaces, detect last as issue, penultimate as possible year
    parts = re.split(r'\s+', line)
    if len(parts) < 2:
        return None, None, None
    
    issue = parts[-1]
    year = None
    if len(parts) >= 3 and parts[-2].isdigit() and len(parts[-2]) == 4:
        year = parts[-2]
        series = " ".join(parts[:-2])
    else:
        series = " ".join(parts[:-1])
    
    return series, issue, year

def get_cover_url(issue_data: dict, issue_id: str = None) -> str:
    """Extract cover from GCD data or fallback"""
    cover = issue_data.get("image") or issue_data.get("cover_url") or ""
    if cover and "http" in cover:
        return cover
    # Common GCD cover pattern (if we have ID)
    if issue_id:
        return f"https://www.comics.org/issue/{issue_id}/cover/"
    return ""

def fetch_gcd_comic(series: str, issue: str, year: str = None):
    """Fetch from GCD API"""
    series_slug = series.replace(" ", "%20").replace("(", "%28").replace(")", "%29").replace("&", "%26")
    url = f"{GCD_BASE_URL}series/name/{series_slug}/issue/{issue}/"
    if year:
        url += f"year/{year}/"
    
    try:
        resp = requests.get(url, timeout=12)
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}"
        
        data = resp.json()
        
        # GCD often returns list or direct dict — normalize
        if isinstance(data, list) and data:
            issue_data = data[0]
        elif isinstance(data, dict) and "id" in data:
            issue_data = data
        else:
            return None, "Unexpected format"
        
        issue_id = str(issue_data.get("id", ""))
        
        description = (
            issue_data.get("overview") or
            issue_data.get("notes") or
            issue_data.get("description") or
            ""
        )
        
        creators = "; ".join([
            f"{c.get('name', '')} ({c.get('role', '')})"
            for c in issue_data.get("credits", []) if c.get("name")
        ]) or "; ".join(issue_data.get("creator_names", []))
        
        return {
            "Series": issue_data.get("series", {}).get("name", series),
            "Issue #": issue_data.get("number", issue),
            "Title / Story": issue_data.get("title", "") or issue_data.get("name", ""),
            "Cover Date": issue_data.get("cover_date", "") or issue_data.get("key_date", ""),
            "Publisher": issue_data.get("series", {}).get("publisher", {}).get("name", ""),
            "Creators": creators,
            "Description": description[:800] + ("..." if len(description) > 800 else ""),
            "Page Count": issue_data.get("page_count", ""),
            "Image URL": get_cover_url(issue_data, issue_id),
        }, None
    except Exception as e:
        return None, str(e)

if st.button("Fetch Comic Details", type="primary"):
    if not comic_text.strip():
        st.warning("Enter at least one comic identifier.")
    else:
        with st.spinner("Querying Grand Comics Database..."):
            lines = [line.strip() for line in comic_text.splitlines() if line.strip()]
            results = []
            missing = []

            for line in lines:
                series, issue_num, year = parse_comic_input(line)
                if not series or not issue_num:
                    missing.append(f"{line} (parse error)")
                    continue
                
                data, error = fetch_gcd_comic(series, issue_num, year)
                if data:
                    msrp = 0.0  # GCD rarely has prices; could add manual override later
                    
                    # Comic pricing logic (adjust to your store rules)
                    if "New" in condition or "Near Mint" in condition or "Graded" in condition:
                        suggested = msrp if msrp > 0 else ""
                    elif "Very Fine" in condition or "Fine" in condition or "Key" in condition:
                        suggested = msrp * 0.8 if msrp > 0 else ""
                    elif "Bulk" in condition or "Rescue" in condition:
                        suggested = 1.00
                    elif "Vintage" in condition:
                        suggested = ""  # Vintage often needs manual valuation
                    else:
                        suggested = msrp * 0.4 if msrp > 0 else ""
                    
                    row = {
                        **data,
                        "Condition": condition,
                        "Suggested Selling Price": f"${suggested:.2f}" if suggested else "Manual",
                    }
                    results.append(row)
                else:
                    missing.append(f"{line} ({error or 'not found'})")

            if results:
                df = pd.DataFrame(results)
                st.success(f"Retrieved {len(results)} comics")
                st.dataframe(df, use_container_width=True, hide_index=True)

                now = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
                vendor_part = vendor_id.strip() if vendor_id.strip() else "gcd_batch"
                filename = f"{vendor_part}_{now}.csv"
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "↓ Download CSV",
                    csv,
                    file_name=filename,
                    mime="text/csv"
                )

                has_images = df["Image URL"].str.strip().astype(bool).any()
                if has_images:
                    st.subheader("Covers (previews)")
                    cols = st.columns(5)
                    for idx, row in df.iterrows():
                        url = row["Image URL"]
                        title = f"{row['Series']} #{row['Issue #']}"[:35]
                        if url:
                            with cols[idx % 5]:
                                st.image(url, use_column_width=True, caption=title)
                        else:
                            with cols[idx % 5]:
                                st.caption(f"No cover\n{title}")
                else:
                    st.info("No covers found in this batch.")

            if missing:
                st.warning(f"Failed for {len(missing)} entries:\n" + "\n".join(missing))

if st.button("Clear Form"):
    st.rerun()
