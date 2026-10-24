import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

API = 'https://api.finmindtrade.com/api/v4/data'
TZ = timezone(timedelta(hours=8))
TODAY = datetime.now(TZ).date()
START = TODAY - timedelta(days=180)
OUTPUT = Path(__file__).resolve().parent / 'futures_data.json'


def get_futures(code):
    token = os.environ.get('FINMIND_TOKEN', '').strip()
    if not token:
        raise RuntimeError('缺少 FINMIND_TOKEN GitHub Secret')
    response = requests.get(
        API,
        params={'dataset': 'TaiwanFuturesInstitutionalInvestors', 'data_id': code,
                'start_date': START.isoformat(), 'end_date': TODAY.isoformat()},
        headers={'Authorization': f'Bearer {token}'}, timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get('status') != 200:
        raise RuntimeError(f'FinMind {code} API 回傳異常：{payload.get("msg", payload)}')
    rows = payload.get('data')
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f'{code} 沒有資料')
    return rows


def foreign_only(rows, code):
    result = {}
    for row in rows:
        identity = str(row.get('institutional_investors', '')).strip()
        if identity not in ('外資', 'Foreign_Investor'):
            continue
        date = row.get('date')
        if not isinstance(date, str):
            continue
        if date in result:
            raise RuntimeError(f'{code} {date} 外資資料重複，拒絕覆寫')
        long_oi = int(row['long_open_interest_balance_volume'])
        short_oi = int(row['short_open_interest_balance_volume'])
        result[date] = {'long': long_oi, 'short': short_oi, 'net': long_oi - short_oi}
    if not result:
        names = sorted({str(r.get('institutional_investors')) for r in rows})
        raise RuntimeError(f'{code} 找不到外資欄位，API 身分別：{names}')
    return result


def main():
    tx = foreign_only(get_futures('TX'), 'TX')
    mtx = foreign_only(get_futures('MTX'), 'MTX')
    dates = sorted(set(tx) & set(mtx))
    if not dates:
        raise RuntimeError('TX 與 MTX 沒有共同日期')
    if max(tx) != dates[-1] or max(mtx) != dates[-1]:
        raise RuntimeError('TX、MTX 最新日期不一致，不更新資料')
    data = []
    for date in dates:
        net_x4 = tx[date]['net'] * 4 + mtx[date]['net']
        data.append({'date': date, 'tx_net': tx[date]['net'],
                     'mtx_net': mtx[date]['net'], 'net_tx_equivalent': net_x4 / 4})
    latest = data[-1]
    direction = 1 if latest['net_tx_equivalent'] > 0 else -1 if latest['net_tx_equivalent'] < 0 else 0
    streak = 0
    if direction:
        for row in reversed(data):
            value = row['net_tx_equivalent']
            if value == 0 or (value > 0) != (direction > 0):
                break
            streak += 1
    signal = 'blue' if streak >= 3 and direction > 0 else 'orange' if streak >= 3 and direction < 0 else 'neutral'
    output = {'source': 'FinMind', 'dataset': 'TaiwanFuturesInstitutionalInvestors',
              'description': '外資 TX + MTX/4 淨未平倉（大臺指等值口數）',
              'updated_at_taipei': datetime.now(TZ).isoformat(timespec='seconds'),
              'latest_date': latest['date'], 'latest_net_tx_equivalent': latest['net_tx_equivalent'],
              'streak_days': streak, 'signal': signal, 'data': data}
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'更新 {OUTPUT.name}：{latest["date"]} {latest["net_tx_equivalent"]:+,.2f} 口；{signal} {streak} 天')


if __name__ == '__main__':
    main()
