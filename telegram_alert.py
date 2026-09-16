#!/usr/bin/env python3
"""Отправка алертов в Telegram (запускается из GitHub Actions).

Аргумент: путь к JSON-файлу с выводом check_alerts.py.
Переменные окружения: TG_TOKEN (токен бота), TG_CHAT (chat_id).
Если алертов нет — молчит. Если нет токена — просто выходит.
"""
import json
import os
import sys
import urllib.request
import urllib.parse


STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "digest_state.json")

def digest_due():
    """Сводка — раз в час, только в торговые часы (9–16 ET, пн–пт)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("America/New_York"))
    if now.weekday() > 4 or not (9 <= now.hour <= 16):
        return False
    key = now.strftime("%Y-%m-%d %H")
    try:
        last = json.loads(open(STATE).read()).get("last")
    except Exception:
        last = None
    if last == key:
        return False
    open(STATE, "w").write(json.dumps({"last": key}))
    return True

def digest_text(s):
    vx1, vx2 = s.get("VX1") or {}, s.get("VX2") or {}
    return "\n".join([
        "📊 VIX-монитор — часовая сводка",
        "",
        f"VIX {s.get('VIX')} · UVXY {s.get('UVXY')}",
        f"VX1 {vx1.get('price')} / VX2 {vx2.get('price')} · контанго {s.get('contango_pct')}%",
        f"Декай: {'подходит ✅' if s.get('decay_ok') else 'НЕ подходит ⚠️'} · корр. {s.get('corr20_vix_spx')}",
        f"Ширина: S5TW {s.get('s5tw')}% · S5FI {s.get('s5fi')}%",
        f"Полосы BB: {s.get('bb_lower')} / {s.get('bb_sma')} / {s.get('bb_upper')}",
        "",
        "Алертов нет — триггеры не пересекались.",
    ])

def send(token, chat, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    try:
        with urllib.request.urlopen(url, data=payload, timeout=30) as r:
            ok = json.load(r).get("ok")
        print(f"telegram: отправлено, ok={ok}")
    except Exception as e:
        print(f"telegram: ошибка отправки: {e}")

def main():
    token = os.environ.get("TG_TOKEN", "").strip()
    chat = os.environ.get("TG_CHAT", "").strip()
    if not token or not chat:
        print("telegram: секреты не заданы, пропускаю")
        return

    try:
        data = json.loads(open(sys.argv[1]).read())
    except Exception as e:
        print(f"telegram: не смог прочитать вывод алертов: {e}")
        return

    triggered = data.get("triggered", [])
    if not triggered:
        if os.environ.get("TG_TEST") == "true":
            triggered = ["ТЕСТ: связь работает, алерты будут приходить сюда"]
        elif digest_due():
            send(token, chat, digest_text(data.get("status", {})))
            return
        else:
            print("telegram: алертов нет, сводка в этот час уже была")
            return

    s = data.get("status", {})
    vx1, vx2 = s.get("VX1") or {}, s.get("VX2") or {}
    lines = ["🚨 VIX-МОНИТОР — АЛЕРТ", ""]
    lines += [f"• {t}" for t in triggered]
    lines += [
        "",
        f"VIX {s.get('VIX')} · UVXY {s.get('UVXY')}",
        f"VX1 {vx1.get('price')} / VX2 {vx2.get('price')} · контанго {s.get('contango_pct')}%",
        f"Декай: {'подходит' if s.get('decay_ok') else 'НЕ подходит'} · корр. {s.get('corr20_vix_spx')}",
        f"Полосы BB: {s.get('bb_lower')} / {s.get('bb_sma')} / {s.get('bb_upper')}",
        f"Ширина: S5TW {s.get('s5tw')}% · S5FI {s.get('s5fi')}%",
    ]
    text = "\n".join(lines)

    send(token, chat, text)

if __name__ == "__main__":
    main()
