from __future__ import annotations

import base64
import json
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.wordstat import WordstatClient

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / 'data' / 'app.db'
DB_PATH.parent.mkdir(exist_ok=True)

APP_NAME = os.getenv('APP_NAME', 'MCP Hub + Wordstat')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:8000')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'change_me')
WORDSTAT_API_KEY = os.getenv('WORDSTAT_API_KEY', '')
WORDSTAT_API_BASE_URL = os.getenv('WORDSTAT_API_BASE_URL', 'https://searchapi.api.cloud.yandex.net/v2/wordstat')

app = FastAPI(title=APP_NAME)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def tool_defaults() -> dict[str, dict[str, Any]]:
    return {
        'wordstat_get_top': {
            'type': 'object',
            'properties': {
                'phrase': {'type': 'string'},
                'region': {'type': 'integer'},
                'limit': {'type': 'integer', 'default': 10},
            },
            'required': ['phrase'],
        },
        'wordstat_get_dynamics': {
            'type': 'object',
            'properties': {'phrase': {'type': 'string'}, 'region': {'type': 'integer'}},
            'required': ['phrase'],
        },
        'wordstat_get_regions': {'type': 'object', 'properties': {}},
        'wordstat_get_regions_distribution': {
            'type': 'object',
            'properties': {'phrase': {'type': 'string'}},
            'required': ['phrase'],
        },
        'prompt_render_preview': {
            'type': 'object',
            'properties': {
                'title': {'type': 'string'},
                'phrase': {'type': 'string'},
                'tool_summary': {'type': 'string'},
            },
            'required': ['title'],
        },
    }


