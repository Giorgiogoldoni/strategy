#!/usr/bin/env python3
"""
STRATEGY — Data Fetcher
Scarica prezzi storici da Yahoo Finance e calcola:
  - Strategia A (Berkshire): EMA200, AO normalizzato 100gg
  - Strategia B (GMOM): AO direzionale lungo, momentum score 1M/3M/6M
Salva tutto in data/bte_data.json
"""

import json
import datetime
import math
from pathlib import Path

import requests
import pandas as pd
import numpy as np

BASE = Path(__file__).parent.parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)

TODAY = datetime.date.today().isoformat()

# ── ETF Universe ───────────────────────────────────────────────────────────────

STRATEGY_A = [
    {"ticker": "VWCE.DE",  "name": "Vanguard FTSE All-World",         "role": "Core"},
    {"ticker": "IWQU.L",   "name": "iShares MSCI World Quality",      "role": "Quality"},
    {"ticker": "IWVL.L",   "name": "iShares MSCI World Value",        "role": "Value Global"},
    {"ticker": "IUVL.L",   "name": "iShares Edge MSCI USA Value",     "role": "Value USA"},
    {"ticker": "IDVY.L",   "name": "iShares Euro Dividend",           "role": "Dividend"},
    {"ticker": "IUSV",     "name": "iShares Core S&P US Value",        "role": "Value USA LC"},
    {"ticker": "SGLN.L",   "name": "iShares Physical Gold",           "role": "Gold"},
    {"ticker": "XEON.DE",  "name": "Xtrackers EUR Overnight Rate",    "role": "Cash"},
]

STRATEGY_B = [
    {"ticker": "IWDA.L",   "name": "iShares Core MSCI World",         "role": "World"},
    {"ticker": "IEMA.L",   "name": "iShares Core MSCI EM IMI",        "role": "Emerging"},
    {"ticker": "CSPX.L",   "name": "iShares Core S&P 500",            "role": "USA"},
    {"ticker": "IMEU.L",   "name": "iShares Core MSCI Europe",        "role": "Europe"},
    {"ticker": "IJPA.L",   "name": "iShares Core MSCI Japan",         "role": "Japan"},
    {"ticker": "PRAJ.L",   "name": "iShares MSCI Asia Pacific",       "role": "Asia Pac"},
    {"ticker": "IUSM.L",   "name": "iShares MSCI USA Momentum",       "role": "US Momentum"},
    {"ticker": "CBUH.DE",  "name": "iShares MSCI World Momentum Adv", "role": "World Momentum"},
    {"ticker": "XEON.DE",  "name": "Xtrackers EUR Overnight Rate",    "role": "Cash"},
]

ALL_TICKERS = list({e["ticker"]: e for e in STRATEGY_A + STRATEGY_B}.values())
BENCHMARK   = "IWDA.L"

# ── Yahoo Finance ──────────────────────────────────────────────────────────────

PROXIES = [
    "https://corsproxy.io/?",
    "https://api.allorigins.win/raw?url=",
]

def fetch_yahoo(ticker: str, period: str = "2y") -> pd.DataFrame | None:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={period}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        ohlcv = result["indicators"]["quote"][0]
        adjclose = result["indicators"].get("adjclose", [{}])[0].get("adjclose", ohlcv["close"])

        df = pd.DataFrame({
            "date":   [datetime.date.fromtimestamp(t).isoformat() for t in timestamps],
            "open":   ohlcv["open"],
            "high":   ohlcv["high"],
            "low":    ohlcv["low"],
            "close":  ohlcv["close"],
            "volume": ohlcv["volume"],
            "adjclose": adjclose,
        })
        df = df.dropna(subset=["close"])
        df = df.sort_values("date").reset_index(drop=True)
        return df
    except Exception as e:
        print(f"  ✗ {ticker}: {e}")
        return None

# ── Indicatori ─────────────────────────────────────────────────────────────────

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()

