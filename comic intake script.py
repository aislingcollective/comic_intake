import streamlit as st
import requests
import csv
from datetime import datetime
import io

# UPCitemdb free tier endpoint (100 calls/day, no key needed)
UPCITEMDB_BASE_URL = "https://api.upcitemdb.com/prod/trial"

def parse_supplement(full_barcode):
    """Parse 5-digit supplement: issue (3 digits), variant (1), printing (1)"""
    if len(full_barcode) == 17 and full_barcode.isdigit():
        supplement = full_barcode[-5:]
        issue_number = supplement[:3]
        variant = supplement[3]
        printing = supplement[4]
        return issue_number, variant, printing
    return "N/A", "N/A", "N/A"

def lookup_comic(barcode):
    """Lookup barcode via UPCitemdb using only the base 12-digit UPC"""
    try:
        upc_12 = barcode[:12]  # Critical: use only first 12 digits
        response = requests.get(f"{UPCITEMDB_BASE_URL}/lookup?upc={upc_12}", timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get('code') == 'OK' and data.get('items'):
            item = data['items'][0]
            return {
                'title': item.get('title', "N/A"),
                'description': item.get('description', "No description available."),
                'publisher': item.get('brand', "N/A"),  # Often publisher for comics
                'image_url': item.get('images', [None])[0] or "N/A",
                'category': item.get('category', "N/A")
            }
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400:
            st.warning(f"Invalid UPC format or not found in UPCitemdb for base UPC {upc_12}.")
        else:
            st.warning(f"UPC lookup error for {barcode}: {str(e)}")
    except Exception as e:
        st.warning(f"UPC lookup error for {barcode}: {str(e)}")
    return None

def get_current_value(title, issue_number):
    """Manual current value input with helpful sold/comics site links"""
    search_title = title.replace(" ", "+") + "+" + issue_number if issue_number != "N/A" else title.replace(" ", "+")
    
    st.markdown(f"""
    **Quick check for current value of '{title} #{issue_number}' (open in new tab):**
    - [eBay Sold Listings](https://www.ebay.com/sch/i.html?_nkw={search_title}&_sacat=0&LH_Sold=1&LH_Complete=1&rt=nc&LH_ItemCondition=3000) — filter 'Sold Items' for recent prices
    - [GoCollect Comics](https://gocollect.com/comics/search?q={search_title})
    - [ComicBookRealm Price Guide](https://comicbookrealm.com/search?terms={search_title})
    - [ComicsPriceGuide](https://www.comicspriceguide.com/search?query={search_title})
    - [Key Collector Comics](https://keycollectorcomics.com/search?query={search_title})
    """)

    value_input = st.text_input(
        f"Enter current market value for '{title} #{issue_number}' (e.g. 12.50 or N/A):",
        value="N/A",
        key=f"value_{title}_{issue_number}_{datetime.now().timestamp()}"  # unique per run
    )
    
    try:
        return float(value_input) if value_input.strip().lower() != "n/a" else "N/A"
    except ValueError:
        return "N/A"

def main():
    st.title("Comic Barcode Intake App")
    st.markdown("""
    Enter 17-digit comic barcodes below.  
    • Uses UPCitemdb (free tier) to look up the base 12-digit UPC  
    • Parses the 5-digit supplement for issue/variant/printing  
    • Manual current value input (with eBay sold & price guide links)  
    • Downloads CSV ready for Magento import
    """)

    vendor_id = st.text_input("Vendor ID", value="", help="Your vendor identifier for Magento")
    condition = st.selectbox("Condition", ["New", "Near Mint", "Very Fine", "Fine", "Very Good", "Good", "Fair", "Poor", "Other"])
    msrp = st.number_input("Suggested Retail Price (MSRP)", min_value=0.00, value=3.99, step=0.01, format="%.2f")
    barcodes_text = st.text_area(
        "Barcodes (17 digits each, one per line or comma-separated)",
        height=150,
        help="Examples:\n72513025474003041\n76194134274005021,70985301979401111"
    )

    if st.button("Process Barcodes", type="primary"):
        if not vendor_id.strip():
            st.error("Vendor ID is required.")
            return
        if not barcodes_text.strip():
            st.error("Please enter at least one barcode.")
            return

        # Clean and collect valid 17-digit barcodes
        barcodes = []
        for part in barcodes_text.replace(",", " ").split():
            cleaned = part.strip()
            if cleaned.isdigit() and len(cleaned) == 17:
                barcodes.append(cleaned)

        if not barcodes:
            st.error("No valid 17-digit barcodes found.")
            return

        st.info(f"Processing {len(barcodes)} barcode(s)...")

        products = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, barcode in enumerate(barcodes):
            status_text.text(f"Processing {barcode} ({i+1}/{len(barcodes)})")

            issue_number, variant, printing = parse_supplement(barcode)
            comic_data = lookup_comic(barcode)

            if not comic_data:
                st.warning(f"No data found for barcode {barcode} (base UPC: {barcode[:12]})")
                manual_title = st.text_input(f"Enter title manually for {barcode} (or leave blank to skip):", key=f"manual_{i}")
                if not manual_title.strip():
                    continue
                comic_data = {
                    'title': manual_title,
                    'description': "N/A",
                    'publisher': "N/A",
                    'image_url': "N/A"
                }

            title = comic_data['title']
            description = comic_data['description']
            publisher = comic_data['publisher']
            image_url = comic_data['image_url']

            current_value = get_current_value(title, issue_number)

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
                "cover_date": "N/A",
                "creators": "N/A",
                "issue_number": issue_number,
                "variant": variant,
                "printing": printing
            }
            products.append(product)

            progress_bar.progress((i + 1) / len(barcodes))

        status_text.text(f"Processing complete! {len(products)} comics ready.")

        if products:
            output = io.StringIO()
            fieldnames = [
                "name", "sku", "description", "image_additional", "price", "current_value",
                "condition", "vendor_id", "publisher", "cover_date", "creators",
                "issue_number", "variant", "printing"
            ]

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
                help="Upload in Magento: System → Data Transfer → Import"
            )
            st.success(f"CSV generated with {len(products)} items!")

if __name__ == "__main__":
    main()
