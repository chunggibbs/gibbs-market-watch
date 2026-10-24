"""Gibbs Market Watch: TX 前十大交易人所有到期月份淨未沖銷部位。"""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

API = 'https://api.finmindtrade.com/api/v4/data'
OUTPUT = Path(__file__).resolve().parent / 'large_traders_data.json'
TZ_TAIPEI = timezone(timedelta(hours=8))


def main():
    token = os.getenv('FINMIND_TOKEN') or os.getenv('FINMIND_API_TOKEN')
    if not token:
        raise RuntimeError('缺少 FINMIND_TOKEN GitHub Secret')
    today = datetime.now(TZ_TAIPEI).date()
    params = {
        'dataset': 'TaiwanFuturesOpenInterestLargeTraders',
        'data_id': 'TX',
        'start_date': (today - timedelta(days=240)).isoformat(),
        'end_date': (today + timedelta(days=1)).isoformat(),
    }
    response = requests.get(API, params=params, headers={'Authorization': f'Bearer {token}'}, timeout=90)
    response.raise_for_status()
    payload = response.json()
    if payload.get('status') != 200:
        raise RuntimeError(f"FinMind 回傳錯誤：{payload.get('msg', payload.get('status'))}")
    records = {}
    for row in payload.get('data', []):
        if str(row.get('futures_id', '')).upper() != 'TX':
            continue
        if str(row.get('contract_type', '')).lower() != 'all':
            continue
        day = str(row.get('date', ''))
        if not day:
            continue
        buy = int(row['buy_top10_trader_open_interest'])
        sell = int(row['sell_top10_trader_open_interest'])
        if day in records:
            raise RuntimeError(f'{day} TX/all 出現重複資料，停止避免重複計算')
        records[day] = {'date': day, 'buy_top10': buy, 'sell_top10': sell, 'net': buy - sell}
    data = [records[day] for day in sorted(records)]
    if not data:
        raise RuntimeError('查無 TX / contract_type=all 資料；請確認 FinMind 權限與 API 回傳內容')
    latest = data[-1]
    direction = (latest['net'] > 0) - (latest['net'] < 0)
    streak = 0
    if direction:
        for row in reversed(data):
            if ((row['net'] > 0) - (row['net'] < 0)) != direction:
                break
            streak += 1
    signal = 'blue' if streak >= 3 and direction > 0 else 'orange' if streak >= 3 and direction < 0 else 'neutral'
    result = {
        'source': 'FinMind',
        'dataset': 'TaiwanFuturesOpenInterestLargeTraders',
        'futures_id': 'TX',
        'contract_type': 'all',
        'description': '臺股期貨前十大交易人（全部交易人、所有到期月份合計）',
        'updated_at_taipei': datetime.now(TZ_TAIPEI).isoformat(timespec='seconds'),
        'latest_date': latest['date'],
        'latest_buy_top10': latest['buy_top10'],
        'latest_sell_top10': latest['sell_top10'],
        'latest_net': latest['net'],
        'streak_days': streak,
        'streak_is_at_least': streak == len(data) and streak > 0,
        'signal': signal,
        'data': data,
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"已更新 {OUTPUT.name}：{latest['date']}，多方 {latest['buy_top10']:,}，空方 {latest['sell_top10']:,}，淨部位 {latest['net']:+,}，連續 {streak} 日，{signal}")


if __name__ == '__main__':
    main()
