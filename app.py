import streamlit as st
import pandas as pd
from apify_client import ApifyClient
import time

# ------------------------------
# CONFIGURATION
# ------------------------------

APIFY_TOKEN = "<YOUR_API_TOKEN>"  # <-- Replace with your Apify token
APIFY_ACTOR_ID = "QGcJvQyG9NqMKTYPH"  # Full Booking Scraper
GOOGLE_SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRJvN35Doqax_qlu0A26R-czbP7oXh6yjaAFs8uvhknllW_A4rFa6t2rPrxEMs8Lp_KmIKnRAYqrwjA/pub?gid=0&single=true&output=csv"

# ------------------------------
# STREAMLIT APP
# ------------------------------

st.set_page_config(page_title="Booking.com Price Monitor", layout="wide")
st.title("📊 Booking.com Group Price Monitor")

# ------------------------------
# LOAD HOTEL LIST
# ------------------------------

@st.cache_data(show_spinner=True)
def load_sheet(url):
    try:
        df = pd.read_csv(url)
        return df
    except Exception as e:
        st.error(f"Error loading Google Sheet CSV: {e}")
        return pd.DataFrame()

df = load_sheet(GOOGLE_SHEET_URL)

if df.empty:
    st.stop()

# Show initial hotel list
st.subheader("Hotel List")
st.dataframe(df)

# ------------------------------
# INIT APIFY CLIENT
# ------------------------------

client = ApifyClient(APIFY_TOKEN)

# ------------------------------
# FETCH PRICES BUTTON
# ------------------------------

if st.button("Fetch Prices from Booking.com"):

    st.info("Running Apify actor... this may take a few minutes ⏳")

    results = []
    progress_bar = st.progress(0)
    total = len(df)

    for idx, row in df.iterrows():
        hotel_name = row.get("hotel_name") or "Unknown"
        hotel_url = row.get("hotel_url") or ""
        if not hotel_url:
            st.warning(f"No URL for {hotel_name}, skipping")
            results.append({"hotel_name": hotel_name, "price_per_night": "N/A"})
            continue

        adults = row.get("adults", 2)
        children = row.get("children", 0)
        rooms = row.get("rooms", 1)

        actor_input = {
            "startUrls": [{"url": hotel_url}],
            "maxItems": 1,
            "adults": adults,
            "children": children,
            "rooms": rooms,
            "currency": "EUR",
            "language": "en-gb"
        }

        try:
            # Run Apify actor
            run = client.actor(APIFY_ACTOR_ID).call(run_input=actor_input)
            dataset_id = run["defaultDatasetId"]

            # Give dataset a moment to populate
            time.sleep(2)

            # Fetch items
            items = list(client.dataset(dataset_id).iterate_items())
            if not items:
                results.append({"hotel_name": hotel_name, "price_per_night": "N/A"})
                st.warning(f"No data for {hotel_name}")
                continue

            # ------------------------------
            # SAFE NESTED PRICE EXTRACTION
            # ------------------------------
            first_item = items[0]
            price_per_night = None
            room_options = first_item.get("roomOptions", [])

            for room in room_options:
                stays = room.get("b_stay_prices", [])
                for stay in stays:
                    p = stay.get("b_price_per_night") or stay.get("b_price") or stay.get("b_raw_price")
                    if p:
                        if isinstance(p, str):
                            p = p.replace("€", "").replace("\xa0","").replace(",", "").strip()
                        try:
                            price_per_night = round(float(p), 2)
                            break
                        except:
                            continue
                if price_per_night:
                    break

            if not price_per_night:
                price_per_night = "N/A"

            results.append({"hotel_name": hotel_name, "price_per_night": price_per_night})

        except Exception as e:
            results.append({"hotel_name": hotel_name, "price_per_night": "Error"})
            st.error(f"Error fetching {hotel_name}: {e}")

        progress_bar.progress((idx + 1) / total)
        time.sleep(0.5)  # avoid rate limits

    # ------------------------------
    # DISPLAY RESULTS
    # ------------------------------

    st.subheader("Prices per Night")
    results_df = pd.DataFrame(results)
    st.dataframe(results_df)


























