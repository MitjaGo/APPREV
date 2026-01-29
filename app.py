import streamlit as st
import pandas as pd
from apify_client import ApifyClient
from datetime import date

# ----------------------------
# SECRETS
# ----------------------------
APIFY_TOKEN = st.secrets["general"]["APIFY_TOKEN"]
GOOGLE_SHEET_ID = st.secrets["general"]["GOOGLE_SHEET_ID"]

# ----------------------------
# CONFIG
# ----------------------------
SHEET_NAME = "competitors"
SHEET_CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/"
    f"{GOOGLE_SHEET_ID}/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"
)

APIFY_ACTOR = "apify/booking-scraper"

ROOM_MAPPING = {
    "double": {"adults": 2, "children": 0},
    "triple": {"adults": 3, "children": 0},
    "family": {"adults": 2, "children": 2},
}

# ----------------------------
# STREAMLIT UI
# ----------------------------
st.set_page_config(page_title="Booking.com Price Monitor", layout="wide")
st.title("🏨 Booking.com Competitor Price Monitor")

df = pd.read_csv(SHEET_CSV_URL)

unit = st.selectbox("Select unit", sorted(df["unit_name"].unique()))
room_type = st.selectbox("Select room type", sorted(df["room_type"].unique()))

col1, col2 = st.columns(2)
with col1:
    check_in = st.date_input("Check-in", date.today())
with col2:
    check_out = st.date_input("Check-out", date.today())

if check_out <= check_in:
    st.error("Check-out must be after check-in")
    st.stop()

nights = (check_out - check_in).days

filtered = df[
    (df["unit_name"] == unit) &
    (df["room_type"] == room_type)
]

if filtered.empty:
    st.warning("No data found for this unit and room type")
    st.stop()

client = ApifyClient(APIFY_TOKEN)

# ----------------------------
# FETCH PRICES
# ----------------------------
results = []

if st.button("Fetch prices"):
    with st.spinner("Fetching prices from Booking.com..."):
        for _, row in filtered.iterrows():
            category = row["property_category"].lower()

            # Decide adults / children
            if category in ["apartment", "mobile"]:
                adults = 1
                children = 0
            else:
                adults = ROOM_MAPPING[room_type]["adults"]
                children = ROOM_MAPPING[room_type]["children"]

            run_input = {
                "startUrls": [{"url": row["booking_url"]}],
                "checkIn": check_in.isoformat(),
                "checkOut": check_out.isoformat(),
                "adults": adults,
                "children": children,
                "currency": "EUR",
                "maxListings": 1
            }

            run = client.actor(APIFY_ACTOR).call(run_input=run_input)
            dataset = client.dataset(run["defaultDatasetId"])
            items = list(dataset.iterate_items())

            if items:
                total_price = items[0]["price"]["total"]
                price_per_night = round(total_price / nights, 2)
            else:
                price_per_night = None

            results.append({
                "Property": row["property_name"],
                "Role": row["role"],
                "Category": category,
                "Price per night (€)": price_per_night
            })

    st.success("Done!")

    st.dataframe(pd.DataFrame(results), use_container_width=True)


