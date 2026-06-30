import asyncio

from duckduckgo_search import DDGS


def search_ddg_sync(query: str, max_results: int = 3):
    """Synchronous DuckDuckGo search using duckduckgo-search package."""
    try:
        with DDGS() as ddgs:
            results = []
            for r in ddgs.text(query, max_results=max_results):
                results.append(r)
            return results
    except Exception as e:
        print(f"[DDG SEARCH ERROR] {e}")
        return []

async def search_competitors(query: str, max_results: int = 3):
    """Async wrapper for DuckDuckGo search."""
    return await asyncio.to_thread(search_ddg_sync, query, max_results)
