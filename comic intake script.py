import streamlit as st
import requests
import pandas as pd
import csv
from datetime import datetime
import io

# UPCitemdb free tier endpoint (100 calls/day, no key needed)
UPCITEMDB_BASE_URL = "https://api.upcitemdb.com/prod/trial"

def parse_supplement(full_barcode):
    if len(full_barcode) == 17 and full_barcode.isdigit():
        supplement = full_barcode[-5:]
        return supplement[:3], supplement[3], supplement[4]
    return "N/A", "N/A", "N/A"

def lookup_comic(barcode):
    try:
        upc_12 = barcode[:12]
        response = requests.get(f"{UPCITEMDB_BASE_URL}/lookup?upc={upc_12}", timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get('code') == 'OK' and data.get('items'):
            item = data['items'][0]
            return {
                'title': item.get('title', "Unknown"),
                'description': item.get('description', "N/A"),
                'publisher': item.get('brand', "N/A"),
                'image_url': item.get('images', [None])[0] or "N/A"
            }
    except Exception as e:
        st.warning(f"Lookup failed for {barcode}: {str(e)}")
    return None

def get_value_lookup_links(title, issue):
    search = f"{title.replace(' ', '+')}+{issue}" if issue != "N/A" else title.replace(' ', '+')
    return f"""
    [eBay Sold](https://www.ebay.com/sch/i.html?_nkw={search}&LH_Sold=1&LH_Complete=1) ·
    [GoCollect](https://gocollect.com/comics/search?q={search}) ·
    [ComicBookRealm](https://comicbookrealm.com/search?terms={search})
    """

# ────────────────────────────────────────────────
# Main App
# ────────────────────────────────────────────────
st.title("Comic Intake App – Batch Table Style")

vendor_id = st.text_input("Vendor ID", value=st.session_state.get("vendor_id", ""), key="vendor_id_input")
condition = st.selectbox("Default Condition", ["New", "Near Mint", "Very Fine", "Fine", "Very Good", "Good", "Fair", "Poor", "Other"])
msrp_default = st.number_input("Default MSRP", min_value=0.00, value=3.99, step=0.01, format="%.2f")

barcodes_text = st.text_area(
    "Paste barcodes here (one per line or comma-separated, 17 digits each)",
    height=120,
    help="Example: 72513025474003041\n76194134274005021"
)

if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame(columns=[
        "barcode", "title", "issue_number", "variant", "printing",
        "publisher", "image_url", "condition", "msrp", "current_value", "notes"
    ])

if st.button("Load / Refresh Barcodes"):
    if not barcodes_text.strip():
        st.error("Enter at least one barcode.")
    else:
        barcodes = []
        for part in barcodes_text.replace(",", "\n").splitlines():
            cleaned = part.strip()
            if cleaned.isdigit() and len(cleaned) == 17:
                barcodes.append(cleaned)
            elif cleaned:
                st.warning(f"Ignored invalid: {cleaned}")

        if barcodes:
            new_rows = []
            with st.spinner(f"Looking up {len(barcodes)} barcodes..."):
                for bc in barcodes:
                    issue, var, print_ = parse_supplement(bc)
                    data = lookup_comic(bc)
                    title = data['title'] if data else "Manual entry needed"
                    pub = data['publisher'] if data else "N/A"
                    img = data['image_url'] if data else "N/A"

                    new_rows.append({
                        "barcode": bc,
                        "title": title,
                        "issue_number": issue,
                        "variant": var,
                        "printing": print_,
                        "publisher": pub,
                        "image_url": img,
                        "condition": condition,
                        "msrp": msrp_default,
                        "current_value": "N/A",
                        "notes": get_value_lookup_links(title, issue) if title != "Manual entry needed" else "Check manually"
                    })

            if new_rows:
                new_df = pd.DataFrame(new_rows)
                # Append only new barcodes (avoid duplicates)
                existing_barcodes = st.session_state.df["barcode"].tolist()
                new_df = new_df[~new_df["barcode"].isin(existing_barcodes)]
                st.session_state.df = pd.concat([st.session_state.df, new_df], ignore_index=True)
                st.success(f"Added {len(new_df)} new comics. Total: {len(st.session_state.df)}")

st.subheader("Edit Comics Table (fill current_value, fix any missing data)")

# Editable table – current_value is number, others text/select as needed
edited_df = st.data_editor(
    st.session_state.df,
    column_config={
        "current_value": st.column_config.NumberColumn(
            "Current Value ($)", min_value=0.0, format="%.2f", required=True
        ),
        "condition": st.column_config.SelectboxColumn(
            "Condition", options=["New", "Near Mint", "Very Fine", "Fine", "Very Good", "Good", "Fair", "Poor", "Other"]
        ),
        "msrp": st.column_config.NumberColumn("MSRP ($)", min_value=0.0, format="%.2f"),
        "notes": st.column_config.TextColumn("Value Check Links / Notes", width="medium")
    },
    num_rows="dynamic",
    use_container_width=True,
    hide_index=False,
    key="comic_editor"
)

# Update session state with edits
if edited_df is not None:
    st.session_state.df = edited_df

if st.button("Generate Magento CSV"):
    if st.session_state.df.empty:
        st.error("No comics in table.")
    else:
        df_export = st.session_state.df.copy()
        # Clean up for CSV
        df_export = df_export.rename(columns={
            "barcode": "sku",
            "title": "name",
            "image_url": "image_additional",
            "msrp": "price"
        })
        df_export["name"] = df_export.apply(
            lambda row: f"{row['name']} #{row['issue_number']}" if row['issue_number'] != "N/A" else row['name'],
            axis=1
        )
        # Add any missing required columns
        for col in ["description", "cover_date", "creators"]:
            if col not in df_export:
                df_export[col] = "N/A"

        output = io.StringIO()
        fieldnames = ["name", "sku", "description", "image_additional", "price", "current_value",
                      "condition", "vendor_id", "publisher", "cover_date", "creators",
                      "issue_number", "variant", "printing"]
        # Fill vendor_id
        df_export["vendor_id"] = vendor_id

        writer = csv.DictWriter(output, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for _, row in df_export.iterrows():
            writer.writerow(row.to_dict())

        csv_data = output.getvalue().encode('utf-8')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"comics_import_{vendor_id or 'batch'}_{timestamp}.csv"

        st.download_button(
            label="📥 Download CSV",
            data=csv_data,
            file_name=filename,
            mime="text/csv"
        )
        st.success("CSV ready!")

st.caption("Tip: Edit directly in the table. Use the links in 'notes' to check values quickly.")