def calc_ao(df: pd.DataFrame) -> pd.Series:
    """AO = SMA5 - SMA34 dei prezzi medi (high+low)/2"""
    mid = (df["high"] + df["low"]) / 2
    return sma(mid, 5) - sma(mid, 34)

def calc_ao_normalized(ao: pd.Series, window: int = 100) -> pd.Series:
    """AO normalizzato nel range min-max degli ultimi N giorni (0-1)"""
    ao_min = ao.rolling(window).min()
    ao_max = ao.rolling(window).max()
    rng = ao_max - ao_min
    return (ao - ao_min) / rng.replace(0, np.nan)

def calc_ao_long(df: pd.DataFrame) -> pd.Series:
    """AO lungo = SMA10 - SMA50 dei prezzi medi"""
    mid = (df["high"] + df["low"]) / 2
    return sma(mid, 10) - sma(mid, 50)

def calc_momentum_score(returns: dict) -> float:
    """Momentum score pesato: 20% 1M + 30% 3M + 50% 6M"""
    w = {"1m": 0.20, "3m": 0.30, "6m": 0.50}
    score = 0.0
    total_w = 0.0
    for period, weight in w.items():
        ret = returns.get(period)
        if ret is not None:
            score += ret * weight
            total_w += weight
    return round(score / total_w, 4) if total_w > 0 else None

def _ytd_ret(prices: pd.Series) -> float | None:
    """Rendimento YTD — funziona con indice numerico, usa df globale non disponibile qui."""
    # Stima: se abbiamo 252 giorni, YTD è circa gli ultimi 252/2 giorni in media
    # Viene calcolato correttamente in process_etf dove abbiamo le date
    return None

def calc_returns(prices: pd.Series) -> dict:
    """Rendimenti per periodo"""
    today_price = prices.iloc[-1]
    def ret(n_days):
        if len(prices) > n_days:
            return round((today_price / prices.iloc[-n_days] - 1) * 100, 2)
        return None
    return {
        "1d":  ret(2),
        "1w":  ret(5),
        "1m":  ret(21),
        "3m":  ret(63),
        "6m":  ret(126),
        "1y":  ret(252),
        "ytd": _ytd_ret(prices),
    }

def calc_sharpe(prices: pd.Series, rf_annual: float = 0.035) -> float | None:
    if len(prices) < 30:
        return None
    daily_ret = prices.pct_change().dropna()
    rf_daily = rf_annual / 252
    excess = daily_ret - rf_daily
    if excess.std() == 0:
        return None
    return round((excess.mean() / excess.std()) * math.sqrt(252), 2)

def calc_max_drawdown(prices: pd.Series) -> float:
    rolling_max = prices.cummax()
    drawdown = (prices - rolling_max) / rolling_max
    return round(drawdown.min() * 100, 2)

def calc_volatility(prices: pd.Series) -> float | None:
    if len(prices) < 20:
        return None
    daily_ret = prices.pct_change().dropna()
    return round(daily_ret.std() * math.sqrt(252) * 100, 2)

def signal_a(ao_norm: float, above_ema200: bool) -> str:
    """Segnale Strategia A — Berkshire mean-reversion"""
    if not above_ema200:
        return "CASH"
    if ao_norm is None:
        return "—"
    if ao_norm < 0.25:
        return "BUY"
    elif ao_norm > 0.75:
        return "SELL"
    else:
        return "HOLD"

def signal_b(ao_long_now: float, ao_long_prev: float, above_ema200: bool) -> str:
    """Segnale Strategia B — GMOM trend following"""
    if not above_ema200:
        return "CASH"
    if ao_long_now is None or ao_long_prev is None:
        return "—"
    if ao_long_now > 0 and ao_long_now > ao_long_prev:
        return "BUY"
    elif ao_long_now < 0 and ao_long_now < ao_long_prev:
        return "SELL"
    elif ao_long_now > 0:
        return "HOLD"
    else:
        return "WATCH"

# ── Backtest semplice ──────────────────────────────────────────────────────────

