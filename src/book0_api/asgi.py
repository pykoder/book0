import os
from pathlib import Path

from book0_api.main import create_app
from book0_config.config import load_libraries

app = create_app(load_libraries(Path(os.environ["BOOK0_API_CONFIG"])))
