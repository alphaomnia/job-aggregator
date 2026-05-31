PRAGUE_BBOX = {"south": 49.9419, "west": 14.2244, "north": 50.1774, "east": 14.7072}
PRAGUE_CENTER = (50.0755, 14.4378)
PRAGUE_SEARCH_RADIUS_M = 15_000

PRAGUE_DISTRICTS = [f"Prague {i}" for i in range(1, 11)]

NEIGHBORHOODS = [
    "Stare Mesto",
    "Nove Mesto",
    "Mala Strana",
    "Hradcany",
    "Vinohrady",
    "Zizkov",
    "Smichov",
    "Holesovice",
    "Dejvice",
    "Nusle",
    "Vrsovice",
    "Letna",
    "Bubenec",
    "Pankrac",
]

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
FOURSQUARE_BASE = "https://api.foursquare.com/v3"
GOOGLE_PLACES_BASE = "https://maps.googleapis.com/maps/api/place"

GOOGLE_DETAIL_FIELDS_BASIC = (
    "name,formatted_address,geometry,place_id,types,"
    "address_components,permanently_closed"
)
GOOGLE_DETAIL_FIELDS_CONTACT = (
    "formatted_phone_number,website,opening_hours"
)
GOOGLE_DETAIL_FIELDS_ATMOSPHERE = (
    "price_level,rating,user_ratings_total,photos"
)
