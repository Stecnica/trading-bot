import sys
import os

here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)
if here not in sys.path:
    sys.path.insert(0, here)

import bot_config

# Writable matplotlib cache (avoids /var/www/.../.config mkdir failures and cold-start stalls).
os.environ.setdefault("MPLCONFIGDIR", str(bot_config.MPLCONFIG))
bot_config.MPLCONFIG.mkdir(parents=True, exist_ok=True)

bot_config.install_import_path()

try:
    import index
    application = index.app
except ImportError as e:
    print(f"ImportError: {e}", file=sys.stderr)
    raise
# reload-stamp 1794734033.4372683
