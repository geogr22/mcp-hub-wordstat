from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / '.venv'


def run(cmd: list[str]) -> None:
    print('>', ' '.join(cmd))
    subprocess.check_call(cmd)


def main() -> None:
    if not VENV.exists():
        run([sys.executable, '-m', 'venv', str(VENV)])
    pip = str(VENV / 'bin' / 'pip')
    run([pip, 'install', '--upgrade', 'pip'])
    run([pip, 'install', '-r', str(ROOT / 'requirements.txt')])
    example = ROOT / '.env.example'
    env = ROOT / '.env'
    if example.exists() and not env.exists():
        shutil.copy(example, env)
        print('Создан .env. Заполните WORDSTAT_API_KEY и BASE_URL.')
    (ROOT / 'data').mkdir(exist_ok=True)
    print('\nГотово. Запуск приложения:')
    print(f"{VENV / 'bin' / 'uvicorn'} app.main:app --host 0.0.0.0 --port 8000")


if __name__ == '__main__':
    main()
