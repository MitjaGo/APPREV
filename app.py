import streamlit as st
import pandas as pd
from apify_client import ApifyClient
import time

# ------------------------------
# CONFIGURATION
# ------------------------------

APIFY_TOKEN = "<YOUR_API_TOKEN>"
APIFY_ACTOR_ID = "QGcJvQyG9NqMKTYPH"  # Full Booking Scraper
GOOGLE_SHEET_URL = "<YOUR_GOOGLE_SHEET_CSV_EXPORT_URL>"  # CSV export URL

# ------------------------------
# STREAMLIT APP
# ------------------------------

st.set_page_config(page_title="Booking.com Price Monitor", layout="wide")
st.title("📊 Booking.com Group Price Monitor")

# Load Google Sheet
@st.cache_data
def load_sheet(url):
    df = pd.read_csv(url)
    return df

df = load_sheet(GOOGLE_SHEET_URL)

# Show initial data
st.subheader("Hotel List")
st.dataframe(df)

# Initialize Apify client
client = ApifyClient(APIFY_TOKEN)

# Button to run scraper
if st.button("Fetch Prices from Booking.com"):

    st.info("Running Apify actor... this may take a few minutes ⏳")
    
    # Iterate through each hotel
    results = []
    for idx, row in df.iterrows():
        hotel_name = row["hotel_name"]
        hotel_type = row.get("property_category", "hotel")  # hotel, apartment, mobilehome
        adults = row.get("adults", 2)
        children = row.get("children", 0)
        rooms = row.get("rooms", 1)

        # Prepare input for Apify actor
        actor_input = {
            "startUrls": [{"url": row.get("hotel_url")}],  # must be full URL of hotel
            "maxItems": 1,
            "adults": adults,
            "children": children,
            "rooms": rooms,
            "currency": "EUR",
            "language": "en-gb"
        }

        try:
            # Run actor
            run = client.actor(APIFY_ACTOR_ID).call(run_input=actor_input)
            dataset_id = run["defaultDatasetId"]
            
            # Wait a few seconds for dataset to populate
            time.sleep(2)
            
            # Fetch dataset items
            items = list(client.dataset(dataset_id).iterate_items())
            
            if not items:
                results.append({"hotel_name": hotel_name, "price_per_night": "N/A"})
                st.warning(f"No data found for {hotel_name}")
                continue

            # Safe nested price extraction
            first_item = items[0]
            price_per_night = None
            room_options = first_item.get("roomOptions", [])
            
            for room in room_options:
                stays = room.get("b_stay_prices", [])
                for stay in stays:
                    # Try multiple price fields
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

    # Display results
    st.subheader("Prices per Night")
    results_df = pd.DataFrame(results)
    st.dataframe(results_df)























