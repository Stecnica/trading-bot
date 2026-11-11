#!/usr/bin/env python3
"""Prepare a fresh checkout and open the page.

Creates the private files beside this repository, creates the MariaDB
database through the local root socket, loads the invented sample, and
serves http://127.0.0.1:8000 . Existing private files are left as they are.
"""

import os
import secrets
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_WEB = os.path.dirname(_HERE)
os.chdir(_WEB)
if _WEB not in sys.path:
    sys.path.insert(0, _WEB)

from bot_config import PRIVATE, apply_env_file, load_private_env
from bot_db import connect

DATABASE = """DB_SERVER=localhost
DB_USERNAME=trading
DB_PASSWORD={password}
DB_NAME=trading
"""

MASSIVE = """# One key from https://massive.com/stocks
# The plan on this key is the plan the cycle uses.
MASSIVE_API_KEY=paste-the-key-here
"""


def write_new(path, text):
    if path.exists():
        return False
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o600)
    return True


def read_env(path):
    found = {}
    apply_env_file(path, found)
    return found


def create_database(user, password, name):
    if not user.isidentifier() or not name.isidentifier():
        raise SystemExit("Database user and name must be plain words.")
    safe = password.replace("\\", "\\\\").replace("'", "''")
    statement = (
        f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4;"
        f"GRANT ALL PRIVILEGES ON `{name}`.* TO '{user}'@'localhost' "
        f"IDENTIFIED BY '{safe}';"
        "FLUSH PRIVILEGES;"
    )
    attempts = (
        ["mysql", "--protocol=socket", "-u", "root", "-e", statement],
        ["sudo", "-n", "mysql", "--protocol=socket", "-u", "root", "-e", statement],
    )
    errors = []
    for command in attempts:
        try:
            done = subprocess.run(command, capture_output=True, text=True)
        except FileNotFoundError:
            errors.append(command[0] + " is not installed")
            continue
        if done.returncode == 0:
            return
        errors.append((done.stderr or done.stdout or "mysql refused").strip())
    raise SystemExit("Could not create the database as local root.\n" + "\n".join(errors))


def database_ready():
    try:
        conn = connect()
    except Exception:
        return False
    conn.close()
    return True


def main():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    password_path = PRIVATE / "ui_password"
    database_path = PRIVATE / "database.env"
    massive_path = PRIVATE / "massive_api.env"
    created_password = None
    if not password_path.exists():
        created_password = secrets.token_urlsafe(12)
        password_path.write_text(created_password + "\n", encoding="utf-8")
        os.chmod(password_path, 0o600)
    if not database_path.exists():
        database_path.write_text(
            DATABASE.format(password=secrets.token_hex(12)),
            encoding="utf-8",
        )
        os.chmod(database_path, 0o600)
    write_new(massive_path, MASSIVE)

    load_private_env()
    if not database_ready():
        values = read_env(database_path)
        create_database(values["DB_USERNAME"], values["DB_PASSWORD"], values["DB_NAME"])
        # The failed attempt may have left nothing in the environment.
        load_private_env()

    if _HERE not in sys.path:
        sys.path.insert(0, _HERE)
    from sample_archive import main as load_sample

    loaded = load_sample()
    print(f"private directory: {PRIVATE}")
    if created_password:
        print(f"sign in as bot, password: {created_password}")
    else:
        print("sign in as bot, with the password already in ui_password")
    print(f"Massive key: {massive_path}")
    if loaded:
        print("sample archive was already present")
    if "--no-serve" in sys.argv:
        print("page: python -c \"import index; index.app.run(host='127.0.0.1', port=8000)\"")
        return 0
    print("Open http://127.0.0.1:8000")
    from index import app

    app.run(host="127.0.0.1", port=8000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
