from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher

from .models import RestaurantListing

SOURCE_PRIORITY = ["google_places", "foursquare", "openstreetmap"]
SIMILARITY_THRESHOLD = 0.85


def _normalise(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(ascii_str.lower().split())


def _similarity(a: RestaurantListing, b: RestaurantListing) -> float:
    key_a = _normalise(f"{a.name} {a.address}")
    key_b = _normalise(f"{b.name} {b.address}")
    return SequenceMatcher(None, key_a, key_b).ratio()


def _merge(primary: RestaurantListing, secondary: RestaurantListing) -> RestaurantListing:
    for attr in ("neighborhood", "phone", "website", "google_maps_url"):
        if not getattr(primary, attr) and getattr(secondary, attr):
            object.__setattr__(primary, attr, getattr(secondary, attr))
    if not primary.cuisine and secondary.cuisine:
        object.__setattr__(primary, "cuisine", secondary.cuisine)
    if primary.rating == 0.0 and secondary.rating:
        object.__setattr__(primary, "rating", secondary.rating)
    if primary.review_count == 0 and secondary.review_count:
        object.__setattr__(primary, "review_count", secondary.review_count)
    if primary.price_level == 0 and secondary.price_level:
        object.__setattr__(primary, "price_level", secondary.price_level)
    if not primary.opening_hours and secondary.opening_hours:
        object.__setattr__(primary, "opening_hours", secondary.opening_hours)
    tracer = f"{secondary.source}:{secondary.source_id}" if secondary.source_id else secondary.source
    tags = list(primary.tags)
    if tracer not in tags:
        tags.append(tracer)
    object.__setattr__(primary, "tags", tags)
    return primary


def deduplicate(listings: list[RestaurantListing]) -> list[RestaurantListing]:
    """
    Deduplicate a mixed-source list. Merges cross-source duplicates,
    preferring google_places > foursquare > openstreetmap.
    """
    def _priority(r: RestaurantListing) -> int:
        try:
            return SOURCE_PRIORITY.index(r.source)
        except ValueError:
            return len(SOURCE_PRIORITY)

    sorted_listings = sorted(listings, key=_priority)

    by_id: dict[str, RestaurantListing] = {}
    for listing in sorted_listings:
        if listing.id in by_id:
            by_id[listing.id] = _merge(by_id[listing.id], listing)
        else:
            by_id[listing.id] = listing

    unique: list[RestaurantListing] = []
    for candidate in by_id.values():
        merged = False
        for existing in unique:
            if _similarity(candidate, existing) >= SIMILARITY_THRESHOLD:
                _merge(existing, candidate)
                merged = True
                break
        if not merged:
            unique.append(candidate)

    return unique
