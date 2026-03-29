# MCP Hub + Wordstat

Готовый проект для установки с GitHub. Это веб-приложение с русской админкой и MCP endpoint `/mcp`.

## Что умеет
- хранить system prompt и tool prompt;
- хранить шаблоны статей;
- включать и выключать tools;
- тестировать Wordstat tools из UI;
- отдавать Wordstat tools через MCP для ChatGPT;
- сохранять логи вызовов.

## Установка на сервере
```bash
git clone https://github.com/geogr22/mcp-hub-wordstat.git
cd mcp-hub-wordstat
python3 install.py
```

После этого:
1. откройте `.env` и заполните `WORDSTAT_API_KEY`;
2. запустите сервер:
```bash
./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Основные URL
- `/admin` — админка
- `/mcp` — MCP endpoint
- `/health` — health check

## Авторизация в админке
Используется Basic Auth:
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

## Подключение к ChatGPT
Укажите публичный HTTPS URL вида:
`https://ваш-домен/mcp`
