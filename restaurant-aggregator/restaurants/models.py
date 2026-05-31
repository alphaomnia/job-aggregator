from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@dataclass
class RestaurantListing:
    name: str
    address: str
    source: str                              # google_places | openstreetmap | foursquare
    source_id: str = ""                      # Google Place ID, OSM node ID, fsq_id
    neighborhood: str = ""
    cuisine: list[str] = field(default_factory=list)
    price_level: int = 0                     # 0=unknown, 1-4 (Google scale)
    rating: float = 0.0
    review_count: int = 0
    phone: str = ""
    website: str = ""
    google_maps_url: str = ""
    opening_hours: dict = field(default_factory=dict)
    photos: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    id: str = ""
    first_seen: str = ""
    last_updated: str = ""
    status: str = "new"                      # new | want_to_visit | visited | dismissed

    def __post_init__(self) -> None:
        today = _now_iso()
        if not self.id:
            self.id = self.compute_id()
        if not self.first_seen:
            self.first_seen = today
        if not self.last_updated:
            self.last_updated = today

    def compute_id(self) -> str:
        key = self.source_id if self.source_id else \
              f"{self.name.lower().strip()}|{self.address.lower().strip()}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> RestaurantListing:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        obj = cls.__new__(cls)
        for f in cls.__dataclass_fields__.values():
            if f.name not in filtered:
                default = f.default if f.default is not f.default_factory else f.default_factory()  # type: ignore[misc]
                object.__setattr__(obj, f.name, default)
        for k, v in filtered.items():
            object.__setattr__(obj, k, v)
        return obj