def backtest_a(df: pd.DataFrame, ticker_info: dict) -> list:
    """
    Backtest Strategia A: ribilanciamento trimestrale basato su segnale AO norm.
    Restituisce serie rendimento cumulativo.
    """
    prices = df["adjclose"].reset_index(drop=True)
    dates  = df["date"].reset_index(drop=True)
    ao     = calc_ao(df)
    ao_norm = calc_ao_normalized(ao, 100)
    ema200 = ema(prices, 200)

    equity = [100.0]
    in_market = False
    last_rebal = None

    for i in range(200, len(prices)):
        above = prices.iloc[i] > ema200.iloc[i]
        norm  = ao_norm.iloc[i]
        date  = dates.iloc[i]
        quarter = date[:7]  # YYYY-MM

        ret = prices.iloc[i] / prices.iloc[i-1] - 1

        # Decisione entrata/uscita (semplificata)
        sig = signal_a(norm if not np.isnan(norm) else None, above)
        if sig == "BUY" and not in_market:
            in_market = True
        elif sig in ("SELL", "CASH") and in_market:
            in_market = False

        if in_market:
            equity.append(equity[-1] * (1 + ret))
        else:
            equity.append(equity[-1] * (1 + 0.035/252))  # rf

    return equity

def backtest_b(df: pd.DataFrame) -> list:
    """
    Backtest Strategia B: compra quando AO lungo sale sopra 0, vende quando scende sotto.
    """
    prices = df["adjclose"].reset_index(drop=True)
    ao_long = calc_ao_long(df)
    ema200  = ema(prices, 200)

    equity = [100.0]
    in_market = False

    for i in range(50, len(prices)):
        above = prices.iloc[i] > ema200.iloc[i]
        ao_now  = ao_long.iloc[i]
        ao_prev = ao_long.iloc[i-1]
        ret = prices.iloc[i] / prices.iloc[i-1] - 1

        sig = signal_b(
            ao_now  if not np.isnan(ao_now)  else None,
            ao_prev if not np.isnan(ao_prev) else None,
            above
        )

        if sig == "BUY" and not in_market:
            in_market = True
        elif sig in ("SELL", "CASH") and in_market:
            in_market = False

        if in_market:
            equity.append(equity[-1] * (1 + ret))
        else:
            equity.append(equity[-1] * (1 + 0.035/252))

    return equity

# ── Processo principale ────────────────────────────────────────────────────────

