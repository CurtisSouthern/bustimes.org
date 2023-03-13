import csv
import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import GEOSGeometry, LineString, MultiLineString
from django.core.management.base import BaseCommand
from django.db.models import Count, Exists, OuterRef, Q
from django.utils.dateparse import parse_duration
from requests_html import HTMLSession

from busstops.models import AdminArea, DataSource, Operator, Region, Service, StopPoint

from ...download_utils import download_if_changed
from ...models import Calendar, CalendarDate, Route, StopTime, Trip

logger = logging.getLogger(__name__)

MODES = {
    0: "tram",
    2: "rail",
    3: "bus",
    4: "ferry",
    200: "coach",
}


def parse_date(string):
    return datetime.strptime(string, "%Y%m%d")


def read_file(archive, name):
    try:
        with archive.open(name) as open_file:
            with io.TextIOWrapper(open_file, encoding="utf-8-sig") as wrapped_file:
                yield from csv.DictReader(wrapped_file)
    except KeyError:
        # file doesn't exist
        return


def get_stop_id(stop_id):
    if "_merged_" in stop_id:
        parts = stop_id.split("_")
        return parts[parts.index("merged") - 1]
    return stop_id


def get_calendar(line):
    return Calendar(
        mon="1" == line["monday"],
        tue="1" == line["tuesday"],
        wed="1" == line["wednesday"],
        thu="1" == line["thursday"],
        fri="1" == line["friday"],
        sat="1" == line["saturday"],
        sun="1" == line["sunday"],
        start_date=parse_date(line["start_date"]),
        end_date=parse_date(line["end_date"]),
    )


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Import data even if the GTFS feeds haven't changed",
        )
        parser.add_argument("collections", nargs="*", type=str)

    def handle_operator(self, line):
        agency_id = line["agency_id"]
        agency_id = f"ie-{agency_id}"

        operator = Operator.objects.filter(
            Q(name__iexact=line["agency_name"]) | Q(noc=agency_id)
        ).first()

        if not operator:
            operator = Operator(name=line["agency_name"], noc=agency_id)
            operator.save()

        return operator

    def do_stops(self, archive):
        stops = {}
        admin_areas = {}
        stops_not_created = {}
        for line in read_file(archive, "stops.txt"):
            stop_id = get_stop_id(line["stop_id"])
            if stop_id[0] in "78" and len(stop_id) <= 16:
                stop = StopPoint(
                    atco_code=stop_id,
                    common_name=line["stop_name"],
                    latlong=GEOSGeometry(
                        f"POINT({line['stop_lon']} {line['stop_lat']})"
                    ),
                    locality_centre=False,
                    active=True,
                )
                if ", stop" in stop.common_name and stop.common_name.count(", ") == 1:
                    stop.common_name, stop.indicator = stop.common_name.split(", ")
                stop.common_name = stop.common_name[:48]
                stops[stop_id] = stop
            else:
                stops_not_created[stop_id] = line
        existing_stops = StopPoint.objects.only(
            "atco_code", "common_name", "latlong"
        ).in_bulk(stops)

        stops_to_create = [
            stop for stop in stops.values() if stop.atco_code not in existing_stops
        ]
        stops_to_update = [
            stop
            for stop in stops.values()
            if stop.atco_code in existing_stops
            and (
                existing_stops[stop.atco_code].latlong != stop.latlong
                or existing_stops[stop.atco_code].common_name != stop.common_name
            )
        ]
        StopPoint.objects.bulk_update(
            stops_to_update, ["common_name", "latlong", "indicator"]
        )

        for stop in stops_to_create:
            admin_area_id = stop.atco_code[:3]
            if admin_area_id not in admin_areas:
                admin_areas[admin_area_id] = AdminArea.objects.filter(
                    id=admin_area_id
                ).exists()
            if admin_areas[admin_area_id]:
                stop.admin_area_id = admin_area_id

        StopPoint.objects.bulk_create(stops_to_create, batch_size=1000)
        return StopPoint.objects.only("atco_code").in_bulk(stops), stops_not_created

    def handle_route(self, line):

        line_name = line["route_short_name"]
        description = line["route_long_name"]
        if not line_name and " " not in description:
            line_name = description
            if len(line_name) < 5:
                description = ""

        operator = self.operators.get(line["agency_id"])

        if self.source.name == "combined GTFS":
            q = Q(operator=operator)
            if operator.name == "Expressway":
                q |= Q(operator__name="Bus Éireann")
        else:
            q = Q(source=self.source) | Q(operator=operator)
        services = Service.objects.filter(q)

        q = Exists(
            Route.objects.filter(code=line["route_id"], service=OuterRef("id"))
        ) | Q(service_code=line["route_id"])

        if line_name:
            q |= Q(line_name__iexact=line_name)
        elif description:
            q |= Q(description=description)

        service = services.filter(q).order_by("id").first()
        if not service:
            service = Service(source=self.source)

        service.service_code = line["route_id"]
        service.line_name = line_name
        service.description = description
        service.mode = MODES.get(int(line["route_type"]), "")
        service.current = True
        service.service_code = line["route_id"]
        service.source = self.source
        service.save()

        if operator:
            if service.id in self.services:
                service.operator.add(operator)
            else:
                service.operator.set([operator])
        self.services[service.id] = service

        route, created = Route.objects.update_or_create(
            {
                "line_name": service.line_name,
                "description": service.description,
                "service": service,
            },
            source=self.source,
            code=line["route_id"],
        )
        if not created:
            route.trip_set.all().delete()
        self.routes[line["route_id"]] = route

    def handle_zipfile(self, path):
        self.shapes = {}
        self.service_shapes = {}
        self.operators = {}
        self.routes = {}
        self.services = {}
        headsigns = {}

        with zipfile.ZipFile(path) as archive:

            for line in read_file(archive, "shapes.txt"):
                shape_id = line["shape_id"]
                if shape_id not in self.shapes:
                    self.shapes[shape_id] = []
                self.shapes[shape_id].append(
                    GEOSGeometry(
                        f"POINT({line['shape_pt_lon']} {line['shape_pt_lat']})"
                    )
                )

            for line in read_file(archive, "agency.txt"):
                self.operators[line["agency_id"]] = self.handle_operator(line)

            for line in read_file(archive, "routes.txt"):
                self.handle_route(line)

            stops, stops_not_created = self.do_stops(archive)

            calendars = {}
            for line in read_file(archive, "calendar.txt"):
                calendar = get_calendar(line)
                calendar.save()
                calendars[line["service_id"]] = calendar

            for line in read_file(archive, "calendar_dates.txt"):
                operation = (
                    line["exception_type"] == "1"
                )  # '1' = operates, '2' = does not operate
                CalendarDate.objects.create(
                    calendar=calendars[line["service_id"]],
                    start_date=parse_date(line["date"]),
                    end_date=parse_date(line["date"]),
                    operation=operation,
                    special=operation,  # additional date of operation
                )

            trips = {}
            for line in read_file(archive, "trips.txt"):
                route = self.routes.get(line["route_id"])
                if not route:
                    continue
                trips[line["trip_id"]] = Trip(
                    route=route,
                    calendar=calendars[line["service_id"]],
                    inbound=line["direction_id"] == "1",
                    ticket_machine_code=line["trip_id"],
                )
                if line["shape_id"]:
                    if route.service_id not in self.service_shapes:
                        self.service_shapes[route.service_id] = set()
                    self.service_shapes[route.service_id].add(line["shape_id"])
                headsign = line["trip_headsign"]
                if headsign:
                    if headsign.endswith(" -"):
                        headsign = None
                    elif headsign.startswith("- "):
                        headsign = headsign[2:]
                    if headsign:
                        if line["route_id"] not in headsigns:
                            headsigns[line["route_id"]] = {
                                "0": set(),
                                "1": set(),
                            }
                        headsigns[line["route_id"]][line["direction_id"]].add(headsign)
            for route_id in headsigns:
                route = self.routes[route_id]
                origins = headsigns[route_id]["1"]  # inbound destinations
                destinations = headsigns[route_id]["0"]  # outbound destinations
                origin = ""
                destination = ""
                if len(origins) <= 1 and len(destinations) <= 1:
                    if origins:
                        origin = list(origins)[0]
                    if destinations:
                        destination = list(destinations)[0]

                    # if headsign contains ' - ' assume it's 'origin - destination', not just destination
                    if origin and " - " in origin:
                        route.inbound_description = origin
                        origin = ""
                    if destination and " - " in destination:
                        route.outbound_description = destination
                        destination = ""

                    route.origin = origin
                    route.destination = destination

                    if not route.service.description:
                        route.service.description = (
                            route.outbound_description or route.inbound_description
                        )

                    route.save(
                        update_fields=[
                            "origin",
                            "destination",
                            "inbound_description",
                            "outbound_description",
                        ]
                    )
                    route.service.save(update_fields=["description"])

            trip = None
            previous_line = None

            for line in read_file(archive, "stop_times.txt"):

                if not previous_line or previous_line["trip_id"] != line["trip_id"]:

                    if trip:
                        trip.destination = stops.get(previous_line["stop_id"])
                        trip.end = parse_duration(previous_line["arrival_time"])

                    trip = trips[line["trip_id"]]
                    trip.start = parse_duration(line["departure_time"])

                previous_line = line

            # last trip:
            trip.destination = stops.get(line["stop_id"])
            trip.end = parse_duration(line["arrival_time"])

            Trip.objects.bulk_create(trips.values(), batch_size=1000)

            i = 0
            stop_times = []

            for line in read_file(archive, "stop_times.txt"):
                stop = stops.get(line["stop_id"])

                stop_time = StopTime(
                    arrival=parse_duration(line["arrival_time"]),
                    departure=parse_duration(line["departure_time"]),
                    sequence=line["stop_sequence"],
                    trip=trips[line["trip_id"]],
                )
                if line.get("pickup_type") == "1":  # "No pickup available"
                    stop_time.pick_up = False

                if stop:
                    stop_time.stop = stop
                elif line["stop_id"] in stops_not_created:
                    stop_time.stop_code = stops_not_created[line["stop_id"]][
                        "stop_name"
                    ]
                else:
                    stop_time.stop_code = line["stop_id"]
                    print(line)

                if stop_time.arrival == stop_time.departure:
                    stop_time.arrival = None

                stop_times.append(stop_time)

                if i == 999:
                    StopTime.objects.bulk_create(stop_times)
                    stop_times = []
                    i = 0
                else:
                    i += 1

                previous_line = line

        # last trip
        if not stop_time.arrival:
            stop_time.arrival = stop_time.departure
            stop_time.departure = None

        StopTime.objects.bulk_create(stop_times)

        for service in self.services.values():
            if service.id in self.service_shapes:
                linestrings = [
                    LineString(*self.shapes[shape])
                    for shape in self.service_shapes[service.id]
                    if shape in self.shapes
                ]
                service.geometry = MultiLineString(*linestrings)
                service.save(update_fields=["geometry"])
            else:
                pass

            service.do_stop_usages()

            service.region = (
                Region.objects.filter(adminarea__stoppoint__service=service)
                .annotate(Count("adminarea__stoppoint__service"))
                .order_by("-adminarea__stoppoint__service__count")
                .first()
            )
            if service.region:
                service.save(update_fields=["region"])
            service.update_search_vector()

        self.source.save(update_fields=["datetime"])

        for operator in self.operators.values():
            operator.region = (
                Region.objects.filter(adminarea__stoppoint__service__operator=operator)
                .annotate(Count("adminarea__stoppoint__service__operator"))
                .order_by("-adminarea__stoppoint__service__operator__count")
                .first()
            )
            if operator.region_id:
                operator.save(update_fields=["region"])

        current_services = self.source.service_set.filter(current=True)
        logger.info(
            current_services.exclude(route__in=self.routes.values()).update(
                current=False
            )
        )
        logger.info(
            current_services.exclude(route__trip__isnull=False).update(current=False)
        )
        logger.info(
            self.source.route_set.exclude(
                id__in=(route.id for route in self.routes.values())
            ).delete()
        )
        StopPoint.objects.filter(active=False, service__current=True).update(
            active=True
        )
        StopPoint.objects.filter(active=True, service__isnull=True).update(active=False)

    def handle(self, *args, **options):
        prefix = "https://www.transportforireland.ie"

        session = HTMLSession()
        response = session.get(f"{prefix}/transitData/PT_Data.html")

        collections = []
        for element in response.html.find('a[href^="Data/GTFS_"]'):
            if element.text in (
                "Dublin Bus",
                "Bus Eireann",
                "GoAhead Ireland",
                "LUAS",
                "Irish Rail",
            ):
                # data is in the combined "Realtime Transport Operators"
                continue
            url = element.absolute_links.pop()
            source = DataSource.objects.filter(url=url).first()
            if not source:
                source = DataSource.objects.create(name=element.text, url=url)
            collections.append(source)

        print(collections)

        # return

        for source in collections:
            path = settings.DATA_DIR / Path(source.url).name

            modified, last_modified = download_if_changed(path, source.url)
            if modified or last_modified and last_modified != source.datetime:

                logger.info(f"{source=} {last_modified=}")
                if last_modified:
                    source.datetime = last_modified
                self.source = source
                self.handle_zipfile(path)
