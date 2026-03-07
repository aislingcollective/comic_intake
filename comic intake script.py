import streamlit as st
import requests
import csv
from datetime import datetime
import io

# No API key needed for free tier (100 calls/day)
UPCITEMDB_BASE_URL = "https://api.upcitemdb.com/prod/trial"

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
    """Lookup by barcode using UPCitemdb (free tier)"""
    try:
        response = requests.get(f"{UPCITEMDB_BASE_URL}/lookup?upc={barcode}", timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('code') == 'OK' and data.get('items'):
            item = data['items'][0]
            return {
                'name': item.get('title', "N/A"),
                'description': item.get('description', "N/A"),
                'publisher': item.get('brand', "N/A"),  # Often publisher for comics
                'image_url': item.get('images', ["N/A"])[0],
                'ean': item.get('ean', "N/A"),
                'upc': item.get('upc', "N/A"),
                # Add more fields as needed
            }
    except Exception as e:
        st.warning(f"Error looking up barcode {barcode} with UPCitemdb: {str(e)}")
    return None

# Keep your get_current_value as-is (manual with sites)

def main():
    st.title("Comic Barcode Intake App (Updated with UPC Lookup)")
    st.markdown("""
    Enter comic details below. Barcodes should be **17 digits** (12-digit UPC + 5-digit supplement).  
    Now uses UPCitemdb for accurate barcode lookups (free for 100/day).
    """)

    # User inputs (same as before)
    vendor_id = st.text_input("Vendor ID", value="", help="Your vendor identifier for Magento")
    condition = st.selectbox("Condition", ["New", "Near Mint", "Very Fine", "Fine", "Very Good", "Good", "Fair", "Poor", "Other"])
    msrp = st.number_input("Suggested Retail Price (MSRP)", min_value=0.00, value=3.99, step=0.01, format="%.2f")
    barcodes_text = st.text_area(
        "Barcodes (one per line or comma-separated, 17 digits each)",
        height=150,
        help="Example:\n72513025474003041\nor\n72513025474003041,76194134274005021"
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
                st.warning(f"No data for {barcode}. Enter manually?")
                manual_title = st.text_input(f"Title for {barcode}:", key=f"manual_title_{i}")
                if manual_title:
                    comic_data = {'name': manual_title, 'description': "N/A", 'publisher': "N/A", 'image_url': "N/A"}
                else:
                    continue

            title = comic_data.get('name', "N/A")
            description = comic_data.get('description', "N/A")
            publisher = comic_data.get('publisher', "N/A")
            image_url = comic_data.get('image_url', "N/A")
            cover_date = "N/A"  # UPCitemdb may not have this; add manual if needed
            creators = "N/A"    # Same

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
            # Create CSV in memory (same as before)
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