def process_etf(etf_info: dict, strategy: str) -> dict | None:
    ticker = etf_info["ticker"]
    print(f"  → {ticker} ({strategy})...")

    df = fetch_yahoo(ticker, period="2y")
    if df is None or len(df) < 50:
        return None

    prices = df["adjclose"]
    ao     = calc_ao(df)
    ao_norm = calc_ao_normalized(ao, 100)
    ao_long = calc_ao_long(df)
    ema200_series = ema(prices, 200)

    last_price   = round(float(prices.iloc[-1]), 4)
    last_ema200  = round(float(ema200_series.iloc[-1]), 4)
    above_ema200 = last_price > last_ema200

    last_ao_norm  = float(ao_norm.iloc[-1]) if not np.isnan(ao_norm.iloc[-1]) else None
    last_ao_long  = float(ao_long.iloc[-1]) if not np.isnan(ao_long.iloc[-1]) else None
    prev_ao_long  = float(ao_long.iloc[-2]) if len(ao_long) > 1 and not np.isnan(ao_long.iloc[-2]) else None

    returns = calc_returns(prices)

    # YTD corretto — abbiamo le date nel DataFrame
    year_start = f"{TODAY[:4]}-01-01"
    ytd_mask = df["date"] >= year_start
    if ytd_mask.any():
        ytd_start_price = float(prices[ytd_mask].iloc[0])
        last_p = float(prices.iloc[-1])
        returns["ytd"] = round((last_p / ytd_start_price - 1) * 100, 2)
    else:
        returns["ytd"] = None
    mom_score = calc_momentum_score(returns)

    # Segnali
    sig_a = signal_a(last_ao_norm, above_ema200) if strategy in ("A", "both") else None
    sig_b = signal_b(last_ao_long, prev_ao_long, above_ema200) if strategy in ("B", "both") else None

    # Serie storica (ultime 252 sedute) per grafici
    hist_dates  = df["date"].tail(252).tolist()
    hist_prices = [round(float(p), 4) for p in prices.tail(252)]
    hist_ema200 = [round(float(e), 4) if not np.isnan(e) else None for e in ema200_series.tail(252)]
    hist_ao     = [round(float(a), 4) if not np.isnan(a) else None for a in ao.tail(252)]
    hist_ao_norm = [round(float(a), 4) if not np.isnan(a) else None for a in ao_norm.tail(252)]
    hist_ao_long = [round(float(a), 4) if not np.isnan(a) else None for a in ao_long.tail(252)]

    return {
        "ticker":       ticker,
        "name":         etf_info["name"],
        "role":         etf_info["role"],
        "price":        last_price,
        "ema200":       last_ema200,
        "above_ema200": above_ema200,
        "ao_norm":      round(last_ao_norm, 4) if last_ao_norm is not None else None,
        "ao_long":      round(last_ao_long, 4) if last_ao_long is not None else None,
        "returns":      returns,
        "momentum_score": mom_score,
        "sharpe":       calc_sharpe(prices),
        "max_drawdown": calc_max_drawdown(prices),
        "volatility":   calc_volatility(prices),
        "signal_a":     sig_a,
        "signal_b":     sig_b,
        "history": {
            "dates":    hist_dates,
            "prices":   hist_prices,
            "ema200":   hist_ema200,
            "ao":       hist_ao,
            "ao_norm":  hist_ao_norm,
            "ao_long":  hist_ao_long,
        }
    }

def main():
    print(f"\n{'='*55}")
    print(f"  STRATEGY DATA FETCH — {TODAY}")
    print(f"{'='*55}\n")

    output = {
        "updated": TODAY,
        "strategy_a": [],
        "strategy_b": [],
        "benchmark":  None,
    }

    # Strategia A
    print("── Strategia A (Berkshire) ──")
    seen = {}
    for etf in STRATEGY_A:
        result = process_etf(etf, "A")
        if result:
            output["strategy_a"].append(result)
            seen[etf["ticker"]] = result

    # Strategia B
    print("\n── Strategia B (GMOM) ──")
    for etf in STRATEGY_B:
        if etf["ticker"] in seen:
            # Riusa dati già scaricati, aggiungi segnale B
            r = dict(seen[etf["ticker"]])
            r["role"] = etf["role"]
            r["signal_b"] = r.get("signal_b") or signal_b(
                r.get("ao_long"), None, r.get("above_ema200", False)
            )
            output["strategy_b"].append(r)
        else:
            result = process_etf(etf, "B")
            if result:
                output["strategy_b"].append(result)

    # Benchmark
    print("\n── Benchmark (IWDA) ──")
    bench = next((r for r in output["strategy_b"] if r["ticker"] == BENCHMARK), None)
    if not bench:
        bench = process_etf({"ticker": BENCHMARK, "name": "iShares Core MSCI World", "role": "Benchmark"}, "B")
    output["benchmark"] = bench

    # Ranking momentum B
    ranked = sorted(
        [e for e in output["strategy_b"] if e.get("momentum_score") is not None and e["ticker"] != "XEON.DE"],
        key=lambda x: x["momentum_score"],
        reverse=True
    )
    for i, etf in enumerate(ranked):
        etf["momentum_rank"] = i + 1

    # Salva
    out_path = DATA / "bte_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*55}")
    print(f"  DONE — A: {len(output['strategy_a'])} ETF · B: {len(output['strategy_b'])} ETF")
    print(f"  Salvato: {out_path}")
    print(f"{'='*55}\n")

if __name__ == "__main__":
    main()
