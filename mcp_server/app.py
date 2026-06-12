import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

from server import get_stock_data, calculate_indicators


st.set_page_config(page_title="Trading Terminal", layout="wide")

st.title("NEON TRADING TERMINAL")


TIMEFRAMES = {
    "15 Minute": {"period": "5d", "interval": "15m"},
    "1 Hour": {"period": "1mo", "interval": "1h"},
    "1 Day": {"period": "6mo", "interval": "1d"},
}


# ----------------------------
# SIDEBAR
# ----------------------------
refresh = st.sidebar.slider("Refresh (sec)", 5, 60, 10)
st_autorefresh(interval=refresh * 1000, key="refresh")

timeframe_label = st.sidebar.selectbox(
    "Timeframe",
    list(TIMEFRAMES.keys()),
    index=2,
)
timeframe = TIMEFRAMES[timeframe_label]

if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["NIFTY 50", "BANKNIFTY", "RELIANCE", "TCS", "HDFCBANK", "INFY"]

st.sidebar.markdown("## Watchlist")

new_stock = st.sidebar.text_input("Add stock")

if st.sidebar.button("Add"):
    cleaned = new_stock.strip().upper()
    if cleaned and cleaned not in st.session_state.watchlist:
        st.session_state.watchlist.append(cleaned)

stock = st.sidebar.radio("Select", st.session_state.watchlist)


# ----------------------------
# DATA
# ----------------------------
data = get_stock_data(
    stock,
    period=timeframe["period"],
    interval=timeframe["interval"],
)
ind = calculate_indicators(
    stock,
    period=timeframe["period"],
    interval=timeframe["interval"],
)

if "error" in data:
    st.error(data["error"])
    st.stop()

if "error" in ind:
    st.error(ind["error"])
    st.stop()


# ----------------------------
# TOP CARDS
# ----------------------------
col1, col2, col3, col4 = st.columns(4)

col1.metric("Price", data["current_price"])
col2.metric("Change %", data["change_pct"])
col3.metric("RSI", ind["rsi_14"])
col4.metric("Signal", ind["signal"])

level1, level2, level3, level4 = st.columns(4)
level1.metric("Entry", ind["entry"])
level2.metric("Stop Loss", ind["stop_loss"])
level3.metric("Target", ind["target"])
level4.metric("Risk Reward", ind["risk_reward"])

st.divider()


# ----------------------------
# CHART SECTION
# ----------------------------
left, right = st.columns([3, 1])

with left:
    st.subheader(f"Price Chart - {timeframe_label}")

    df = pd.DataFrame(data["recent_candles"])
    df["Date"] = pd.to_datetime(df["Date"])

    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=df["Date"],
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="Price",
        )
    )

    if "ema_series" in ind:
        ema_df = pd.DataFrame(ind["ema_series"])
        ema_df["Date"] = pd.to_datetime(ema_df["Date"])
        fig.add_trace(
            go.Scatter(
                x=ema_df["Date"],
                y=ema_df["EMA20"],
                mode="lines",
                name="EMA 20",
                line=dict(width=1.5, color="#00d084"),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=ema_df["Date"],
                y=ema_df["EMA50"],
                mode="lines",
                name="EMA 50",
                line=dict(width=1.5, color="#ffb000"),
            )
        )

    fig.update_layout(
        height=600,
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        font=dict(color="#f5f5f5"),
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )

    st.plotly_chart(fig, width="stretch")


# ----------------------------
# SIDE PANEL
# ----------------------------
with right:
    st.subheader("Signal Engine")

    signal = ind["signal"]

    if "BUY" in signal:
        st.success(signal)
    elif "SELL" in signal:
        st.error(signal)
    else:
        st.info(signal)

    st.markdown("### Signal Score")
    st.progress(max(0, min(100, int(ind["score_percent"]))))
    st.write(f'{ind["score"]} / 5 {ind["score_label"].lower()} checks passed')
    st.caption(
        f'Bullish: {ind["bullish_score"]}/5 | Bearish: {ind["bearish_score"]}/5'
    )

    st.markdown("### Levels")
    st.write("Support:", ind["support"])
    st.write("Resistance:", ind["resistance"])
    st.write("Volume Status:", ind["volume_status"])

    st.markdown("### Indicators")
    st.write("EMA 20:", ind["ema20"])
    st.write("EMA 50:", ind["ema50"])
    st.write("MACD:", ind["macd"])
    st.write("MACD Signal:", ind["macd_signal"])
    st.write("MACD Histogram:", ind["macd_histogram"])


# ----------------------------
# MINI SCANNER
# ----------------------------
st.divider()
st.subheader("Quick Scanner")

scanner = []

for item in st.session_state.watchlist:
    row = calculate_indicators(
        item,
        period=timeframe["period"],
        interval=timeframe["interval"],
    )
    if "error" not in row:
        scanner.append(
            {
                "Stock": item,
                "Timeframe": timeframe_label,
                "Price": row["current_price"],
                "RSI": row["rsi_14"],
                "Signal": row["signal"],
                "Entry": row["entry"],
                "Stop Loss": row["stop_loss"],
                "Target": row["target"],
                "Risk Reward": row["risk_reward"],
            }
        )

st.dataframe(pd.DataFrame(scanner), width="stretch", hide_index=True)
