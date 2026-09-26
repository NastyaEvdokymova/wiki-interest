#!/usr/bin/env python3
"""Single entry point without installing the package: python3 scripts/wikitrends.py ..."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from wikitrends.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
