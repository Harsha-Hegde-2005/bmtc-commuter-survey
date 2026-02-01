import json
import streamlit as st
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

from temp2 import find_survey_buses, norm, stops_df

# --------------------------------------------------
# PAGE CONFIG
# --------------------------------------------------
st.set_page_config(
    page_title="BMTC Commuter Survey",
    page_icon="🚌",
    layout="centered"
)

st.markdown("<h1 style='text-align:center;'>🚌 BMTC Commuter Survey</h1>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align:center;color:gray;'>Academic survey to improve BMTC journey planning</p>",
    unsafe_allow_html=True
)

st.divider()

# --------------------------------------------------
# GOOGLE SHEETS BACKEND
# --------------------------------------------------
@st.cache_resource
def get_sheet():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    service_account_info = json.loads(
        st.secrets["gcp_service_account"]["json"]
    )

    creds = Credentials.from_service_account_info(
        service_account_info,
        scopes=scope
    )

    client = gspread.authorize(creds)
    return client.open("BMTC Survey Responses").sheet1


def save_response(record):
    sheet = get_sheet()
    sheet.append_row([
        record["timestamp"],
        record["source"],
        record["destination"],
        record["selected_buses"],
        record["other_bus"],
        record["wait_time"],
        record["frequency"],
        record["transfers"],
        record["intermediate_stops"]
    ])

# --------------------------------------------------
# FORM
# --------------------------------------------------
all_stops = sorted(stops_df.stop_name.unique())

st.subheader("📍 Your Regular Journey")

src = st.selectbox("Source Stop", all_stops)
dst = st.selectbox("Destination Stop", all_stops)

if src and dst and src != dst:
    possible_buses = find_survey_buses(norm(src), norm(dst))

    st.subheader("🚌 Bus(es) You Usually Take")
    selected_buses = st.multiselect(
        "Select all that apply",
        possible_buses + ["Other bus not listed"]
    )

    other_bus = ""
    if "Other bus not listed" in selected_buses:
        other_bus = st.text_input("Enter the bus number")

    wait_time = st.radio(
        "Typical waiting time",
        ["< 5 min", "5–10 min", "10–20 min", "> 20 min"]
    )

    frequency = st.radio(
        "Bus frequency during peak hours",
        [
            "Every 5–10 minutes",
            "Every 10–20 minutes",
            "Every 20–40 minutes",
            "Rare / unpredictable"
        ]
    )

    transfers = st.radio(
        "Bus changes required",
        ["Direct (0)", "1 transfer", "2+ transfers"]
    )

    stops_text = st.text_area("Major intermediate stops (optional)")

    if st.button("📨 Submit Response"):
        record = {
            "timestamp": datetime.now().isoformat(),
            "source": src,
            "destination": dst,
            "selected_buses": ",".join(selected_buses),
            "other_bus": other_bus,
            "wait_time": wait_time,
            "frequency": frequency,
            "transfers": transfers,
            "intermediate_stops": stops_text
        }

        try:
            save_response(record)
            st.success("✅ Response saved successfully!")
        except Exception as e:
            st.error(f"❌ Error saving response: {e}")

