import streamlit as st
import pandas as pd
import asyncio
import httpx
from datetime import date
import os

# ==========================
# CONFIG / SECRETS
# ==========================
APIFY_TOKEN = st.secrets["general"]["APIFY_TOKEN"]
SPREADSHEET_ID = st.secrets["general"]["GOOGLE_SHEET_ID"]
SLACK_WEBHOOK_URL = st.secrets["general"]["SLACK_WEBHOOK_URL"]

SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet=competitors"
APIFY_ACTOR = "apify/booking-scraper"

# ==========================
# STREAMLIT SETUP
# ==========================
st.set_page_config(page_title="Booking.com Price Monitor", layout="wide")
st.title("🏨 Booking.com Price Monitor")

# ==========================
# LOAD SHEET
# ==========================
@st.cache_data(ttl=300)
def load_sheet():
    df = pd.read_csv(SHEET_CSV_URL)
    required = {"unit_name","room_type","role","property_name","booking_url"}
    if not required.issubset(df.columns):
        st.error("Google Sheet columns are incorrect")
        st.stop()
    return df

# ==========================
# VALIDATE BLOCK
# ==========================
def validate_room_block(df, unit, room):
    block = df[(df["unit_name"]==unit) & (df["room_type"]==room)]
    own = block[block["role"]=="own"]
    competitors = block[block["role"]=="competitor"]

    if len(own)!=1:
        raise ValueError("Must have exactly 1 own property")
    if len(competitors)!=5:
        raise ValueError("Must have exactly 5 competitors")
    if block["booking_url"].isna().any():
        raise ValueError("Missing booking_url")

    return own.iloc[0], competitors

# ==========================
# APIFY CALL
# ==========================
async def run_apify(url, check_in, check_out):
    input_data = {
        "startUrls":[{"url":url}],
        "checkIn": check_in.isoformat(),
        "checkOut": check_out.isoformat(),
        "currency": "EUR",
        "maxListings":1
    }
    async with httpx.AsyncClient(timeout=120) as client:
        res = await client.post(
            f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/runs",
            params={"token":APIFY_TOKEN,"waitForFinish":120},
            json=input_data
        )
        res.raise_for_status()
        return res.json()

def extract_price_per_night(apify_result,nights):
    try:
        total = apify_result["data"]["items"][0]["price"]["total"]
        return round(total/nights,2)
    except Exception:
        return None

async def fetch_price(row, check_in, check_out, nights):
    result = await run_apify(row["booking_url"], check_in, check_out)
    price = extract_price_per_night(result,nights)
    return {
        "property_name": row["property_name"],
        "role": row["role"],
        "price_per_night": price
    }

# ==========================
# BUILD ROOM TABLE
# ==========================
async def build_room_table(df, unit, room, check_in, check_out):
    nights = (check_out - check_in).days
    own, competitors = validate_room_block(df, unit, room)
    rows = [own] + competitors.to_dict("records")
    tasks = [fetch_price(row, check_in, check_out, nights) for row in rows]
    results = await asyncio.gather(*tasks)
    df_result = pd.DataFrame(results)

    own_price = df_result[df_result["role"]=="own"]["price_per_night"].iloc[0]
    df_result["diff_vs_own (€)"] = df_result["price_per_night"]-own_price
    df_result["diff_vs_own (%)"] = (df_result["diff_vs_own (€)"]/own_price*100).round(1)

    return df_result

# ==========================
# SLACK ALERT
# ==========================
def send_slack_alert(message):
    import httpx
    payload = {"text": message}
    try:
        httpx.post(SLACK_WEBHOOK_URL, json=payload)
    except Exception as e:
        st.warning(f"Failed to send Slack alert: {e}")

# ==========================
# STREAMLIT UI
# ==========================
col1,col2 = st.columns(2)
with col1:
    check_in = st.date_input("Check-in", date.today())
with col2:
    check_out = st.date_input("Check-out", date.today())

if check_out <= check_in:
    st.warning("Check-out must be after check-in")
    st.stop()

if st.button("▶ Run comparison"):
    df = load_sheet()
    alerts = []

    for unit in df["unit_name"].unique():
        st.header(f"🏨 {unit}")
        rooms = df[df["unit_name"]==unit]["room_type"].unique()

        for room in rooms:
            st.subheader(f"Room type: {room}")
            try:
                df_room = asyncio.run(build_room_table(df, unit, room, check_in, check_out))
                cheapest = df_room[df_room["role"]=="competitor"]["price_per_night"].min()

                # highlight cheapest
                def highlight(row):
                    if row["role"]=="competitor" and row["price_per_night"]==cheapest:
                        return ["background-color: #c6f6d5"]*len(row)
                    return [""]*len(row)

                st.dataframe(df_room.style.apply(highlight, axis=1), use_container_width=True)

                # check for price changes using cached CSV
                cache_file = f"prices_cache_{unit}_{room}.csv"
                try:
                    old = pd.read_csv(cache_file)
                    merged = df_room.merge(old,on="property_name",suffixes=("","_old"))
                    changed = merged[merged["price_per_night"] != merged["price_per_night_old"]]
                    if not changed.empty:
                        for _, r in changed.iterrows():
                            alerts.append(f"{unit}/{room} - {r['property_name']} price changed {r['price_per_night_old']} -> {r['price_per_night']}")
                except FileNotFoundError:
                    pass

                # save current prices
                df_room.to_csv(cache_file,index=False)

            except Exception as e:
                st.error(f"{unit}/{room}: {e}")

    if alerts:
        body = "\n".join(alerts)
        send_slack_alert(f"🏨 Competitor Price Alert:\n{body}")
        st.success(f"{len(alerts)} competitor prices changed! Slack notification sent.")
    else:
        st.info("No competitor price changes detected.")
