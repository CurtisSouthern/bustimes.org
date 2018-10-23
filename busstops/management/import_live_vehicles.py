import math
import requests
import logging
import sys
from setproctitle import setproctitle
from time import sleep
from django.db import OperationalError, IntegrityError, transaction
from django.core.management.base import BaseCommand
from django.utils import timezone
from ..models import DataSource


logger = logging.getLogger(__name__)


def calculate_bearing(a, b):
    a_lat = math.radians(a.y)
    a_lon = math.radians(a.x)
    b_lat = math.radians(b.y)
    b_lon = math.radians(b.x)

    y = math.sin(b_lon - a_lon) * math.cos(b_lat)
    x = math.cos(a_lat) * math.sin(b_lat) - math.sin(a_lat) * math.cos(b_lat) * math.cos(b_lon - b_lon)

    bearing_radians = math.atan2(y, x)
    bearing_degrees = math.degrees(bearing_radians)

    if bearing_degrees < 0:
        bearing_degrees += 360

    return bearing_degrees


class ImportLiveVehiclesCommand(BaseCommand):
    session = requests.Session()
    current_location_ids = set()

    def get_items(self):
        response = self.session.get(self.url, timeout=5)
        if response.ok:
            return response.json()
        return ()

    @transaction.atomic
    def handle_item(self, item, now):
        vehicle, vehicle_created, service = self.get_vehicle_and_service(item)
        if not vehicle:
            return
        if vehicle_created:
            latest = None
        else:
            latest = vehicle.latest_location
            if latest and latest.current:
                if latest.source != self.source:
                    return  # defer to other source
                if (type(item) is dict and latest.data == item):
                    self.current_location_ids.add(latest.id)
                    return  # no change
        location = self.create_vehicle_location(item, vehicle, service)
        if type(item) is dict:
            location.data = item
        elif latest and location.datetime == latest.datetime:
            self.current_location_ids.add(latest.id)
            return
        location.vehicle = vehicle
        location.service = service
        location.source = self.source
        if not location.heading and latest and latest.service == service:
            location.heading = calculate_bearing(latest.latlong, location.latlong)
        if not location.datetime:
            location.datetime = now
        # save new location
        location.current = True
        location.save()
        vehicle.latest_location = location
        vehicle.save()
        self.current_location_ids.add(location.id)
        if latest:
            # mark old location as not current
            latest.current = False
            latest.save()

    def update(self):
        now = timezone.now()
        self.source, source_created = DataSource.objects.update_or_create(
            {'url': self.url, 'datetime': now},
            name=self.source_name
        )

        self.current_location_ids = set()

        try:
            for item in self.get_items():
                self.handle_item(item, now)
            # mark any vehicles that have gone offline as not current
            old_locations = self.source.vehiclelocation_set.filter(current=True)
            old_locations = old_locations.exclude(id__in=self.current_location_ids)
            print(old_locations.update(current=False), end='\t', flush=True)
        except (requests.exceptions.RequestException, IntegrityError, TypeError, ValueError) as e:
            print(e)
            logger.error(e, exc_info=True)
            self.source.vehiclelocation_set.filter(current=True).update(current=False)
            return 120

        return 40

    def handle(self, *args, **options):
        setproctitle(sys.argv[1])
        while True:
            try:
                wait = self.update()
            except OperationalError as e:
                wait = 0
                print(e)
                logger.error(e, exc_info=True)
            sleep(wait)
