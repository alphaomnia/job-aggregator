from __future__ import annotations

import time

from restaurants.config import (
    GOOGLE_DETAIL_FIELDS_ATMOSPHERE,
    GOOGLE_DETAIL_FIELDS_BASIC,
    GOOGLE_DETAIL_FIELDS_CONTACT,
    GOOGLE_PLACES_BASE,
    PRAGUE_CENTER,
    PRAGUE_DISTRICTS,
    NEIGHBORHOODS,
)
from restaurants.models import RestaurantListing
from .base import BaseRestaurantAdapter

_SKIP_TYPES = {
    "restaurant", "food", "point_of_interest", "establishment",
    "meal_takeaway", "meal_delivery", "store", "bar", "cafe",
}


def _types_to_cuisine(types: list[str]) -> list[str]:
    result = []
    for t in types:
        if t in _SKIP_TYPES:
            continue
        label = t.replace("_restaurant", "").replace("_", " ").title()
        if label:
            result.append(label)
    return result


def _extract_neighborhood(address_components: list[dict]) -> str:
    for comp in address_components:
        types = comp.get("types", [])
        if "sublocality_level_1" in types or "neighborhood" in types:
            return comp.get("long_name", "")
    return ""


class GooglePlacesAdapter(BaseRestaurantAdapter):
    name = "google_places"

    def fetch(self) -> list[RestaurantListing]:
        if not self.api_key:
            print(f"[{self.name}] No API key set - skipping")
            return []

        if self.mode == "bulk":
            return self._bulk_scan()
        return self._incremental()

    def _bulk_scan(self) -> list[RestaurantListing]:
        queries = [f"restaurants in {d}" for d in PRAGUE_DISTRICTS]
        queries += [f"restaurants in {n}, Prague" for n in NEIGHBORHOODS]
        return self._run_text_searches(queries)

    def _incremental(self) -> list[RestaurantListing]:
        nearby = self._nearby_search()
        text = self._run_text_searches(["restaurants in Prague 1", "restaurants in Prague 2"])
        seen_ids: set[str] = set()
        results: list[RestaurantListing] = []
        for listing in nearby + text:
            if listing.source_id not in seen_ids:
                seen_ids.add(listing.source_id)
                results.append(listing)
        return results

    def _run_text_searches(self, queries: list[str]) -> list[RestaurantListing]:
        seen_place_ids: set[str] = set()
        results: list[RestaurantListing] = []
        for query in queries:
            raw_places = self._text_search(query)
            for place in raw_places:
                pid = place.get("place_id", "")
                if not pid or pid in seen_place_ids:
                    continue
                seen_place_ids.add(pid)
                details = self._place_details(pid)
                listing = self._to_listing(place, details)
                if listing:
                    results.append(listing)
                self._sleep(0.1)
        return results

    def _text_search(self, query: str) -> list[dict]:
        url = f"{GOOGLE_PLACES_BASE}/textsearch/json"
        places: list[dict] = []
        params = {"query": query, "type": "restaurant", "key": self.api_key}
        for _ in range(3):
            resp = self._get(url, params=params)
            if not resp:
                break
            data = resp.json()
            status = data.get("status", "")
            if status not in ("OK", "ZERO_RESULTS"):
                print(f"[{self.name}] Text search status={status} for query={query!r}")
                break
            places.extend(data.get("results", []))
            token = data.get("next_page_token")
            if not token:
                break
            self._sleep(2)
            params = {"pagetoken": token, "key": self.api_key}
        return places

    def _nearby_search(self) -> list[dict]:
        url = f"{GOOGLE_PLACES_BASE}/nearbysearch/json"
        places: list[dict] = []
        params = {
            "location": f"{PRAGUE_CENTER[0]},{PRAGUE_CENTER[1]}",
            "radius": 15000,
            "type": "restaurant",
            "rankby": "prominence",
            "key": self.api_key,
        }
        for _ in range(3):
            resp = self._get(url, params=params)
            if not resp:
                break
            data = resp.json()
            status = data.get("status", "")
            if status not in ("OK", "ZERO_RESULTS"):
                print(f"[{self.name}] Nearby search status={status}")
                break
            places.extend(data.get("results", []))
            token = data.get("next_page_token")
            if not token:
                break
            self._sleep(2)
            params = {"pagetoken": token, "key": self.api_key}
        return places

    def _place_details(self, place_id: str) -> dict:
        url = f"{GOOGLE_PLACES_BASE}/details/json"
        all_fields = ",".join([
            GOOGLE_DETAIL_FIELDS_BASIC,
            GOOGLE_DETAIL_FIELDS_CONTACT,
            GOOGLE_DETAIL_FIELDS_ATMOSPHERE,
        ])
        resp = self._get(url, params={"place_id": place_id, "fields": all_fields, "key": self.api_key})
        if not resp:
            return {}
        return resp.json().get("result", {})

    def _to_listing(self, place: dict, details: dict) -> RestaurantListing | None:
        src = details if details else place
        name = src.get("name", "").strip()
        if not name:
            return None

        place_id = place.get("place_id", "")
        address = src.get("formatted_address", place.get("formatted_address", ""))
        neighborhood = _extract_neighborhood(src.get("address_components", []))
        cuisine = _types_to_cuisine(src.get("types", []))
        rating = float(src.get("rating", 0.0) or 0.0)
        review_count = int(src.get("user_ratings_total", 0) or 0)
        price_level = int(src.get("price_level", 0) or 0)
        phone = src.get("formatted_phone_number", "")
        website = src.get("website", "")
        maps_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}" if place_id else ""

        oh_data = src.get("opening_hours", {})
        opening_hours: dict = {}
        if oh_data:
            opening_hours = {
                "weekday_text": oh_data.get("weekday_text", []),
                "open_now": oh_data.get("open_now"),
            }

        photos: list[str] = []
        for photo in src.get("photos", [])[:3]:
            ref = photo.get("photo_reference", "")
            if ref:
                photos.append(
                    f"https://maps.googleapis.com/maps/api/place/photo"
                    f"?maxwidth=400&photoreference={ref}&key={self.api_key}"
                )

        if src.get("permanently_closed"):
            return None

        return RestaurantListing(
            name=name,
            address=address,
            source="google_places",
            source_id=place_id,
            neighborhood=neighborhood,
            cuisine=cuisine,
            price_level=price_level,
            rating=rating,
            review_count=review_count,
            phone=phone,
            website=website,
            google_maps_url=maps_url,
            opening_hours=opening_hours,
            photos=photos,
        )
