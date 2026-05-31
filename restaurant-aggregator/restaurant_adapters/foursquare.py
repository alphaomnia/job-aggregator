from __future__ import annotations

from restaurants.config import FOURSQUARE_BASE, PRAGUE_CENTER
from restaurants.models import RestaurantListing
from .base import BaseRestaurantAdapter

RESTAURANT_CATEGORY_ID = "13065"
MAX_RESULTS = 950


class FoursquareAdapter(BaseRestaurantAdapter):
    name = "foursquare"

    def fetch(self) -> list[RestaurantListing]:
        if not self.api_key:
            print(f"[{self.name}] No API key, skipping")
            return []

        results: list[RestaurantListing] = []
        cursor: str | None = None
        headers = {
            "Authorization": self.api_key,
            "Accept": "application/json",
        }

        while len(results) < MAX_RESULTS:
            params: dict = {
                "query": "restaurant",
                "ll": f"{PRAGUE_CENTER[0]},{PRAGUE_CENTER[1]}",
                "radius": 15000,
                "limit": 50,
                "categories": RESTAURANT_CATEGORY_ID,
            }
            if cursor:
                params["cursor"] = cursor

            resp = self._get(f"{FOURSQUARE_BASE}/places/search", params=params, headers=headers)
            if not resp:
                break

            data = resp.json()
            for place in data.get("results", []):
                listing = self._to_listing(place)
                if listing:
                    results.append(listing)

            cursor = data.get("context", {}).get("next_cursor")
            if not cursor:
                break

            self._sleep(0.2)

        if len(results) >= MAX_RESULTS:
            print(f"[{self.name}] Hit {MAX_RESULTS} result cap (free tier limit)")

        return results

    def _to_listing(self, place: dict) -> RestaurantListing | None:
        name = place.get("name", "").strip()
        if not name:
            return None

        location = place.get("location", {})
        address_parts = [
            location.get("address", ""),
            location.get("locality", ""),
            location.get("region", ""),
        ]
        address = ", ".join(p for p in address_parts if p) or "Praha"

        fsq_id = place.get("fsq_id", "")
        google_maps_url = f"https://foursquare.com/v/{fsq_id}" if fsq_id else ""

        cuisine = [cat["name"] for cat in place.get("categories", []) if cat.get("name")]
        price_level = place.get("price", 0)
        raw_rating = place.get("rating", 0.0)
        rating = round(raw_rating / 2, 1) if raw_rating else 0.0

        neighborhood = location.get("neighborhood", [""])[0] if isinstance(
            location.get("neighborhood"), list
        ) else location.get("neighborhood", "")

        return RestaurantListing(
            name=name,
            address=address,
            source="foursquare",
            source_id=fsq_id,
            neighborhood=neighborhood,
            cuisine=cuisine,
            price_level=price_level,
            rating=rating,
            phone=place.get("tel", ""),
            website=place.get("website", ""),
            google_maps_url=google_maps_url,
        )
