"""Strict, read-only yfinance adapter for the local paper stock service."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable

import pandas as pd
import yfinance as yf


@dataclass(frozen=True)
class StockQuote:
    symbol: str
    price: Decimal
    as_of: datetime
    fetched_at: datetime


def normalize_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        raise ValueError("Stock symbol must be a string")
    normalized = symbol.strip().upper().replace(".", "-")
    if not re.fullmatch(r"[A-Z]{1,5}(?:-[A-Z])?", normalized):
        raise ValueError("Unsupported US stock symbol")
    return normalized


def _timestamp(value, *, check_future: bool = True) -> datetime:
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp) or stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("Market timestamp must be present and timezone aware")
        result = stamp.to_pydatetime().astimezone(timezone.utc)
        if check_future and result > datetime.now(timezone.utc):
            raise ValueError("Market timestamp is in the future")
        return result
    except (TypeError, OverflowError) as exc:
        raise ValueError("Invalid market timestamp") from exc


def _number(value, *, allow_zero: bool = False) -> Decimal:
    try:
        if isinstance(value, bool):
            raise ValueError("Boolean market price is invalid")
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or (not allow_zero and number == 0):
            raise ValueError("Market price must be finite and positive")
        return number
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("Invalid market number") from exc


class ExchangeProvider:
    """No order execution or broker dependencies. No fabricated source timestamps.

    yfinance often labels common and preferred stocks alike as EQUITY. Ambiguous
    metadata therefore requires an operator-maintained approved_symbols list;
    that list never overrides a conflicting instrument, exchange or currency.
    """

    _EXCHANGES = frozenset({"NYQ", "NMS", "NGM", "NCM", "ASE"})
    _INTERVALS = {"1m": "5d", "5m": "1mo", "15m": "1mo", "30m": "1mo",
                  "60m": "1y", "1h": "1y", "1d": "5y", "1wk": "max", "1mo": "max"}
    _EXCLUDED = re.compile(
        r"\b(?:ADR|ADS|GDR|ETF|ETN|PREFERRED|PREFERENCE|PREF|DEPOSITARY|DEPOSITORY|"
        r"WARRANTS?|UNITS?|OPTIONS?|CRYPTOCURRENCY|FUND)\b", re.IGNORECASE
    )

    def __init__(self, *, approved_symbols: Iterable[str] = ()):
        self._approved_symbols = frozenset(normalize_symbol(s) for s in approved_symbols)

    def _instrument(self, symbol: str):
        ticker = yf.Ticker(symbol)
        info = ticker.info
        if not isinstance(info, dict):
            raise ValueError("Missing security metadata")
        if normalize_symbol(info.get("symbol")) != symbol:
            raise ValueError("Security metadata symbol mismatch")
        if info.get("quoteType") != "EQUITY" or info.get("currency") != "USD":
            raise ValueError("Only USD US common stocks are supported")
        if info.get("exchange") not in self._EXCHANGES:
            raise ValueError("Unsupported US stock exchange")
        description = " ".join(str(info.get(k, "")) for k in
                               ("shortName", "longName", "securityType", "typeDisp", "instrumentType"))
        if (self._EXCLUDED.search(description.replace("_", " ")) or
                any(info.get(k) for k in ("isETF", "isAdr", "isADR", "isPreferred"))):
            raise ValueError("Unsupported instrument: only ordinary common stocks are allowed")
        security_type = str(info.get("securityType", "")).upper().replace("_", " ")
        explicit_common = security_type in {"COMMON STOCK", "COMMON SHARES", "COMMONSTOCK"}
        explicit_common = explicit_common or bool(re.search(r"\bcommon (?:stock|shares)\b", description, re.I))
        if not explicit_common and symbol not in self._approved_symbols:
            raise ValueError("Ambiguous common-stock metadata: operator approval required")
        return ticker, info

    def fetch_quote(self, symbol: str) -> StockQuote:
        symbol = normalize_symbol(symbol)
        ticker, _ = self._instrument(symbol)
        history = ticker.history(period="1d", interval="1m", auto_adjust=False,
                                 prepost=False, actions=False)
        if not isinstance(history, pd.DataFrame) or history.empty or "Close" not in history:
            raise ValueError("No regular-session stock price available")
        history = history.sort_index()
        as_of = _timestamp(history.index[-1])
        price = _number(history.iloc[-1]["Close"])
        return StockQuote(symbol, price, as_of, datetime.now(timezone.utc))

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1d", limit: int = 100) -> list[dict]:
        symbol = normalize_symbol(symbol)
        if not isinstance(timeframe, str) or timeframe not in self._INTERVALS:
            raise ValueError("Unsupported history interval")
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("History limit must be an integer from 1 to 1000")
        ticker, _ = self._instrument(symbol)
        history = ticker.history(period=self._INTERVALS[timeframe], interval=timeframe,
                                 auto_adjust=False, prepost=False, actions=False)
        if not isinstance(history, pd.DataFrame) or history.empty:
            raise ValueError("No stock history available")
        if not {"Open", "High", "Low", "Close", "Volume"}.issubset(history.columns):
            raise ValueError("Incomplete stock history")
        result = []
        for index, row in history.sort_index().tail(limit).iterrows():
            bar = {"timestamp": _timestamp(index).isoformat()}
            for column in ("Open", "High", "Low", "Close", "Volume"):
                number = float(_number(row[column], allow_zero=column == "Volume"))
                if not math.isfinite(number):
                    raise ValueError("Nonfinite stock history")
                bar[column.lower()] = number
            if bar["low"] > min(bar["open"], bar["close"]) or bar["high"] < max(bar["open"], bar["close"]):
                raise ValueError("Inconsistent OHLC history")
            result.append(bar)
        return result

    def search_symbol(self, query: str, limit: int = 10) -> list[dict]:
        if not isinstance(query, str) or not query.strip() or len(query) > 100:
            raise ValueError("Search query must contain 1 to 100 characters")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("Search limit must be an integer from 1 to 50")
        search = yf.Search(query.strip(), max_results=limit, news_count=0)
        result, seen = [], set()
        for entry in search.quotes:
            try:
                symbol = normalize_symbol(entry.get("symbol"))
                if symbol in seen:
                    continue
                seen.add(symbol)
                _, info = self._instrument(symbol)
            except (ValueError, TypeError, AttributeError):
                continue
            result.append({"symbol": symbol, "name": str(info.get("longName") or info.get("shortName") or symbol),
                           "exchange": info["exchange"], "currency": "USD", "type": "COMMON_STOCK"})
            if len(result) >= limit:
                break
        return result

    def check_corporate_actions(self, symbol: str, since: datetime) -> None:
        """Block holdings affected by splits; dividends are explicitly not modeled.

        Fetch unadjusted action-bearing history with raise_errors=True: yfinance's
        convenience splits property can silently convert network errors to empty
        data. Empty/malformed responses cannot certify a holding as split-free.
        """
        symbol = normalize_symbol(symbol)
        since_utc = _timestamp(since, check_future=False)
        ticker, _ = self._instrument(symbol)
        try:
            history = ticker.history(start=(since_utc - timedelta(days=7)).date().isoformat(),
                                     interval="1d", auto_adjust=False, prepost=False,
                                     actions=True, raise_errors=True)
        except Exception as exc:
            raise ValueError("Unable to verify stock splits") from exc
        if (not isinstance(history, pd.DataFrame) or history.empty or
                "Stock Splits" not in history):
            raise ValueError("Unable to verify stock splits")
        for timestamp, ratio in history["Stock Splits"].items():
            if _timestamp(timestamp) >= since_utc and _number(ratio, allow_zero=True) not in (0, 1):
                raise ValueError("Stock split since acquisition requires account reconciliation")
