from __future__ import annotations

import os

from mt5_client import MT5Client, MT5ClientError


def main() -> int:
    print("MT5 diagnosis is intended for a local terminal with MetaTrader5 installed.")
    print("Configured mappings:")
    for key in ("MT5_EURUSD_SYMBOL", "MT5_GBPUSD_SYMBOL", "MT5_XAUUSD_SYMBOL", "MT5_DXY_SYMBOL"):
        print(f"  {key}={os.getenv(key, '<unset>')}")
    try:
        client = MT5Client()
        print("Testing connection...")
        if not client.is_connected():
            print("MT5 is not connected. Initialize the terminal or configure the credentials.")
            return 0
        print("MT5 is connected.")
        for name in [
            client.settings.mt5_eurusd_symbol,
            client.settings.mt5_gbpusd_symbol,
            client.settings.mt5_xauusd_symbol,
            client.settings.mt5_dxy_symbol,
        ]:
            if not name:
                continue
            try:
                info = client.mt5.symbol_info(name)
                print(f"  {name}: available={bool(info)}")
            except Exception as exc:  # pragma: no cover - live environment only
                print(f"  {name}: error={exc}")
        return 0
    except MT5ClientError as exc:
        print(f"Configuration or connection issue: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
