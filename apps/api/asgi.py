"""Vercel entrypoint: re-export the app from the installed ``travel_aid`` package.

Vercel resolves entrypoints relative to ``apps/api``, so ``travel_aid.main:app`` would not be
found under ``src/``. Importing through this module keeps a single copy of ``travel_aid`` loaded.
"""

from travel_aid.main import app

__all__ = ["app"]
