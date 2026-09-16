#!/usr/bin/env python3
"""Проверка алерт-триггеров по правилам стратегии.

Печатает JSON: {"triggered": [строки-алерты], "status": {...}}.
Повторы подавляются: каждый алерт срабатывает один раз в день
(состояние в alerts_state.json).

Запуск: python3 check_alerts.py
"""
import json
import math
import urllib.request
from datetime import datetime, date
from pathlib import Path

HERE = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

def chart(symbol, rng="5d", interval="1d"):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol)}?range={rng}&interval={interval}")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["chart"]["result"][0]

def closes_of(d):
    return [c for c in d["indicators"]["quote"][0].get("close", []) if c is not None]

def pairs_by_date(d):
    ts = d.get("timestamp", [])
    cs = d["indicators"]["quote"][0].get("close", [])
    return {datetime.utcfromtimestamp(t).strftime("%Y-%m-%d"): c
            for t, c in zip(ts, cs) if c is not None}

def corr20(vix_d, spx_d):
    """Корреляция дневных изменений VIX и S&P за 20 сессий."""
    v, s = pairs_by_date(vix_d), pairs_by_date(spx_d)
    days = sorted(set(v) & set(s))[-21:]
    if len(days) < 21:
        return None
    rv = [v[days[i]] / v[days[i - 1]] - 1 for i in range(1, 21)]
    rs = [s[days[i]] / s[days[i - 1]] - 1 for i in range(1, 21)]
    mv, ms = sum(rv) / 20, sum(rs) / 20
    num = sum((a - mv) * (b - ms) for a, b in zip(rv, rs))
    den = math.sqrt(sum((a - mv) ** 2 for a in rv) * sum((b - ms) ** 2 for b in rs))
    return num / den if den else None

def main():
    vix_d = chart("^VIX", "3mo")
    vix_hist = closes_of(vix_d)
    vix = vix_d["meta"]["regularMarketPrice"]
    vix_prev = vix_hist[-2] if len(vix_hist) >= 2 else None

    v3_d = chart("^VIX3M", "5d")
    v3_hist = closes_of(v3_d)
    v3 = v3_d["meta"]["regularMarketPrice"]
    v3_prev = v3_hist[-2] if len(v3_hist) >= 2 else None

    uv_d = chart("UVXY", "5d")
    uv_hist = closes_of(uv_d)
    uv = uv_d["meta"]["regularMarketPrice"]
    uv_prev = uv_hist[-2] if len(uv_hist) >= 2 else None

    spx_d = chart("^GSPC", "3mo")
    corr = corr20(vix_d, spx_d)

    import build_dashboard
    vx = build_dashboard.cboe_vx_front2()  # [VX1, VX2] или None

    # Bollinger (20, 2) по дневным закрытиям VIX (текущая цена как последняя точка)
    series = vix_hist[:-1] + [vix]
    win = series[-20:]
    sma = sum(win) / len(win)
    sd = math.sqrt(sum((x - sma) ** 2 for x in win) / len(win))
    upper, lower = sma + 2 * sd, sma - 2 * sd

    events = json.loads((HERE / "events.json").read_text()) if (HERE / "events.json").exists() else []
    if not events:
        # синхронизировано с build_dashboard.EVENTS
        import build_dashboard
        events = build_dashboard.EVENTS
    today = date.today()
    upcoming = []
    for e in events:
        dd = (date.fromisoformat(e["date"]) - today).days
        if 0 <= dd <= 1:
            upcoming.append((dd, e["label"]))

    triggered = []
    # --- декай по реальным VX1/VX2 (fallback — индексы VIX/VIX3M)
    if vx:
        vx1, vx2 = vx[0], vx[1]
        cont_now = (vx2["price"] / vx1["price"] - 1) * 100
        cont_prev = ((vx2["prevClose"] / vx1["prevClose"] - 1) * 100
                     if vx1.get("prevClose") and vx2.get("prevClose") else None)
        if cont_now <= 0 and (cont_prev is None or cont_prev > 0):
            triggered.append(f"ДЕКАЙ ОТРИЦАТЕЛЬНЫЙ: VX1/VX2 в бэквордации ({cont_now:+.1f}%) — шорт-вол не подходит")
        if 0 < cont_now < 5 and (cont_prev is None or cont_prev >= 5):
            triggered.append(f"Декай упал ниже лимита 5%: контанго VX1→VX2 всего {cont_now:+.1f}% — новые входы не подходят")
    elif v3 is not None:
        back_now = vix > v3
        back_prev = (vix_prev is not None and v3_prev is not None and vix_prev > v3_prev)
        if back_now and not back_prev:
            triggered.append(f"Кривая перешла в БЭКВОРДАЦИЮ (VIX {vix:.2f} > VIX3M {v3:.2f}) — ролл против шорт-вол")

    # --- ширина рынка S5TW: перепроданность / перекупленность
    import build_dashboard
    try:
        br = build_dashboard.breadth_sp500()
    except Exception:
        br = None
    if br:
        s5tw = br["s5tw"]
        if s5tw < 20:
            triggered.append(f"Ширина рынка: S5TW {s5tw}% — ниже 20%, зона перепроданности (исторически близко к развороту)")
        if s5tw > 80:
            triggered.append(f"Ширина рынка: S5TW {s5tw}% — выше 80%, зона перекупленности")

    # подавление повторов: один и тот же алерт не чаще раза в день
    state_f = HERE / "alerts_state.json"
    state = json.loads(state_f.read_text()) if state_f.exists() else {}
    tkey = today.isoformat()
    sent = set(state.get(tkey, []))
    fresh = [t for t in triggered if t.split("—")[0].strip() not in sent]
    state = {tkey: sorted(sent | {t.split("—")[0].strip() for t in triggered})}
    state_f.write_text(json.dumps(state, ensure_ascii=False, indent=1))

    print(json.dumps({
        "triggered": fresh,
        "suppressed_repeats": len(triggered) - len(fresh),
        "status": {
            "VIX": round(vix, 2), "VIX3M": round(v3, 2) if v3 else None,
            "UVXY": round(uv, 2),
            "VX1": {"symbol": vx[0]["sym"], "price": vx[0]["price"], "expiry": vx[0]["expiry"]} if vx else None,
            "VX2": {"symbol": vx[1]["sym"], "price": vx[1]["price"], "expiry": vx[1]["expiry"]} if vx else None,
            "contango_pct": round((vx[1]["price"] / vx[0]["price"] - 1) * 100, 2) if vx else None,
            "decay_ok": bool(vx and (vx[1]["price"] / vx[0]["price"] - 1) * 100 >= 5),
            "corr20_vix_spx": round(corr, 2) if corr is not None else None,
            "s5tw": br["s5tw"] if br else None,
            "s5fi": br["s5fi"] if br else None,
            "bb_lower": round(lower, 2), "bb_sma": round(sma, 2), "bb_upper": round(upper, 2),
            "structure": ("backwardation" if vx[1]["price"] < vx[0]["price"] else "contango") if vx
                         else ("backwardation" if (v3 and vix > v3) else "contango"),
        },
    }, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
