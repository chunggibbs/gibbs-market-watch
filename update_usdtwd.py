#!/usr/bin/env python3
"""Fetch Yahoo Finance USD/TWD daily closes and publish a static JSON snapshot."""
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TZ = timezone(timedelta(hours=8))
URL = 'https://query1.finance.yahoo.com/v8/finance/chart/TWD=X?range=1y&interval=1d'

def main():
    req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0 GibbsMarketWatch/1.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    result = payload['chart']['result'][0]
    stamps = result['timestamp']
    closes = result['indicators']['quote'][0]['close']
    # Exchange-rate daily close is based on the source's timestamps; preserve its date.
    by_day = {}
    for ts, value in zip(stamps, closes):
        if value is not None and value > 0:
            day = datetime.fromtimestamp(ts, timezone.utc).date().isoformat()
            by_day[day] = float(value)
    rows = sorted(by_day.items())
    if len(rows) < 60:
        raise RuntimeError(f'Insufficient FX closes for 60MA: {len(rows)}')
    closes_only = [r[1] for r in rows]
    close = closes_only[-1]
    ma20 = sum(closes_only[-20:]) / 20
    ma60 = sum(closes_only[-60:]) / 60
    if close > ma20 > ma60:
        signal = 'orange'
        label = '橘燈｜台幣偏弱・注意持股'
    elif ma60 > ma20 > close:
        signal = 'blue'
        label = '藍燈｜台幣偏強'
    else:
        signal = 'neutral'
        label = '中性｜尚未形成指定排列'
    output = {
        'symbol': 'TWD=X',
        'source': 'Yahoo Finance',
        'date': rows[-1][0],
        'updated_at_taipei': datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S %z'),
        'close': round(close, 4),
        'ma20': round(ma20, 4),
        'ma60': round(ma60, 4),
        'signal': signal,
        'label': label,
        'definition': '20MA and 60MA are simple averages of 20 and 60 valid daily closes.',
    }
    (ROOT / 'market_data.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
