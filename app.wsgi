import sys
import os

here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)
if here not in sys.path:
    sys.path.insert(0, here)

import bot_config

bot_config.install_import_path()

try:
    import index
    application = index.app
except ImportError as e:
    print(f"ImportError: {e}", file=sys.stderr)
    raise