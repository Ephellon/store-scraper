from __future__ import annotations
import argparse
import asyncio

from catalog.adapters.base import AdapterConfig
from catalog.adapters.steam import SteamAdapter
from catalog.adapters.psn import PSNAdapter
from catalog.adapters.xbox import XboxAdapter
from catalog.adapters.nintendo import NintendoAdapter
from catalog.runner import run_adapter

FACTORY = {
   "steam": lambda c: SteamAdapter(config=c),
   "psn": lambda c: PSNAdapter(config=c),
   "xbox": lambda c: XboxAdapter(config=c),
   "nintendo": lambda c: NintendoAdapter(config=c),
}

async def main():
   ap = argparse.ArgumentParser(description="Crawl game stores and write JSON outputs.")
   ap.add_argument("--stores", type=str, default="steam",
                   help="Comma-separated list of stores: steam,psn,xbox,nintendo")
   ap.add_argument("--out", type=str, default="./out", help="Output directory")
   ap.add_argument("--country", type=str, default="US", help="Region country code (e.g., US)")
   ap.add_argument("--locale", type=str, default="en-US", help="Locale (e.g., en-US)")
   args = ap.parse_args()

   cfg = AdapterConfig(country=args.country, locale=args.locale)
   stores = [s.strip().lower() for s in args.stores.split(",") if s.strip()]

   tasks = []
   for s in stores:
      ctor = FACTORY.get(s)
      if not ctor:
         print(f"Unknown store: {s}")
         continue
      tasks.append(run_adapter(ctor(cfg), args.out))

   if tasks:
      await asyncio.gather(*tasks)

if __name__ == "__main__":
   asyncio.run(main())
