import sys
import os

# Imposta la directory di lavoro
os.chdir('/var/www/clients/client0/web5/web')

# Aggiungi la directory corrente a sys.path
sys.path.insert(0, '.')

path_to_libs = '/var/www/clients/client0/web5/home/default_botmanager/.local/lib/python3.10/site-packages'
if path_to_libs not in sys.path:
    sys.path.insert(0, path_to_libs)

try:
    import index
    application = index.app
except ImportError as e:
    print(f"ImportError: {e}", file=sys.stderr)
    raise