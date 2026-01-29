import streamlit as st
import pandas as pd
from apify_client import ApifyClient
import time

# ------------------------------
# CONFIG
# ------------------------------

GOOGLE_SHEET_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRJvN35Doqax_qlu0A26R-czbP7oXh6yjaAFs8uvhknllW_A4rFa6t2rPrxEMs8Lp_KmIKnRAYqrwjA/pub?gid=0&single=true&output=csv"
APIFY_ACTOR_ID = "QGcJvQyG9NqMKTYPH"  # Full Booking Scraper Actor
APIFY_API_TOKEN = "<YOUR_API_TOKEN>"

# ------------------------------
# FUNCTIONS
# ------------------------------

@st.cache_data(show_spinner=True)
def load_sheet(csv_url):
    try:
        df = pd.read_csv(csv_url)
        return df
    except Exception as e:
        st.error(f"Error loading Google Sheet CSV: {e}")
        return pd.DataFrame()

def run_apify_scraper(hotel_url, adults=2, children=0, rooms=1):
    client = ApifyClient(APIFY_API_TOKEN)
    input_data = {
        "startUrls": [{"url": hotel_url}],
        "adults": adults,
        "children": children,
        "rooms": rooms,
        "currency": "EUR",
        "language": "en-gb",
    }
    try:
        run = client.actor(APIFY_ACTOR_ID).call(run_input=input_data)
        dataset_id = run["defaultDatasetId"]
        items = list(client.dataset(dataset_id).iterate_items())
        return items
    except Exception as e:
        st.warning(f"Error running Apify scraper for {hotel_url}: {e}")
        return []

def extract_price(item):
    """Full nested price extraction from Apify output"""
    try:
        if "b_avg_price_per_night_eur" in item and item["b_avg_price_per_night_eur"]:
            return float(item["b_avg_price_per_night_eur"])
        elif "b_price" in item and item["b_price"]:
            return float(str(item["b_price"]).replace("€","").replace(",","").strip())
        elif "roomOptions" in item and item["roomOptions"]:
            for option in item["roomOptions"]:
                if "b_avg_price_per_night_eur" in option:
                    return float(option["b_avg_price_per_night_eur"])
                if "b_price" in option and option["b_price"]:
                    return float(str(option["b_price"]).replace("€","").replace(",","").strip())
        return None
    except Exception:
        return None

# ------------------------------
# STREAMLIT APP
# ------------------------------

st.set_page_config(page_title="Booking Price Monitor", layout="wide")
st.title("📊 Booking.com Price Monitor")

# Load hotel list
df_hotels = load_sheet(GOOGLE_SHEET_CSV)
if df_hotels.empty:
    st.stop()

# Sidebar options
st.sidebar.header("Scraper Options")
adults = st.sidebar.number_input("Adults", min_value=1, max_value=10, value=2)
children = st.sidebar.number_input("Children", min_value=0, max_value=5, value=0)
rooms = st.sidebar.number_input("Rooms", min_value=1, max_value=5, value=1)

if st.sidebar.button("Fetch Prices"):
    results = []
    progress_bar = st.progress(0)
    total = len(df_hotels)

    for idx, row in df_hotels.iterrows():
        hotel_name = row.get("Property Name") or row.get("hotel_name") or "Unknown"
        hotel_url = row.get("Booking URL") or row.get("url") or ""
        if not hotel_url:
            st.warning(f"No URL found for {hotel_name}")
            continue

        st.info(f"Fetching prices for {hotel_name}...")
        items = run_apify_scraper(hotel_url, adults, children, rooms)

        price = None
        if items:
            for item in items:
                price = extract_price(item)
                if price:
                    break

        results.append({
            "Hotel": hotel_name,
            "Price per Night (€)": price if price else "N/A",
        })

        progress_bar.progress((idx + 1) / total)
        time.sleep(0.5)  # avoid hitting rate limits

    st.subheader("Scraping Results")
    st.dataframe(pd.DataFrame(results))

























