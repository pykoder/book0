import os
from pathlib import Path

from book0_api.config import load_libraries
from book0_api.main import create_app

app = create_app(load_libraries(Path(os.environ["BOOK0_API_CONFIG"])))
