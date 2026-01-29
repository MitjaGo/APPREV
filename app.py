import streamlit as st
import pandas as pd
from datetime import date
from apify_client import ApifyClient
import asyncio

# -----------------------------
# CONFIG / SECRETS
# -----------------------------
APIFY_TOKEN = st.secrets["general"]["APIFY_TOKEN"]
GOOGLE_SHEET_ID = st.secrets["general"]["GOOGLE_SHEET_ID"]
SLACK_WEBHOOK_URL = st.secrets["general"]["SLACK_WEBHOOK_URL"]
APIFY_ACTOR = "apify/booking-scraper"

SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/gviz/tq?tqx=out:csv&sheet=competitors"

# -----------------------------
# ROOM TYPE → ADULTS / CHILDREN mapping
# -----------------------------
room_mapping = {
    "double": {"adults": 2, "children": 0},
    "triple": {"adults": 3, "children": 0},
    "family": {"adults": 2, "children": 2},
    "single": {"adults": 1, "children": 0},
}

# -----------------------------
# STREAMLIT UI
# -----------------------------
st.set_page_config(page_title="Booking.com Price Monitor", layout="wide")
st.title("🏨 Booking.com Price Monitor")

check_in = st.date_input("Check-in", date.today())
check_out = st.date_input("Check-out", date.today())

if check_out <= check_in:
    st.warning("Check-out must be after check-in")
    st.stop()

nights = (check_out - check_in).days

# -----------------------------
# LOAD GOOGLE SHEET
# -----------------------------
@st.cache_data(ttl=300)
def load_sheet():
    df = pd.read_csv(SHEET_CSV_URL)
    required_cols = ["unit_name","room_type","role","property_name","booking_url","property_category"]
    if not set(required_cols).issubset(df.columns):
        st.error(f"Google Sheet must have columns: {required_cols}")
        st.stop()
    return df

df = load_sheet()

# -----------------------------
# APIFY FETCH
# -----------------------------
async def fetch_price(client, row, check_in, check_out, nights):
    category = row["property_category"].lower()
    if category in ["apartment", "mobile"]:
        adults = 1  # dummy
        children = 0
    else:
        if row["room_type"] not in room_mapping:
            st.error(f"Unknown room type: {row['room_type']}")
            return None
        adults = room_mapping[row["room_type"]]["adults"]
        children = room_mapping[row["room_type"]]["children"]

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

    return {
        "property_name": row["property_name"],
        "role": row["role"],
        "price_per_night": price_per_night
    }

# -----------------------------
# SLACK ALERT
# -----------------------------
def send_slack_alert(message):
    import httpx
    try:
        httpx.post(SLACK_WEBHOOK_URL, json={"text": message})
    except Exception as e:
        st.warning(f"Failed to send Slack alert: {e}")

# -----------------------------
# RUN COMPARISON
# -----------------------------
if st.button("▶ Run comparison"):
    client = ApifyClient(APIFY_TOKEN)
    alerts = []

    for unit in df["unit_name"].unique():
        st.header(f"🏨 {unit}")
        rooms = df[df["unit_name"]==unit]["room_type"].unique()

        for room in rooms:
            st.subheader(f"Room type: {room}")
            block = df[(df["unit_name"]==unit) & (df["room_type"]==room)]

            # Run Apify for all properties concurrently
            tasks = [fetch_price(client, row, check_in, check_out, nights) for _, row in block.iterrows()]
            results = asyncio.run(asyncio.gather(*tasks))

            # Build DataFrame
            df_room = pd.DataFrame(results)
            if df_room.empty:
                st.warning("No prices found")
                continue

            # Highlight cheapest competitor
            own_price = df_room[df_room["role"]=="own"]["price_per_night"].iloc[0]
            df_room["diff_vs_own (€)"] = df_room["price_per_night"] - own_price
            df_room["diff_vs_own (%)"] = (df_room["diff_vs_own (€)"] / own_price * 100).round(1)

            cheapest = df_room[df_room["role"]=="competitor"]["price_per_night"].min()
            def highlight(row):
                if row["role"]=="competitor" and row["price_per_night"]==cheapest:
                    return ["background-color: #c6f6d5"]*len(row)
                return [""]*len(row)

            st.dataframe(df_room.style.apply(highlight, axis=1), use_container_width=True)

            # -----------------------------
            # Slack Alert Logic (if price changed)
            # -----------------------------
            cache_file = f"prices_cache_{unit}_{room}.csv"
            try:
                old = pd.read_csv(cache_file)
                merged = df_room.merge(old, on="property_name", suffixes=("","_old"))
                changed = merged[merged["price_per_night"] != merged["price_per_night_old"]]
                if not changed.empty:
                    for _, r in changed.iterrows():
                        alerts.append(f"{unit}/{room} - {r['property_name']} price changed {r['price_per_night_old']} -> {r['price_per_night']}")
            except FileNotFoundError:
                pass

            df_room.to_csv(cache_file, index=False)

    # Send Slack alert if there are any changes
    if alerts:
        body = "\n".join(alerts)
        send_slack_alert(f"🏨 Competitor Price Alert:\n{body}")
        st.success(f"{len(alerts)} competitor prices changed! Slack notification sent.")
    else:
        st.info("No competitor price changes detected.")

