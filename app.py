import streamlit as st
import pandas as pd
from apify_client import ApifyClient
from datetime import date

# -----------------------------
# SECRETS
# -----------------------------
APIFY_TOKEN = st.secrets["general"]["APIFY_TOKEN"]
GOOGLE_SHEET_ID = st.secrets["general"]["GOOGLE_SHEET_ID"]

# -----------------------------
# CONFIG
# -----------------------------
SHEET_NAME = "competitors"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/gviz/tq?tqx=out:csv&sheet={SHEET_NAME}"
APIFY_ACTOR = "voyager/fast-booking-scraper"

# Group mapping 1-7
GROUP_MAPPING = {
    1: "Hotel Convent",
    2: "Villas",
    3: "Villas with Balcony",
    4: "Olive Suites",
    5: "MH Premium",
    6: "MH Standard",
    7: "Apartments Adria"
}

# -----------------------------
# STREAMLIT UI
# -----------------------------
st.set_page_config(page_title="Booking.com Price Monitor", layout="wide")
st.title("📊 Booking.com Group Price Monitor")

# -----------------------------
# LOAD GOOGLE SHEET
# -----------------------------
df = pd.read_csv(SHEET_URL)

# Normalize column names
df.columns = df.columns.str.lower().str.strip()
required_columns = ["group","unit_name","nr_persons","role","property_name","booking_url","property_category"]
for col in required_columns:
    if col not in df.columns:
        st.error(f"Column missing in Google Sheet: {col}")
        st.stop()

# Strip strings and clean
df["booking_url"] = df["booking_url"].astype(str).str.strip()
df["property_category"] = df["property_category"].astype(str).str.lower().str.strip()
df["nr_persons"] = pd.to_numeric(df["nr_persons"], errors="coerce")
df = df.dropna(subset=["group", "booking_url", "property_category", "nr_persons"])
df = df[df["booking_url"].str.startswith("http")]

# -----------------------------
# STREAMLIT SELECT GROUP
# -----------------------------
available_groups = [num for num in GROUP_MAPPING if num in df["group"].unique()]
group_selected_number = st.selectbox(
    "Select group",
    available_groups,
    format_func=lambda x: GROUP_MAPPING[x]
)

group_df = df[df["group"] == group_selected_number]

# Date picker
col1, col2 = st.columns(2)
with col1:
    check_in = st.date_input("Check-in", date.today())
with col2:
    check_out = st.date_input("Check-out", date.today())

if check_out <= check_in:
    st.error("Check-out must be after check-in")
    st.stop()

nights = (check_out - check_in).days
client = ApifyClient(APIFY_TOKEN)

# -----------------------------
# FETCH PRICES
# -----------------------------
if st.button("🔍 Fetch prices"):
    results = []

    with st.spinner("Fetching prices from Booking.com (this may take a few minutes)…"):
        for _, row in group_df.iterrows():
            # Determine adults/children based on category
            if row["property_category"] in ["apartment","mobile"]:
                adults = 1
                children = 0
            else:  # hotel
                adults = int(row["nr_persons"])
                children = 0

            # Prepare correct actor input
            run_input = {
                "hotelUrls": [row["booking_url"]],
                "checkIn": check_in.isoformat(),
                "checkOut": check_out.isoformat(),
                "adults": adults,
                "children": children,
                "rooms": 1,
                "currency": "EUR",
                "language": "en-gb",
                "proxyConfiguration": {"useApifyProxy": True},
                "headless": True
            }

            try:
                run = client.actor(APIFY_ACTOR).call(run_input=run_input)
                dataset = client.dataset(run["defaultDatasetId"])
                items = list(dataset.iterate_items())

                # Extract price per night from rooms[0].price.amount
                if items and "rooms" in items[0] and items[0]["rooms"]:
                    total_price = items[0]["rooms"][0]["price"]["amount"]
                    price_per_night = round(total_price / nights, 2)
                else:
                    price_per_night = None

            except Exception as e:
                price_per_night = None
                st.write(f"Error fetching {row['property_name']}: {e}")

            results.append({
                "Property": row["property_name"],
                "Role": row["role"],
                "Category": row["property_category"],
                "Nr persons": adults,
                "Price / night (€)": price_per_night
            })

    st.success("Finished")
    st.dataframe(pd.DataFrame(results), use_container_width=True)












