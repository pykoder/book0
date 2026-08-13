import os
from pathlib import Path

from book0_api.cli import CONFIG_ENV_VAR
from book0_api.main import create_app
from book0_config.config import load_libraries

config = load_libraries(Path(os.environ[CONFIG_ENV_VAR]))
app = create_app(config.libraries, config.default_tag)
