"""
Stock Engine for the Streamlit trading terminal.

Returns Python dictionaries so the functions can be used directly by Streamlit.
Supports multi-timeframe OHLCV, stronger signal logic, entry, stop loss, target,
and risk-reward calculations.
"""

import yfinance as yf
import pandas as pd
import ta
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("nse-stock-engine")


def _normalize_ticker(ticker: str) -> str:
    ticker = ticker.strip().upper()
    compact = ticker.replace(" ", "").replace("-", "")

    yahoo_aliases = {
        "NIFTY": "^NSEI",
        "NIFTY50": "^NSEI",
        "NIFTYFIFTY": "^NSEI",
        "NSEI": "^NSEI",
        "^NSEI": "^NSEI",
        "BANKNIFTY": "^NSEBANK",
        "NIFTYBANK": "^NSEBANK",
        "NSEBANK": "^NSEBANK",
        "^NSEBANK": "^NSEBANK",
        "FINNIFTY": "NIFTY_FIN_SERVICE.NS",
        "NIFTYIT": "^CNXIT",
        "MIDCPNIFTY": "NIFTY_MID_SELECT.NS",
    }

    if compact in yahoo_aliases:
        return yahoo_aliases[compact]

    if ticker.startswith("^") or ticker.endswith(".NS") or ticker.endswith(".BO"):
        return ticker

    return f"{ticker}.NS"


def _safe_round(value, digits: int = 2):
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def _download_history(symbol: str, period: str, interval: str):
    stock = yf.Ticker(symbol)
    hist = stock.history(period=period, interval=interval, auto_adjust=False)

    if hist.empty:
        return stock, hist

    hist = hist.dropna(subset=["Open", "High", "Low", "Close"])
    return stock, hist


