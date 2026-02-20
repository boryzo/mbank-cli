import importlib.util
import os
import uuid
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / 'mbank_http_wrapper.py'


def load_wrapper(env=None):
    env = {} if env is None else dict(env)
    old = {}
    keys = set(env.keys())
    for k in keys:
        old[k] = os.environ.get(k)
    try:
        for k, v in env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        mod_name = f'mbank_http_wrapper_under_test_{uuid.uuid4().hex}'
        spec = importlib.util.spec_from_file_location(mod_name, MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for k in keys:
            if old[k] is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old[k]
