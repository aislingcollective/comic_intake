# Add to secrets: GCD_API_BASE = "https://www.comics.org/api/"
# No key needed for anonymous (but limited)

def fetch_from_gcd(identifier: str):
    # Simple parse: assume "Series Issue [Year]" format
    parts = identifier.split()
    if len(parts) < 2:
        return None
    series_name = " ".join(parts[:-1]) if len(parts) > 2 else parts[0]
    issue_num = parts[-1]
    year = parts[-2] if len(parts) > 2 and parts[-2].isdigit() and len(parts[-2]) == 4 else None

    url = f"{GCD_API_BASE}series/name/{series_name.replace(' ', '%20')}/issue/{issue_num}/"
    if year:
        url += f"year/{year}/"

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()  # Assuming it returns issue details
        # Adapt based on actual response structure (test!)
        if 'results' in data and data['results']:
            issue = data['results'][0]  # or appropriate key
            return {
                "Series": issue.get("series", {}).get("name", ""),
                "Issue #": issue.get("number", ""),
                "Title": issue.get("title", "") or issue.get("name", ""),
                "Cover Date": issue.get("cover_date", "") or issue.get("key_date", ""),
                "Publisher": issue.get("series", {}).get("publisher", {}).get("name", ""),
                "Creators": "; ".join([c.get("name", "") for c in issue.get("credits", [])]),
                "Description": issue.get("overview", "") or "",
                "Image URL": issue.get("cover", {}).get("url", "") or f"https://www.comics.org/issue/{issue.get('id')}/cover/",  # adjust
                # Add more: characters, etc. if available
            }
    except Exception as e:
        st.error(f"GCD fetch error for {identifier}: {e}")
    return None

# In loop:
for line in comic_inputs:
    data = fetch_from_gcd(line.strip())
    if data:
        row = {**data, "Condition": condition, ...}  # add pricing logic as before
        results.append(row)
