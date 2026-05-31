from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .models import RestaurantListing, _now_iso


class RestaurantStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._restaurants: dict[str, RestaurantListing] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text("utf-8"))
            for r in data.get("restaurants", []):
                listing = RestaurantListing.from_dict(r)
                self._restaurants[listing.id] = listing
        except Exception as exc:
            print(f"[store] Failed to load {self._path}: {exc}")

    def all(self) -> list[RestaurantListing]:
        return list(self._restaurants.values())

    def get(self, rid: str) -> RestaurantListing | None:
        return self._restaurants.get(rid)

    def ids(self) -> set[str]:
        return set(self._restaurants.keys())

    def merge(self, incoming: Iterable[RestaurantListing]) -> list[RestaurantListing]:
        today = _now_iso()
        new_listings: list[RestaurantListing] = []

        for listing in incoming:
            existing = self._restaurants.get(listing.id)
            if existing is None:
                self._restaurants[listing.id] = listing
                new_listings.append(listing)
            else:
                for attr in (
                    "name", "address", "neighborhood", "cuisine", "price_level",
                    "rating", "review_count", "phone", "website", "google_maps_url",
                    "opening_hours", "photos", "tags",
                ):
                    new_val = getattr(listing, attr)
                    if new_val:
                        object.__setattr__(existing, attr, new_val)
                object.__setattr__(existing, "last_updated", today)

        return new_listings

    def new_since(self, days: int = 7) -> list[RestaurantListing]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        return [r for r in self._restaurants.values() if r.first_seen >= cutoff]

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        restaurants = sorted(
            self._restaurants.values(),
            key=lambda r: (r.first_seen, r.rating),
            reverse=True,
        )
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(restaurants),
            "restaurants": [r.to_dict() for r in restaurants],
        }
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
        print(f"[store] Saved {len(restaurants)} restaurants to {self._path}")
