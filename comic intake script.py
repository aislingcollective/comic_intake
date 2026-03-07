import streamlit as st
import requests
import csv
from datetime import datetime
import io

# Replace with your actual ComicVine API key
COMICVINE_API_KEY = "da58407c48328439ae1c16418b4358165a9c1f3f"  # ← Put your key here

# Optional: For better security later, move to Streamlit secrets:
# comicvine_api_key = st.secrets["comicvine_api_key"]

def parse_supplement(full_barcode):
    """Parse the 5-digit supplement: issue (3 digits), variant (1), printing (1)"""
    if len(full_barcode) == 17 and full_barcode.isdigit():
        supplement = full_barcode[-5:]
        issue_number = supplement[:3]
        variant = supplement[3]
        printing = supplement[4]
        return issue_number, variant, printing
    return "N/A", "N/A", "N/A"

def lookup_comic(barcode):
    """Search ComicVine by UPC/barcode and get issue details"""
    if not COMICVINE_API_KEY or COMICVINE_API_KEY == "YOUR_COMICVINE_API_KEY_HERE":
        st.error("Please set your ComicVine API key in the code.")
        return None

    search_url = f"https://comicvine.gamespot.com/api/search/?api_key={COMICVINE_API_KEY}&format=json&query={barcode}&resources=issue&limit=1"
    headers = {"User-Agent": "ComicIntakeApp/1.0"}
    
    try:
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('number_of_total_results', 0) > 0:
            issue_id = data['results'][0]['id']
            detail_url = f"https://comicvine.gamespot.com/api/issue/4000-{issue_id}/?api_key={COMICVINE_API_KEY}&format=json"
            detail_response = requests.get(detail_url, headers=headers, timeout=10)
            detail_response.raise_for_status()
            return detail_response.json()['results']
    except Exception as e:
        st.warning(f"Error looking up barcode {barcode}: {str(e)}")
    return None

def get_current_value(title):
    """Manual input with helpful site suggestions (no eBay yet)"""
    st.markdown("""
    **Quick value check sites (open in a new tab):**
    - [GoCollect](https://gocollect.com/comics) — search title + issue
    - [ComicBookRealm](https://comicbookrealm.com/) — free price guide
    - [ComicsPriceGuide](https://www.comicspriceguide.com/) — free signup for values
    - [Key Collector Comics](https://www.keycollectorcomics.com/) — good for variants/keys
    """)
    
    value_str = st.text_input(
        f"Current market value for '{title}' (e.g., 12.50 or N/A)",
        value="N/A",
        key=f"value_{title}_{datetime.now().timestamp()}"  # unique key to avoid collisions
    )
    try:
        return float(value_str) if value_str.lower() != "n/a" else "N/A"
    except ValueError:
        return "N/A"

def main():
    st.title("Comic Barcode Intake App")
    st.markdown("""
    Enter comic details below. Barcodes should be **17 digits** (12-digit UPC + 5-digit supplement).  
    The app fetches data from ComicVine and generates a CSV for Magento import.
    """)

    # User inputs
    vendor_id = st.text_input("Vendor ID", value="", help="Your vendor identifier for Magento")
    condition = st.selectbox("Condition", ["New", "Near Mint", "Very Fine", "Fine", "Very Good", "Good", "Fair", "Poor", "Other"])
    msrp = st.number_input("Suggested Retail Price (MSRP)", min_value=0.00, value=3.99, step=0.01, format="%.2f")
    barcodes_text = st.text_area(
        "Barcodes (one per line or comma-separated, 17 digits each)",
        height=150,
        help="Example:\n75960620200300111\nor\n75960620200300111,75960620200400121"
    )

    if st.button("Process Barcodes", type="primary"):
        if not vendor_id.strip():
            st.error("Vendor ID is required.")
            return
        if not barcodes_text.strip():
            st.error("Please enter at least one barcode.")
            return

        # Clean and split barcodes
        barcodes = []
        for line in barcodes_text.splitlines():
            cleaned = line.strip().replace(" ", "").replace(",", "")
            if cleaned:
                barcodes.extend([b for b in cleaned.split(",") if b.isdigit() and len(b) == 17])

        if not barcodes:
            st.error("No valid 17-digit barcodes found.")
            return

        st.info(f"Processing {len(barcodes)} barcode(s)...")

        products = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, barcode in enumerate(barcodes):
            status_text.text(f"Looking up {barcode} ({i+1}/{len(barcodes)})")
            
            issue_number, variant, printing = parse_supplement(barcode)
            comic_data = lookup_comic(barcode)

            if not comic_data:
                st.warning(f"No ComicVine data for {barcode}. Skipping.")
                continue

            title = comic_data.get('name', "Unknown Title")
            description = comic_data.get('description', "No description available.")
            publisher = comic_data.get('volume', {}).get('publisher', {}).get('name', "N/A")
            cover_date = comic_data.get('cover_date', "N/A")
            creators = ", ".join([c['name'] for c in comic_data.get('person_credits', []) if c.get('name')])
            image_url = comic_data.get('image', {}).get('super_url', "N/A") or comic_data.get('image', {}).get('original_url', "N/A")

            current_value = get_current_value(title)

            product = {
                "name": f"{title} #{issue_number}" if issue_number != "N/A" else title,
                "sku": barcode,
                "description": description,
                "image_additional": image_url,
                "price": msrp,
                "current_value": current_value,
                "condition": condition,
                "vendor_id": vendor_id,
                "publisher": publisher,
                "cover_date": cover_date,
                "creators": creators,
                "issue_number": issue_number,
                "variant": variant,
                "printing": printing
            }
            products.append(product)

            progress_bar.progress((i + 1) / len(barcodes))

        status_text.text(f"Done! Processed {len(products)} comics successfully.")

        if products:
            # Create CSV in memory
            output = io.StringIO()
            fieldnames = ["name", "sku", "description", "image_additional", "price", "current_value", 
                          "condition", "vendor_id", "publisher", "cover_date", "creators", 
                          "issue_number", "variant", "printing"]
            
            writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(products)
            
            csv_data = output.getvalue().encode('utf-8')
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"comics_import_{vendor_id}_{timestamp}.csv"

            st.download_button(
                label="📥 Download CSV for Magento",
                data=csv_data,
                file_name=filename,
                mime="text/csv",
                help="Upload this file in Magento under System > Data Transfer > Import"
            )
            st.success(f"CSV generated with {len(products)} items!")

if __name__ == "__main__":
    main()
