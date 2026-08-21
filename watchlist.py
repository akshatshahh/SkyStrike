"""Rooms and names to pull. Edit this, then run ingest.py.

Venue ids skip a lookup when we already know them. Leave id empty
and ingest will resolve the first US match for the name.
"""

VENUES = [
    {"name": "Madison Square Garden", "id": "KovZpZA7AAEA"},
    {"name": "Radio City Music Hall", "id": ""},
    {"name": "Red Rocks Amphitheatre", "id": ""},
    {"name": "Hollywood Bowl", "id": ""},
    {"name": "United Center", "id": ""},
    {"name": "The Anthem", "id": ""},
]

# Keyword search against Ticketmaster event names / attractions.
ARTISTS = [
    "SZA",
    "Chappell Roan",
    "Tyler, The Creator",
    "Noah Kahan",
]

# Extra searches. Arena listings often come back with no scale;
# these still publish a low/high in Discovery right now.
SEARCHES = [
    {"countryCode": "CA", "classificationName": "music", "size": 80},
    {"keyword": "jazz", "countryCode": "US", "size": 30},
    {"keyword": "comedy", "countryCode": "US", "size": 30},
]

EVENTS_PER_QUERY = 20
