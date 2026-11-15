import os
import tempfile
from pathlib import Path

import bot_config


def test_private_files_win_over_a_stale_server_environment():
    saved_private, saved_env = bot_config.PRIVATE, dict(os.environ)
    with tempfile.TemporaryDirectory() as folder:
        try:
            bot_config.PRIVATE = Path(folder)
            (Path(folder) / "bot.env").write_text("export DB_PASSWORD=new\nexport DB_PASSWORD_web5=new\n")
            os.environ["DB_PASSWORD_web5"] = "stale"
            bot_config.load_private_env()
            assert bot_config.env_db("DB_PASSWORD") == "new"
        finally:
            bot_config.PRIVATE = saved_private
            os.environ.clear()
            os.environ.update(saved_env)
