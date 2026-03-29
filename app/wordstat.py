from __future__ import annotations

import httpx


class WordstatClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')

    async def _post(self, path: str, payload: dict) -> dict:
        headers = {
            'Authorization': f'Api-key {self.api_key}',
            'Content-Type': 'application/json',
        }
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}/{path.lstrip('/')}",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def get_top(self, phrase: str, region: int | None = None, limit: int = 10) -> dict:
        payload = {'phrase': phrase, 'pageSize': limit}
        if region is not None:
            payload['regionId'] = region
        return await self._post('topRequests', payload)

    async def get_dynamics(self, phrase: str, region: int | None = None) -> dict:
        payload = {'phrase': phrase}
        if region is not None:
            payload['regionId'] = region
        return await self._post('dynamics', payload)

    async def get_regions(self) -> dict:
        return await self._post('regions', {})

    async def get_regions_distribution(self, phrase: str) -> dict:
        return await self._post('regionsDistribution', {'phrase': phrase})
