"""
catalog.adapters — store-specific adapter implementations.

Each adapter inherits from `catalog.adapters.base.Adapter`
and yields normalized `GameRecord` objects suitable for writing
to the `game-store-catalog` schema.

Available adapters:
   - SteamAdapter
   - PSNAdapter
   - XboxAdapter
   - NintendoAdapter
"""

from catalog.adapters.base import Adapter, AdapterConfig, Capabilities
from catalog.adapters.steam import SteamAdapter
from catalog.adapters.psn import PSNAdapter
from catalog.adapters.xbox import XboxAdapter
from catalog.adapters.nintendo import NintendoAdapter

__all__ = [
   "Adapter",
   "AdapterConfig",
   "Capabilities",
   "SteamAdapter",
   "PSNAdapter",
   "XboxAdapter",
   "NintendoAdapter",
]

ADAPTERS = {
   "steam": SteamAdapter,
   "psn": PSNAdapter,
   "xbox": XboxAdapter,
   "nintendo": NintendoAdapter,
}

def get_adapter(name: str):
   """
   Return an adapter class by name, or None if not found.
   Example:
       from catalog.adapters import get_adapter
       AdapterClass = get_adapter("steam")
       if AdapterClass:
           adapter = AdapterClass(config=AdapterConfig())
   """
   return ADAPTERS.get(name.lower())
