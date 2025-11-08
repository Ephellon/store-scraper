"""
Game Catalog — unified Python package for Ephellon/game-store-catalog

This package scrapes and normalizes data from major digital game stores,
emitting JSON files compatible with the original `game-store-catalog` schema.
"""

__version__ = "0.1.0"
__author__ = "Ephellon"
__license__ = "MIT"

from catalog.models import GameRecord, LetterItem
from catalog.adapters.base import Adapter, AdapterConfig, Capabilities
from catalog.io_writer import write_catalog
from catalog.runner import run_adapter

__all__ = [
   "GameRecord",
   "LetterItem",
   "Adapter",
   "AdapterConfig",
   "Capabilities",
   "write_catalog",
   "run_adapter",
]

# Convenience: top-level async entry for single-store crawling
import asyncio

async def crawl(store_adapter: Adapter, out_dir: str) -> None:
   """Convenience alias for catalog.runner.run_adapter."""
   await run_adapter(store_adapter, out_dir)

def crawl_sync(store_adapter: Adapter, out_dir: str) -> None:
   """Synchronous alias for crawl(); wraps asyncio.run."""
   asyncio.run(run_adapter(store_adapter, out_dir))
