from .base import BaseRestaurantAdapter
from .google_places import GooglePlacesAdapter
from .openstreetmap import OpenStreetMapAdapter
from .foursquare import FoursquareAdapter

RESTAURANT_ADAPTERS: dict[str, type[BaseRestaurantAdapter]] = {
    "google_places": GooglePlacesAdapter,
    "openstreetmap": OpenStreetMapAdapter,
    "foursquare": FoursquareAdapter,
}
