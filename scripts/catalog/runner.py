from __future__ import annotations
import asyncio
from typing import Iterable, AsyncIterator

from catalog.adapters.base import Adapter
from catalog.io_writer import write_catalog
from catalog.models import GameRecord

async def run_adapter(adapter: Adapter, out_dir: str) -> None:
   async with adapter as a:
      async def gather() -> AsyncIterator[GameRecord]:
         async for rec in a.iter_games():
            yield rec
      await _consume_and_write(a.store, out_dir, gather())

async def _consume_and_write(store: str, out_dir: str, rows: AsyncIterator[GameRecord]) -> None:
   buf = []
   async for r in rows:
      buf.append(r)
   write_catalog(out_dir, store, buf)