@mcp.tool()
def get_stock_data(ticker: str, period: str = "6mo", interval: str = "1d"):
    """
    Returns OHLCV and price data.
    """
    try:
        symbol = _normalize_ticker(ticker)
        stock, hist = _download_history(symbol, period, interval)

        if hist.empty:
            return {"error": f"No data found for {symbol}"}

        info = stock.fast_info
        current_price = float(info.get("last_price", hist["Close"].iloc[-1]))

        if len(hist) >= 2:
            prev_close = float(hist["Close"].iloc[-2])
        else:
            prev_close = float(info.get("previous_close", hist["Close"].iloc[-1]))

        change_pct = 0 if prev_close == 0 else round((current_price - prev_close) / prev_close * 100, 2)

        recent = hist.tail(80).reset_index()
        date_col = "Datetime" if "Datetime" in recent.columns else "Date"
        recent["Date"] = recent[date_col].astype(str)

        candles = recent[["Date", "Open", "High", "Low", "Close", "Volume"]].to_dict(
            orient="records"
        )

        return {
            "ticker": symbol,
            "current_price": _safe_round(current_price),
            "previous_close": _safe_round(prev_close),
            "change_pct": change_pct,
            "day_high": _safe_round(hist["High"].iloc[-1]),
            "day_low": _safe_round(hist["Low"].iloc[-1]),
            "52w_high": _safe_round(info.get("year_high", 0)),
            "52w_low": _safe_round(info.get("year_low", 0)),
            "period": period,
            "interval": interval,
            "recent_candles": candles,
        }

    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def calculate_indicators(ticker: str, period: str = "6mo", interval: str = "1d"):
    """
    Calculates RSI, MACD, EMA, volume confirmation, support/resistance,
    trading levels, and a scanner-ready signal label.
    """
    try:
        symbol = _normalize_ticker(ticker)
        _, hist = _download_history(symbol, period, interval)

        if hist.empty or len(hist) < 50:
            return {"error": f"Not enough data for {symbol}. Try a higher period/timeframe."}

        close = hist["Close"]
        high = hist["High"]
        low = hist["Low"]
        volume = hist["Volume"]

        rsi = ta.momentum.RSIIndicator(close, window=14).rsi()
        macd = ta.trend.MACD(close)
        ema20 = ta.trend.EMAIndicator(close, window=20).ema_indicator()
        ema50 = ta.trend.EMAIndicator(close, window=50).ema_indicator()
        avg_volume = volume.rolling(20).mean()

        current_price = float(close.iloc[-1])
        rsi_latest = float(rsi.iloc[-1])
        macd_latest = float(macd.macd().iloc[-1])
        macd_signal_latest = float(macd.macd_signal().iloc[-1])
        macd_hist_latest = float(macd.macd_diff().iloc[-1])
        ema20_latest = float(ema20.iloc[-1])
        ema50_latest = float(ema50.iloc[-1])
        volume_latest = float(volume.iloc[-1])
        avg_volume_latest = float(avg_volume.iloc[-1])

        recent = hist.tail(20)
        support = float(recent["Low"].min())
        resistance = float(recent["High"].max())

        bullish_checks = [
            ema20_latest > ema50_latest,
            current_price > ema20_latest,
            45 <= rsi_latest <= 68,
            macd_latest > macd_signal_latest,
            volume_latest > avg_volume_latest,
        ]
        bearish_checks = [
            ema20_latest < ema50_latest,
            current_price < ema20_latest,
            rsi_latest >= 70 or rsi_latest <= 35,
            macd_latest < macd_signal_latest,
            volume_latest < avg_volume_latest,
        ]

        bullish_score = sum(bullish_checks)
        bearish_score = sum(bearish_checks)

        if bullish_score >= 4:
            signal = "STRONG BUY"
        elif bullish_score == 3:
            signal = "BUY"
        elif bearish_score >= 4:
            signal = "STRONG SELL"
        elif bearish_score == 3:
            signal = "SELL"
        else:
            signal = "HOLD"

        risk_buffer = current_price * 0.01

        if "BUY" in signal:
            entry = current_price
            stop_loss = min(support, current_price - risk_buffer)
            risk = max(entry - stop_loss, risk_buffer)
            target = entry + (risk * 2)
        elif "SELL" in signal:
            entry = current_price
            stop_loss = max(resistance, current_price + risk_buffer)
            risk = max(stop_loss - entry, risk_buffer)
            target = entry - (risk * 2)
        else:
            entry = current_price
            stop_loss = support
            target = resistance
            risk = abs(entry - stop_loss)

        reward = abs(target - entry)
        risk_reward = 0 if risk == 0 else reward / risk

        ema_recent = hist.tail(80).reset_index()
        date_col = "Datetime" if "Datetime" in ema_recent.columns else "Date"
        ema_recent["Date"] = ema_recent[date_col].astype(str)
        ema_recent["EMA20"] = ema20.tail(80).values
        ema_recent["EMA50"] = ema50.tail(80).values

        return {
            "ticker": symbol,
            "period": period,
            "interval": interval,
            "current_price": _safe_round(current_price),
            "rsi_14": _safe_round(rsi_latest),
            "macd": _safe_round(macd_latest),
            "macd_signal": _safe_round(macd_signal_latest),
            "macd_histogram": _safe_round(macd_hist_latest),
            "ema20": _safe_round(ema20_latest),
            "ema50": _safe_round(ema50_latest),
            "support": _safe_round(support),
            "resistance": _safe_round(resistance),
            "entry": _safe_round(entry),
            "stop_loss": _safe_round(stop_loss),
            "target": _safe_round(target),
            "risk_reward": _safe_round(risk_reward),
            "volume": int(volume_latest),
            "avg_volume_20": int(avg_volume_latest),
            "volume_status": "Above Average" if volume_latest > avg_volume_latest else "Below Average",
            "score": bullish_score if "BUY" in signal or signal == "HOLD" else bearish_score,
            "score_percent": (bullish_score if "BUY" in signal or signal == "HOLD" else bearish_score) * 20,
            "signal": signal,
            "ema_series": ema_recent[["Date", "EMA20", "EMA50"]].dropna().to_dict(orient="records"),
        }

    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    print("Engine Test Mode")
    print(get_stock_data("RELIANCE", period="5d", interval="15m"))
    print(calculate_indicators("RELIANCE", period="6mo", interval="1d"))