import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timezone
import os
import time
from dotenv import load_dotenv
import joblib

# ---- Load API Key ----
load_dotenv()
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY")
COINGECKO_URL = "https://api.coingecko.com/api/v3"

headers = {
    "accept": "application/json",
    "x-cg-demo-api-key": COINGECKO_API_KEY
}

# ---- Exchange List ----
EXCHANGE_LIST = [
    {"id": "binance_futures", "name": "Binance (Futures)"},
    {"id": "bitget_futures", "name": "Bitget Futures"},
    {"id": "bybit", "name": "Bybit (Futures)"},
    {"id": "coinw_futures", "name": "CoinW (Futures)"},
    {"id": "gate_futures", "name": "Gate (Futures)"},
    {"id": "hyperliquid", "name": "Hyperliquid (Futures)"},
    {"id": "weex-futures", "name": "WEEX (Futures)"},
    {"id": "okex_swap", "name": "OKX (Futures)"},
    {"id": "xt_derivatives", "name": "XT.COM (Derivatives)"},
    {"id": "huobi_dm", "name": "HTX Futures"},
    {"id": "coincatch_derivatives", "name": "CoinCatch Derivatives"},
    {"id": "mxc_futures", "name": "MEXC (Futures)"},
    {"id": "bitmart_futures", "name": "Bitmart Futures"},
    {"id": "whitebit_futures", "name": "WhiteBIT Futures"},
    {"id": "toobit_derivatives", "name": "Toobit Futures"},
    {"id": "bingx_futures", "name": "BingX (Futures)"},
    {"id": "deepcoin_derivatives", "name": "Deepcoin (Derivatives)"},
    {"id": "dmex", "name": "DMEX"},
    {"id": "kumex", "name": "KuCoin Futures"},
    {"id": "lbank-futures", "name": "LBank (Futures)"},
    {"id": "deribit", "name": "Deribit"},
]
ALLOWED_MARKETS = {ex["name"] for ex in EXCHANGE_LIST}

# ---- Cache Config ----
CACHE_FILE = "perps_snapshot.joblib"
CACHE_TTL = 60 * 60 * 4  # 4 hours


# ---- Fetch data from API ----
def fetch_data():
    with st.spinner("Fetching data from Coingecko..."):
        time.sleep(1)
    resp = requests.get(f"{COINGECKO_URL}/derivatives",
                        headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    fetched_at = datetime.now(timezone.utc)

    filtered_data = [
        {
            "market": item["market"],
            "symbol": item["symbol"],
            "index_id": item["index_id"],
            "open_interest": item["open_interest"],
            "funding_rate": item["funding_rate"],
            "volume_24h": item["volume_24h"],
            "fetched_at": fetched_at.isoformat()
        }
        for item in data if item.get("market") in ALLOWED_MARKETS
    ]
    return pd.DataFrame(filtered_data)


# ---- Joblib Cache Wrapper ----
def get_data():
    if os.path.exists(CACHE_FILE):
        cached = joblib.load(CACHE_FILE)
        last_fetch = cached.get("fetched_at")
        if last_fetch:
            elapsed = (datetime.now(timezone.utc) - last_fetch).total_seconds()
            if elapsed < CACHE_TTL:
                return cached["data"]

    # Fetch fresh if no cache or cache expired
    df = fetch_data()
    joblib.dump(
        {"data": df, "fetched_at": datetime.now(timezone.utc)}, CACHE_FILE)
    return df


# ---- Streamlit Page Setup ----
st.set_page_config(page_title="Perps Snapshot", layout="wide")
st.title("📊 Perpetuals Snapshot Dashboard")
st.info('Data from Coingecko', icon="ℹ️")

# ---- Fetch data (cached with joblib) ----
df_db = get_data()

# ---- Use index_id as token ----
df_db["token"] = df_db["index_id"]

# ---- Highest-volume contract per token & exchange ----
df_best = (
    df_db.sort_values(["token", "market", "volume_24h"],
                      ascending=[True, True, False])
    .groupby(["token", "market"], as_index=False)
    .first()
)

# ---- Sidebar ----
with st.sidebar:
    st.header("ℹ️ About Funding Rates")
    st.markdown("""
    Funding rates are periodic payments exchanged between long and short positions in perpetual futures.  
    - **Positive funding**: Longs pay shorts → Bearish sentiment.  
    - **Negative funding**: Shorts pay longs → Bullish sentiment.  
    - **Near zero funding**: Neutral sentiment.  
    ---
    **Legend:**  
    - **Green**: Bullish (Funding < 0.005%)  
    - **White**: Neutral (Funding ≈ 0.01%)  
    - **Red**: Bearish (Funding > 0.01%)  
    """, unsafe_allow_html=True)

    # ---- Footer ----
    st.markdown("---")
    st.markdown(
        "🔨 Built by [@Daddy Brian](https://x.com/seniormanfm) "
        "and [@Daniel Amah](https://x.com/danny_4reel)",
        unsafe_allow_html=True,
    )


# ---- Funding Table ----
funding_table = df_best.pivot_table(
    index="token",
    columns="market",
    values="funding_rate",
    aggfunc="first"
).reset_index()

# ---- Open Interest Table ----
oi_table = df_best.pivot_table(
    index="token",
    columns="market",
    values="open_interest",
    aggfunc="first"
).reset_index()

# ---- Limit to Top 100 tokens ----
top_tokens = (
    df_best.groupby("token")["volume_24h"]
    .sum()
    .sort_values(ascending=False)
    .head(100)
    .index
)
funding_table = funding_table[funding_table["token"].isin(top_tokens)]
oi_table = oi_table[oi_table["token"].isin(top_tokens)]

# ---- Format Funding Table ----
for col in funding_table.columns[1:]:
    funding_table[col] = funding_table[col].apply(
        lambda x: f"{x:.4f}%" if pd.notnull(x) else "-"
    )


def color_funding(val):
    if val == "-":
        return ""
    try:
        num = float(val.strip('%'))
    except Exception:
        return ""
    if num < 0.005:
        return "color: green;"   # Bullish
    elif num > 0.01:
        return "color: red;"     # Bearish
    else:
        return "color: white;"   # Neutral


styled_funding_table = funding_table.style.applymap(
    color_funding, subset=funding_table.columns[1:]
)

# ---- Format Open Interest Table ----
for col in oi_table.columns[1:]:
    oi_table[col] = oi_table[col].apply(
        lambda x: f"${x:,.0f}" if pd.notnull(x) else "-"
    )

# ---- Tabs ----
tab1, tab2 = st.tabs(["📈 Funding Rates", "💰 Open Interest"])

with tab1:
    st.subheader("Funding Rates (Top 100 Most Traded Tokens)")
    st.dataframe(styled_funding_table, use_container_width=True,
                 height=800, hide_index=True)

with tab2:
    st.subheader("Open Interest (Top 100 Most Traded Tokens)")
    st.dataframe(oi_table, use_container_width=True,
                 height=800, hide_index=True)
