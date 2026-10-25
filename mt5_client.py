from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from config import get_settings

logger = logging.getLogger(__name__)


class MT5ClientError(RuntimeError):
    """Raised when MT5 data access or symbol discovery fails."""


@dataclass(frozen=True)
class SymbolRecord:
    name: str
    description: str
    path: str = ""


class MT5Client:
    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self._mt5 = None

    def _import_mt5(self) -> Any:
        try:
            import MetaTrader5 as mt5  # type: ignore
        except ModuleNotFoundError as exc:  # pragma: no cover - environment feature
            raise MT5ClientError("MetaTrader5 package is not installed. Install it for live MT5 use.") from exc
        return mt5

    def initialize(self) -> Any:
        mt5 = self._import_mt5()
        init_kwargs = {
            "path": os.getenv("MT5_PATH"),
            "login": int(os.getenv("MT5_LOGIN", "0")) if os.getenv("MT5_LOGIN") else None,
            "password": os.getenv("MT5_PASSWORD"),
            "server": os.getenv("MT5_SERVER"),
            "timeout": int(os.getenv("MT5_TIMEOUT", "10000")),
        }
        init_kwargs = {key: value for key, value in init_kwargs.items() if value is not None}
        if not mt5.initialize(**init_kwargs):
            raise MT5ClientError(f"MT5.initialize() failed: {mt5.last_error()}")
        self._mt5 = mt5
        logger.info("MetaTrader5 connected successfully.")
        return mt5

    @property
    def mt5(self) -> Any:
        if self._mt5 is None:
            return self.initialize()
        return self._mt5

    def is_connected(self) -> bool:
        try:
            mt5 = self.mt5
            terminal = mt5.terminal_info()
            return bool(terminal is not None and getattr(terminal, "connected", False))
        except Exception:
            return False

    def reconnect(self) -> Any:
        logger.warning("MT5 connection lost; attempting reconnect.")
        try:
            self.shutdown()
        except Exception:
            pass
        return self.initialize()

    def shutdown(self) -> None:
        if self._mt5 is None:
            return
        try:
            self._mt5.shutdown()
        finally:
            self._mt5 = None

    def discover_symbols(self, candidates: Iterable[str] | None = None) -> list[SymbolRecord]:
        mt5 = self.mt5
        symbol_names = list(candidates or [])
        if not symbol_names:
            symbol_names = [
                self.settings.mt5_eurusd_symbol,
                self.settings.mt5_gbpusd_symbol,
                self.settings.mt5_xauusd_symbol,
                self.settings.mt5_dxy_symbol,
            ]
        symbol_names = [name.strip() for name in symbol_names if name and name.strip()]
        if not symbol_names:
            raise MT5ClientError("No MT5 symbol names were configured. Populate the MT5_*_SYMBOL environment variables.")

        records: list[SymbolRecord] = []
        all_symbols = mt5.symbols_get()
        if not all_symbols:
            raise MT5ClientError("MT5 returned no symbols. Verify the terminal is connected and the symbol list is loaded.")

        symbol_map = {item.name: item for item in all_symbols}
        for name in symbol_names:
            info = symbol_map.get(name)
            if info is not None:
                records.append(SymbolRecord(name=info.name, description=getattr(info, "description", ""), path=getattr(info, "path", "")))
            else:
                for item in all_symbols:
                    candidate_name = getattr(item, "name", "")
                    candidate_desc = getattr(item, "description", "").lower()
                    if name.lower() in candidate_name.lower() or name.lower() in candidate_desc:
                        records.append(SymbolRecord(name=candidate_name, description=candidate_desc, path=getattr(item, "path", "")))
                        break
        if not records:
            names = ", ".join(symbol_names)
            raise MT5ClientError(f"Could not resolve MT5 symbols: {names}. Check your symbol mappings and terminal symbol list.")
        return records

    def resolve_symbol(self, instrument: str) -> str:
        mapping = {
            "EURUSD": self.settings.mt5_eurusd_symbol,
            "GBPUSD": self.settings.mt5_gbpusd_symbol,
            "XAUUSD": self.settings.mt5_xauusd_symbol,
            "DXY": self.settings.mt5_dxy_symbol,
        }
        symbol = mapping.get(instrument)
        if symbol:
            return symbol
        raise MT5ClientError(f"No MT5 symbol mapping configured for {instrument}. Update the environment variables.")

    def symbol_is_available(self, symbol_name: str) -> bool:
        info = self.mt5.symbol_info(symbol_name)
        if info is None:
            return False
        return bool(getattr(info, "visible", True) or getattr(info, "select", True))

    def ensure_symbol_selected(self, symbol_name: str) -> str:
        if not self.symbol_is_available(symbol_name):
            if not self.mt5.symbol_select(symbol_name, True):
                raise MT5ClientError(f"Unable to select MT5 symbol '{symbol_name}'.")
        return symbol_name

    def get_recent_candles(self, symbol_name: str, count: int = 200, timeframe: Any | None = None) -> list[dict[str, Any]]:
        if not self.symbol_is_available(symbol_name):
            self.ensure_symbol_selected(symbol_name)
        mt5 = self.mt5
        timeframe = timeframe or getattr(mt5, "TIMEFRAME_M15", 15)
        rates = mt5.copy_rates_from_pos(symbol_name, timeframe, 0, count)
        if rates is None:
            raise MT5ClientError(f"No M15 OHLC data returned for '{symbol_name}'.")
        rows = []
        for rate in rates:
            rows.append(
                {
                    "time": datetime.fromtimestamp(int(rate[0]), tz=timezone.utc),
                    "open": float(rate[1]),
                    "high": float(rate[2]),
                    "low": float(rate[3]),
                    "close": float(rate[4]),
                    "volume": int(rate[5]),
                }
            )
        rows.sort(key=lambda item: item["time"])
        return rows
