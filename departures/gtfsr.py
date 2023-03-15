from datetime import timedelta

import requests
from django.conf import settings
from django.core.cache import cache
from google.protobuf import json_format
from google.transit import gtfs_realtime_pb2

from bustimes.formatting import format_timedelta
from vehicles.utils import redis_client


def _get_feed():
    if settings.NTA_API_KEY:
        if not redis_client.set("ntaie_lock", 1, ex=60, nx=True):
            return
        url = "https://api.nationaltransport.ie/gtfsr/v2/TripUpdates"
        response = requests.get(
            url, headers={"x-api-key": settings.NTA_API_KEY}, timeout=10
        )
        if response.ok:
            feed = gtfs_realtime_pb2.FeedMessage()
            feed.ParseFromString(response.content)
            return feed


def get_feed_entities() -> dict:
    feed = _get_feed()
    if feed:
        feed = json_format.MessageToDict(feed)
        if "entity" in feed:
            feed["entity"] = {
                entity["tripUpdate"]["trip"]["tripId"]: entity
                for entity in feed["entity"]
                if "tripId" in entity["tripUpdate"]["trip"]
            }
            cache.set("ntaie", feed, 300)  # cache for 5 minutes
            return feed
    return cache.get("ntaie")


def get_trip_update(trip) -> dict:
    trip_id = trip.ticket_machine_code
    if trip_id:
        feed = get_feed_entities()
        if feed and trip_id in feed["entity"]:
            return feed["entity"][trip_id]


def apply_trip_update(stops, trip_update: dict):
    if "stopTimeUpdate" not in trip_update["tripUpdate"]:
        return

    stops_by_sequence = {}
    for stop in stops:
        assert stop.sequence not in stops_by_sequence
        stops_by_sequence[stop.sequence] = stop
        stop.update = None

    for stop_time_update in trip_update["tripUpdate"]["stopTimeUpdate"]:
        sequence = stop_time_update["stopSequence"]
        stop_time = stops_by_sequence[sequence]
        assert sequence == stop_time.sequence
        if "stopId" in stop_time_update:
            assert stop_time_update["stopId"] == stop_time.stop_id
        stop_time.update = stop_time_update

    stop_time_update = None
    for stop_time in stops:
        if stop_time.update:
            stop_time_update = stop_time.update

        if stop_time_update:
            stop_time.update = stop_time_update
            if stop_time_update["scheduleRelationship"] == "SKIPPED":
                continue
            if stop_time.arrival and "arrival" in stop_time_update:
                stop_time.expected_arrival = format_timedelta(
                    stop_time.arrival
                    + timedelta(seconds=stop_time_update["arrival"]["delay"])
                )
            if stop_time.departure and "departure" in stop_time_update:
                stop_time.expected_departure = format_timedelta(
                    stop_time.departure
                    + timedelta(seconds=stop_time_update["departure"]["delay"])
                )


def update_stop_departures(departures):
    feed = get_feed_entities()
    if not feed:
        return

    for departure in departures:
        stop_time = departure["stop_time"]
        trip = stop_time.trip
        trip_update = feed["entity"].get(trip.ticket_machine_code)
        if trip_update:
            if trip_update["tripUpdate"]["trip"]["scheduleRelationship"] == "CANCELED":
                departure["cancelled"] = True
            else:
                stop_time_update = None
                for update in trip_update["tripUpdate"]["stopTimeUpdate"]:
                    if update["stopSequence"] > stop_time.sequence:
                        break
                    stop_time_update = update
                if stop_time_update:
                    if stop_time_update["scheduleRelationship"] == "SKIPPED":
                        departure["cancelled"] = True
                    elif "departure" in stop_time_update:
                        delay = timedelta(
                            seconds=stop_time_update["departure"]["delay"]
                        )
                        departure["live"] = departure["time"] + delay