def init_db() -> None:
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS prompts (
            name TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            content TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS templates (
            name TEXT PRIMARY KEY,
            description TEXT,
            content TEXT NOT NULL,
            active INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tools (
            name TEXT PRIMARY KEY,
            enabled INTEGER DEFAULT 1,
            schema_json TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            tool_name TEXT,
            request_json TEXT,
            response_json TEXT,
            status TEXT,
            error_message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    defaults = [
        ('system_main', 'system', 'Ты SEO-редактор. Пиши только на основе подтверждённых данных Wordstat.'),
        ('tool_wordstat', 'tool', 'Используй Wordstat как подтверждение спроса, а не как догадку.'),
    ]
    for name, kind, content in defaults:
        conn.execute(
            'INSERT OR IGNORE INTO prompts(name, kind, content) VALUES (?, ?, ?)',
            (name, kind, content),
        )
    conn.execute(
        'INSERT OR IGNORE INTO templates(name, description, content, active) VALUES (?, ?, ?, ?)',
        (
            'Базовая SEO-статья',
            'Стартовый шаблон',
            'Заголовок\nВступление\nПодтверждённые запросы\nОсновной текст\nFAQ\nВывод',
            1,
        ),
    )
    for name, schema in tool_defaults().items():
        conn.execute(
            'INSERT OR IGNORE INTO tools(name, enabled, schema_json) VALUES (?, 1, ?)',
            (name, json.dumps(schema, ensure_ascii=False)),
        )
    conn.commit()
    conn.close()


def is_authorized(request: Request) -> bool:
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Basic '):
        return False
    try:
        raw = base64.b64decode(auth.split(' ', 1)[1]).decode()
        username, password = raw.split(':', 1)
        return secrets.compare_digest(username, ADMIN_USERNAME) and secrets.compare_digest(password, ADMIN_PASSWORD)
    except Exception:
        return False


def require_admin(request: Request) -> None:
    if not is_authorized(request):
        raise HTTPException(status_code=401, detail='Требуется авторизация', headers={'WWW-Authenticate': 'Basic'})


def html_page(title: str, body: str) -> HTMLResponse:
    html = f"""<!doctype html>
    <html lang='ru'>
    <head>
      <meta charset='utf-8'>
      <title>{title}</title>
      <style>
        body {{ font-family: Arial, sans-serif; max-width: 1100px; margin: 40px auto; padding: 0 16px; }}
        textarea {{ width: 100%; min-height: 180px; }}
        input[type=text], input[type=password] {{ width: 100%; padding: 8px; box-sizing: border-box; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td, th {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
        .card {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin: 16px 0; }}
        nav a {{ margin-right: 14px; }}
        pre {{ white-space: pre-wrap; word-break: break-word; }}
      </style>
    </head>
    <body>
      <h1>{APP_NAME}</h1>
      <nav>
        <a href='/admin'>Главная</a>
        <a href='/admin/prompts'>Промпты</a>
        <a href='/admin/templates'>Шаблоны</a>
        <a href='/admin/tools'>Тулы</a>
        <a href='/admin/settings'>Настройки</a>
        <a href='/admin/logs'>Логи</a>
      </nav>
      {body}
    </body>
    </html>"""
    return HTMLResponse(html)


def log_call(source: str, tool_name: str, request_data: Any, response_data: Any = None, status: str = 'success', error_message: str = '') -> None:
    conn = db()
    conn.execute(
        'INSERT INTO logs(source, tool_name, request_json, response_json, status, error_message) VALUES (?, ?, ?, ?, ?, ?)',
        (
            source,
            tool_name,
            json.dumps(request_data, ensure_ascii=False),
            json.dumps(response_data, ensure_ascii=False) if response_data is not None else '',
            status,
            error_message,
        ),
    )
    conn.commit()
    conn.close()


def get_setting(key: str, default: str = '') -> str:
    conn = db()
    row = conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    conn.close()
    return row['value'] if row else default


def set_setting(key: str, value: str) -> None:
    conn = db()
    conn.execute(
        'INSERT INTO settings(key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP',
        (key, value),
    )
    conn.commit()
    conn.close()


async def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    api_key = get_setting('wordstat_api_key', WORDSTAT_API_KEY)
    client = WordstatClient(api_key=api_key, base_url=WORDSTAT_API_BASE_URL)
    if name == 'wordstat_get_top':
        return await client.get_top(arguments['phrase'], arguments.get('region'), int(arguments.get('limit', 10)))
    if name == 'wordstat_get_dynamics':
        return await client.get_dynamics(arguments['phrase'], arguments.get('region'))
    if name == 'wordstat_get_regions':
        return await client.get_regions()
    if name == 'wordstat_get_regions_distribution':
        return await client.get_regions_distribution(arguments['phrase'])
    if name == 'prompt_render_preview':
        conn = db()
        system_prompt = conn.execute('SELECT content FROM prompts WHERE name=?', ('system_main',)).fetchone()['content']
        tool_prompt = conn.execute('SELECT content FROM prompts WHERE name=?', ('tool_wordstat',)).fetchone()['content']
        template = conn.execute('SELECT content FROM templates WHERE active=1 ORDER BY updated_at DESC LIMIT 1').fetchone()['content']
        conn.close()
        return {
            'system_prompt': system_prompt,
            'tool_prompt': tool_prompt,
            'template': template,
            'title': arguments['title'],
            'phrase': arguments.get('phrase', ''),
            'tool_summary': arguments.get('tool_summary', ''),
        }
    raise HTTPException(status_code=404, detail=f'Неизвестный tool: {name}')


@app.on_event('startup')
def startup() -> None:
    init_db()


@app.get('/')
def root() -> dict[str, str]:
    return {
        'name': APP_NAME,
        'admin_url': f'{BASE_URL}/admin',
        'mcp_url': f'{BASE_URL}/mcp',
        'health_url': f'{BASE_URL}/health',
    }


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'healthy', 'service': APP_NAME}


@app.get('/admin', response_class=HTMLResponse)
def admin_dashboard(request: Request):
    require_admin(request)
    conn = db()
    prompt_count = conn.execute('SELECT COUNT(*) c FROM prompts').fetchone()['c']
    template_count = conn.execute('SELECT COUNT(*) c FROM templates').fetchone()['c']
    tool_count = conn.execute('SELECT COUNT(*) c FROM tools WHERE enabled=1').fetchone()['c']
    logs = conn.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 10').fetchall()
    conn.close()
    rows = ''.join(
        f"<tr><td>{r['created_at']}</td><td>{r['source']}</td><td>{r['tool_name']}</td><td>{r['status']}</td><td>{r['error_message']}</td></tr>"
        for r in logs
    )
    body = f"<div class='card'><b>Промпты:</b> {prompt_count}<br><b>Шаблоны:</b> {template_count}<br><b>Активные тулы:</b> {tool_count}<br><b>MCP URL:</b> <code>{BASE_URL}/mcp</code></div><div class='card'><h3>Последние вызовы</h3><table><tr><th>Когда</th><th>Источник</th><th>Tool</th><th>Статус</th><th>Ошибка</th></tr>{rows}</table></div>"
    return html_page('Панель управления', body)


@app.get('/admin/prompts', response_class=HTMLResponse)
def prompts_page(request: Request):
    require_admin(request)
    conn = db()
    rows = conn.execute('SELECT * FROM prompts ORDER BY kind, name').fetchall()
    conn.close()
    forms = ''.join(
        f"<div class='card'><form method='post' action='/admin/prompts/save'><input type='hidden' name='name' value='{r['name']}'><input type='hidden' name='kind' value='{r['kind']}'><h3>{r['name']}</h3><p>Тип: {r['kind']}</p><textarea name='content'>{r['content']}</textarea><p><button type='submit'>Сохранить</button></p></form></div>"
        for r in rows
    )
    return html_page('Промпты', forms)


@app.post('/admin/prompts/save')
def save_prompt(request: Request, name: str = Form(...), kind: str = Form(...), content: str = Form(...)):
    require_admin(request)
    conn = db()
    conn.execute(
        'INSERT INTO prompts(name, kind, content, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP) ON CONFLICT(name) DO UPDATE SET content=excluded.content, updated_at=CURRENT_TIMESTAMP',
        (name, kind, content),
    )
    conn.commit()
    conn.close()
    return RedirectResponse('/admin/prompts', status_code=303)


@app.get('/admin/templates', response_class=HTMLResponse)
def templates_page(request: Request):
    require_admin(request)
    conn = db()
    rows = conn.execute('SELECT * FROM templates ORDER BY updated_at DESC').fetchall()
    conn.close()
    create = "<div class='card'><form method='post' action='/admin/templates/save'><h3>Новый шаблон</h3><p><input type='text' name='name' placeholder='Название'></p><p><input type='text' name='description' placeholder='Описание'></p><textarea name='content'></textarea><p><label><input type='checkbox' name='active' value='1'> Активный</label></p><button type='submit'>Создать</button></form></div>"
    cards = ''.join(
        f"<div class='card'><form method='post' action='/admin/templates/save'><h3>{r['name']}</h3><input type='hidden' name='original_name' value='{r['name']}'><p><input type='text' name='name' value='{r['name']}'></p><p><input type='text' name='description' value='{r['description'] or ''}'></p><textarea name='content'>{r['content']}</textarea><p><label><input type='checkbox' name='active' value='1' {'checked' if r['active'] else ''}> Активный</label></p><button type='submit'>Сохранить</button></form></div>"
        for r in rows
    )
    return html_page('Шаблоны', create + cards)


@app.post('/admin/templates/save')
def save_template(request: Request, name: str = Form(...), description: str = Form(''), content: str = Form(...), active: str | None = Form(None), original_name: str = Form('')):
    require_admin(request)
    conn = db()
    if active:
        conn.execute('UPDATE templates SET active=0')
    key = original_name or name
    conn.execute(
        'INSERT OR REPLACE INTO templates(name, description, content, active, updated_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)',
        (name if original_name else key, description, content, 1 if active else 0),
    )
    if original_name and original_name != name:
        conn.execute('DELETE FROM templates WHERE name=?', (original_name,))
    conn.commit()
    conn.close()
    return RedirectResponse('/admin/templates', status_code=303)


@app.get('/admin/tools', response_class=HTMLResponse)
def tools_page(request: Request):
    require_admin(request)
    conn = db()
    rows = conn.execute('SELECT * FROM tools ORDER BY name').fetchall()
    conn.close()
    cards = []
    for r in rows:
        cards.append(
            f"<div class='card'><form method='post' action='/admin/tools/save'><h3>{r['name']}</h3><input type='hidden' name='name' value='{r['name']}'><p><label><input type='checkbox' name='enabled' value='1' {'checked' if r['enabled'] else ''}> Включён</label></p><textarea name='schema_json'>{r['schema_json']}</textarea><p><button type='submit'>Сохранить</button></p></form><form method='post' action='/admin/tools/test'><input type='hidden' name='name' value='{r['name']}'><p><input type='text' name='payload' placeholder='{{\"phrase\":\"походы в архызе\"}}'></p><button type='submit'>Тестировать</button></form></div>"
        )
    return html_page('Тулы', ''.join(cards))


@app.post('/admin/tools/save')
def save_tool(request: Request, name: str = Form(...), schema_json: str = Form(...), enabled: str | None = Form(None)):
    require_admin(request)
    conn = db()
    conn.execute('UPDATE tools SET enabled=?, schema_json=?, updated_at=CURRENT_TIMESTAMP WHERE name=?', (1 if enabled else 0, schema_json, name))
    conn.commit()
    conn.close()
    return RedirectResponse('/admin/tools', status_code=303)


@app.post('/admin/tools/test', response_class=HTMLResponse)
def test_tool(request: Request, name: str = Form(...), payload: str = Form('{}')):
    require_admin(request)
    try:
        arguments = json.loads(payload or '{}')
    except json.JSONDecodeError as exc:
        return html_page('Ошибка теста', f"<div class='card'>Некорректный JSON: {exc}</div>")
    import asyncio
    try:
        result = asyncio.run(call_tool(name, arguments))
        log_call('ui', name, arguments, result)
        return html_page('Результат теста', f"<div class='card'><pre>{json.dumps(result, ensure_ascii=False, indent=2)}</pre></div>")
    except Exception as exc:
        log_call('ui', name, arguments, None, 'error', str(exc))
        return html_page('Ошибка теста', f"<div class='card'>{exc}</div>")


@app.get('/admin/settings', response_class=HTMLResponse)
def settings_page(request: Request):
    require_admin(request)
    current_key = '*** скрыт ***' if get_setting('wordstat_api_key', WORDSTAT_API_KEY) else ''
    body = f"<div class='card'><form method='post' action='/admin/settings/save'><h3>Настройки</h3><p>Wordstat API key</p><input type='password' name='wordstat_api_key' value='{current_key}'><p>Публичный base URL</p><input type='text' name='base_url' value='{get_setting('base_url', BASE_URL)}'><p><button type='submit'>Сохранить</button></p></form></div>"
    return html_page('Настройки', body)


@app.post('/admin/settings/save')
def save_settings(request: Request, wordstat_api_key: str = Form(''), base_url: str = Form('')):
    require_admin(request)
    if wordstat_api_key and wordstat_api_key != '*** скрыт ***':
        set_setting('wordstat_api_key', wordstat_api_key)
    if base_url:
        set_setting('base_url', base_url)
    return RedirectResponse('/admin/settings', status_code=303)


@app.get('/admin/logs', response_class=HTMLResponse)
def logs_page(request: Request):
    require_admin(request)
    conn = db()
    rows = conn.execute('SELECT * FROM logs ORDER BY id DESC LIMIT 100').fetchall()
    conn.close()
    body = "<div class='card'><table><tr><th>ID</th><th>Когда</th><th>Источник</th><th>Tool</th><th>Статус</th><th>Ошибка</th></tr>" + ''.join(
        f"<tr><td>{r['id']}</td><td>{r['created_at']}</td><td>{r['source']}</td><td>{r['tool_name']}</td><td>{r['status']}</td><td>{r['error_message']}</td></tr>"
        for r in rows
    ) + '</table></div>'
    return html_page('Логи', body)


@app.post('/mcp')
async def mcp_post(request: Request):
    payload = await request.json()
    method = payload.get('method')
    req_id = payload.get('id')
    if method == 'initialize':
        return JSONResponse({'jsonrpc': '2.0', 'id': req_id, 'result': {'protocolVersion': '2024-11-05', 'capabilities': {'tools': {}}, 'serverInfo': {'name': APP_NAME, 'version': '1.0.0'}}})
    if method == 'tools/list':
        conn = db()
        rows = conn.execute('SELECT * FROM tools WHERE enabled=1 ORDER BY name').fetchall()
        conn.close()
        tools = [{'name': r['name'], 'description': r['name'], 'inputSchema': json.loads(r['schema_json'])} for r in rows]
        return JSONResponse({'jsonrpc': '2.0', 'id': req_id, 'result': {'tools': tools}})
    if method == 'tools/call':
        params = payload.get('params', {})
        name = params.get('name')
        arguments = params.get('arguments', {})
        try:
            result = await call_tool(name, arguments)
            log_call('mcp', name, arguments, result)
            return JSONResponse({'jsonrpc': '2.0', 'id': req_id, 'result': {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}]}})
        except Exception as exc:
            log_call('mcp', name, arguments, None, 'error', str(exc))
            return JSONResponse({'jsonrpc': '2.0', 'id': req_id, 'error': {'code': -32000, 'message': str(exc)}})
    return JSONResponse({'jsonrpc': '2.0', 'id': req_id, 'error': {'code': -32601, 'message': 'Method not found'}})
