import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / 'mbank-cli.py'


def load_module():
    spec = importlib.util.spec_from_file_location('mbank_cli_under_test', MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
