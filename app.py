import streamlit as st
import pandas as pd
from apify_client import ApifyClient
from datetime import date

# ----------------------------------
# SECRETS
# ----------------------------------
APIFY_TOKEN = st.secrets["general"]["APIFY_TOKEN"]
GOOGLE_SHEET_ID = st.secrets["general"]["GOOGLE_SHEET_ID"]

# ----------------------------------
# CONFIG
# ----------------------------------
SHEET_NAME = "competitors"
SHEET_URL = (
    f"https://docs.google.com/spreadsheets/d/"
    f"{GOOGLE_SHEET_ID}/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"
)

APIFY_ACTOR = "apify/booking-scraper"

ROOM_MAPPING = {
    "double": {"adults": 2, "children": 0},
    "triple": {"adults": 3, "children": 0},
    "family": {"adults": 2, "children": 2},
    "unit": {"adults": 1, "children": 0},
    "mobile": {"adults": 1, "children": 0},
}

# ----------------------------------
# UI
# ----------------------------------
st.set_page_config(layout="wide")
st.title("📊 Booking.com Group Price Monitor")

df = pd.read_csv(SHEET_URL)

# Normalize & clean
df.columns = df.columns.str.lower().str.strip()
df["room_type"] = df["room_type"].str.lower().str.strip()
df["property_category"] = df["property_category"].str.lower().str.strip()
df["booking_url"] = df["booking_url"].astype(str).str.strip()

df = df.dropna(subset=["group", "booking_url", "property_category"])

groups = sorted(df["group"].unique())

group_selected = st.selectbox("Select group", groups)

col1, col2 = st.columns(2)
with col1:
    check_in = st.date_input("Check-in", date.today())
with col2:
    check_out = st.date_input("Check-out", date.today())

if check_out <= check_in:
    st.error("Check-out must be after check-in")
    st.stop()

nights = (check_out - check_in).days

group_df = df[df["group"] == group_selected]

client = ApifyClient(APIFY_TOKEN)

# ----------------------------------
# FETCH PRICES
# ----------------------------------
if st.button("🔍 Fetch prices"):
    results = []

    with st.spinner("Fetching prices from Booking.com..."):
        for _, row in group_df.iterrows():

            booking_url = row["booking_url"]
            if not booking_url.startswith("http"):
                continue

            room_type = row["room_type"]
            category = row["property_category"]

            if category in ["apartment", "mobile"]:
                adults = 1
                children = 0
            else:
                adults = ROOM_MAPPING.get(room_type, {"adults": 2})["adults"]
                children = ROOM_MAPPING.get(room_type, {"children": 0})["children"]

            run_input = {
                "startUrls": [{"url": booking_url}],
                "checkIn": check_in.isoformat(),
                "checkOut": check_out.isoformat(),
                "adults": int(adults),
                "children": int(children),
                "currency": "EUR",
                "maxListings": 1
            }

            try:
                run = client.actor(APIFY_ACTOR).call(run_input=run_input)
                dataset = client.dataset(run["defaultDatasetId"])
                items = list(dataset.iterate_items())

                if items:
                    total_price = items[0]["price"]["total"]
                    price_per_night = round(total_price / nights, 2)
                else:
                    price_per_night = None

            except Exception:
                price_per_night = None

            results.append({
                "Property": row["property_name"],
                "Role": row["role"],
                "Room type": room_type,
                "Category": category,
                "Price / night (€)": price_per_night
            })

    st.success("Done")
    st.dataframe(pd.DataFrame(results), use_container_width=True)



