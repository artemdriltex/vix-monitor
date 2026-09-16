# VIX Монитор — автономная версия (GitHub Pages + Actions)

Дашборд волатильности: VIX/полосы Боллинджера, VX-фьючерсы и декай, ширина рынка
(S5TW/S5FI), SPY с EMA 10/20/50, календарь событий. Пересобирается автоматически
каждые 30 минут в торговые часы (GitHub Actions), алерты уходят в Telegram.

## Как это работает
- `.github/workflows/update.yml` — расписание: каждые 30 мин, пн–пт, 13:00–20:30 UTC.
- `check_alerts.py` — проверяет триггеры стратегии (полосы BB, декай VX1→VX2,
  корреляция, UVXY ±8%, события FOMC/CPI/экспирации). Повторы подавляются день.
- `build_dashboard.py` — собирает `dashboard.html` (данные Yahoo + CBOE).
- `telegram_alert.py` — шлёт сработавшие алерты в Telegram (секреты
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
- Страница публикуется в `docs/index.html` → GitHub Pages.

## Секреты (Settings → Secrets and variables → Actions)
- `TELEGRAM_BOT_TOKEN` — токен бота от @BotFather
- `TELEGRAM_CHAT_ID` — твой числовой id (узнать: написать @userinfobot)

## Включение Pages
Settings → Pages → Source: Deploy from a branch → Branch: `main`, папка `/docs`.

## Ручной запуск
Вкладка Actions → update-dashboard → Run workflow.
