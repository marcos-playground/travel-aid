"""Export the OpenAPI schema used to generate the TypeScript API client."""

import json
import sys
from pathlib import Path

from travel_aid.main import app


def main() -> None:
    schema = json.dumps(app.openapi(), indent=2) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(schema)
    else:
        sys.stdout.write(schema)
