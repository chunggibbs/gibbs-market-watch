"""Fetch Taiwan market-wide institutional buy/sell flows from FinMind.

Output is a standalone JSON file. Existing USD/TWD files are untouched.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

API_URL = "https://api.finmindtrade.com/api/v4/data"
DATASET = "TaiwanStockTotalInstitutionalInvestors"
OUTPUT_FILE = Path("institutional_data.json")
TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()
TYPES = {
    "Foreign_Investor": "外資及陸資（不含外資自營商）",
    "Investment_Trust": "投信",
    "Dealer_self": "自營商（自行買賣）",
}
TWD_PER_100M = 100_000_000
TW_TZ = timezone(timedelta(hours=8))


def fetch_data(start_date: str, end_date: str) -> list[dict]:
    params = {
        "dataset": DATASET,
        "start_date": start_date,
        "end_date": end_date,
        "token": TOKEN,
    }
    for attempt in range(3):
        try:
            response = requests.get(API_URL, params=params, timeout=45)
            response.raise_for_status()
            result = response.json()
            if result.get("status") != 200:
                raise RuntimeError(f"FinMind status={result.get('status')}: {result.get('msg')}")
            data = result.get("data")
            if not isinstance(data, list):
                raise ValueError("FinMind API data is not a list")
            return data
        except (requests.RequestException, ValueError) as exc:
            if attempt == 2:
                raise
            print(f"Retry {attempt + 1}: {exc}", file=sys.stderr)
            time.sleep(2 ** attempt)
    raise RuntimeError("API retries exhausted")


def load_existing() -> dict[str, dict]:
    if not OUTPUT_FILE.exists():
        return {}
    with OUTPUT_FILE.open("r", encoding="utf-8") as f:
        saved = json.load(f)
    return {row["date"]: row for row in saved.get("data", []) if "date" in row}


def main() -> None:
    if not TOKEN:
        raise RuntimeError("Missing FINMIND_TOKEN environment variable")

    today = datetime.now(TW_TZ).date()
    existing = load_existing()
    # Backfill 90 calendar days on first run; refresh recent 7 days thereafter.
    start = today - timedelta(days=7 if existing else 90)
    raw = fetch_data(start.isoformat(), today.isoformat())

    grouped: dict[str, dict[str, dict]] = {}
    for item in raw:
        kind = item.get("name", item.get("type"))
        if kind not in TYPES:
            continue
        day = str(item.get("date", ""))
        if not day:
            continue
        buy = int(item["buy"])
        sell = int(item["sell"])
        grouped.setdefault(day, {})[kind] = {
            "buy_100m": round(buy / TWD_PER_100M, 4),
            "sell_100m": round(sell / TWD_PER_100M, 4),
            "net_buy_100m": round((buy - sell) / TWD_PER_100M, 4),
        }

    for day, kinds in grouped.items():
        # Incomplete dates are not written as complete market data.
        if not all(k in kinds for k in TYPES):
            print(f"Skipping incomplete date: {day}")
            continue
        existing[day] = {
            "date": day,
            "foreign_investor": kinds["Foreign_Investor"],
            "investment_trust": kinds["Investment_Trust"],
            "dealer_self": kinds["Dealer_self"],
        }

    if not existing:
        raise RuntimeError("No complete institutional data received; output not changed")

    payload = {
        "source": "FinMind",
        "dataset": DATASET,
        "unit": "TWD 100 million (億元)",
        "updated_at_taipei": datetime.now(TW_TZ).isoformat(timespec="seconds"),
        "data": [existing[day] for day in sorted(existing)],
    }
    tmp = OUTPUT_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(OUTPUT_FILE)
    print(f"Saved {len(payload['data'])} trading days; latest: {max(existing)}")


if __name__ == "__main__":
    main()
