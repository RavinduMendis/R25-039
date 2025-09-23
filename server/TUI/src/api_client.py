import time
from typing import Any
import aiohttp
from .config import API_URL, DATA_CACHE, CACHE_LIFETIME

async def fetch_data(session: aiohttp.ClientSession, endpoint: str) -> Any:
    cache_key = endpoint
    cached_data = DATA_CACHE.get(cache_key)
    if cached_data and (time.time() - cached_data['timestamp']) < CACHE_LIFETIME:
        return cached_data['data']

    try:
        async with session.get(f"{API_URL}{endpoint}") as response:
            response.raise_for_status()
            data = await response.json()
            result = data.get("data", data)
            DATA_CACHE[cache_key] = {'data': result, 'timestamp': time.time()}
            return result
    except aiohttp.ClientError as e:
        return {"error": f"Failed to fetch {endpoint}: {e}"}