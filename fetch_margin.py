#!/usr/bin/env python3
"""Fetch Taiwan market-wide margin financing balances from FinMind.

Writes margin_data.json.
Other market dashboard files are untouched.
"""

import json
import os
import sys
import time

from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


# ==================================================
# 基本設定
# ==================================================

API_URL = "https://api.finmindtrade.com/api/v4/data"

DATASET = "TaiwanStockTotalMarginPurchaseShortSale"

TARGET_NAME = "MarginPurchaseMoney"

ROOT = Path(__file__).resolve().parent

OUTPUT_FILE = ROOT / "margin_data.json"

TOKEN = os.environ.get("FINMIND_TOKEN", "").strip()

TW_TZ = timezone(timedelta(hours=8))

TWD_PER_100M = 100_000_000


# ==================================================
# 取得 FinMind 資料
# ==================================================

def fetch_data(start_date: str, end_date: str) -> list[dict]:

    params = {
        "dataset": DATASET,
        "start_date": start_date,
        "end_date": end_date,
        "token": TOKEN,
    }

    for attempt in range(3):

        try:

            response = requests.get(
                API_URL,
                params=params,
                timeout=45
            )

            response.raise_for_status()

            result = response.json()

            if result.get("status") != 200:
                raise RuntimeError(
                    f"FinMind status={result.get('status')}: "
                    f"{result.get('msg')}"
                )

            data = result.get("data")

            if not isinstance(data, list):
                raise ValueError(
                    "FinMind API data is not a list"
                )

            return data

        except (
            requests.RequestException,
            ValueError
        ) as exc:

            if attempt == 2:
                raise

            print(
                f"Retry {attempt + 1}: {exc}",
                file=sys.stderr
            )

            time.sleep(2 ** attempt)

    raise RuntimeError("API retries exhausted")


# ==================================================
# 讀取既有歷史資料
# ==================================================

def load_existing() -> dict[str, dict]:

    if not OUTPUT_FILE.exists():
        return {}

    with OUTPUT_FILE.open(
        "r",
        encoding="utf-8"
    ) as f:

        saved = json.load(f)

    return {
        row["date"]: row
        for row in saved.get("data", [])
        if "date" in row
    }


# ==================================================
# 主程式
# ==================================================

def main() -> None:

    if not TOKEN:
        raise RuntimeError(
            "Missing FINMIND_TOKEN environment variable"
        )

    today = datetime.now(TW_TZ).date()

    existing = load_existing()

    # 首次抓取最近 2 年
    # 後續更新最近 7 天

    if existing:

        start = today - timedelta(days=7)

    else:

        start = today - timedelta(days=730)

    raw = fetch_data(
        start.isoformat(),
        today.isoformat()
    )

    # ==================================================
    # 篩選 MarginPurchaseMoney
    # ==================================================

    for item in raw:

        kind = item.get(
            "name",
            item.get("type")
        )

        if kind != TARGET_NAME:
            continue

        day = str(
            item.get("date", "")
        )

        if not day:
            continue

        today_balance = float(
            item["TodayBalance"]
        )

        yesterday_balance = float(
            item["YesBalance"]
        )

        # 換算成億元

        today_balance_100m = (
            today_balance / TWD_PER_100M
        )

        yesterday_balance_100m = (
            yesterday_balance / TWD_PER_100M
        )

        # 每日融資餘額變化

        daily_change_100m = (
            today_balance - yesterday_balance
        ) / TWD_PER_100M

        existing[day] = {

            "date": day,

            "today_balance": round(
                today_balance_100m,
                2
            ),

            "yesterday_balance": round(
                yesterday_balance_100m,
                2
            ),

            "daily_change": round(
                daily_change_100m,
                2
            ),
        }

    if not existing:

        raise RuntimeError(
            "No margin financing data received; "
            "output not changed"
        )

    # ==================================================
    # 日期排序
    # ==================================================

    dates = sorted(existing)

    latest_date = dates[-1]

    # ==================================================
    # 建立 JSON
    # ==================================================

    payload = {

        "source": "FinMind",

        "dataset": DATASET,

        "name": TARGET_NAME,

        "unit": "TWD 100 million (億元)",

        "updated_at_taipei": datetime.now(
            TW_TZ
        ).isoformat(timespec="seconds"),

        "data": [
            existing[day]
            for day in dates
        ],
    }

    # ==================================================
    # 安全寫入 JSON
    # ==================================================

    tmp = OUTPUT_FILE.with_suffix(
        ".json.tmp"
    )

    with tmp.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2
        )

        f.write("\n")

    tmp.replace(OUTPUT_FILE)

    # ==================================================
    # 執行結果
    # ==================================================

    latest = existing[latest_date]

    print(
        f"Saved {len(dates)} trading days; "
        f"latest: {latest_date}"
    )

    print(
        "Margin balance: "
        f"{latest['today_balance']:,.2f} 億元"
    )

    print(
        "Daily change: "
        f"{latest['daily_change']:+,.2f} 億元"
    )


if __name__ == "__main__":
    main()
