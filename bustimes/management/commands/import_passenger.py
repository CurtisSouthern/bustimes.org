"""Import timetable data "fresh from the cow"
"""

import os
import requests
from urllib.parse import urljoin, urlparse
from time import sleep
from requests_html import HTMLSession
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q
from busstops.models import DataSource
from .import_bod import handle_file, get_operator_ids, clean_up, logger
from .import_transxchange import Command as TransXChangeCommand
from ...models import TimetableDataSource
from ...download_utils import write_file


def get_version(url):
    modified = False

    filename = os.path.basename(urlparse(url).path)
    path = os.path.join(settings.DATA_DIR, filename)

    if not os.path.exists(path):
        response = requests.get(url, stream=True)
        url = response.url  # in case there was a redirect
        filename = os.path.basename(urlparse(url).path)
        path = os.path.join(settings.DATA_DIR, filename)

        if not os.path.exists(path):
            write_file(path, response)
            modified = True

    return {
        "url": url,
        "filename": filename,
        "modified": modified,
    }


def get_versions(session, url):
    versions = []
    try:
        response = session.get(url, timeout=5)
    except requests.RequestException as e:
        logger.warning(f"{url} {e}")
        sleep(5)
        return
    if not response.ok:
        logger.warning(f"{url} {response}")
        sleep(5)
        return
    for element in response.html.find():
        if element.tag == "a":
            url = urljoin(element.base_url, element.attrs["href"])
            if "/txc" in url:
                versions.append(get_version(url))

    return versions


class Command(BaseCommand):
    @staticmethod
    def add_arguments(parser):
        parser.add_argument("operator_name", type=str, nargs="?")

    def handle(self, operator_name, *args, **options):
        command = TransXChangeCommand()
        command.set_up()

        session = HTMLSession()

        prefix = "https://data.discoverpassenger.com/operator"

        sources = DataSource.objects.filter(url__startswith=prefix)

        timetable_data_sources = TimetableDataSource.objects.filter(
            active=True, url__startswith=prefix
        )
        if operator_name:
            timetable_data_sources = timetable_data_sources.filter(name=operator_name)

        for source in timetable_data_sources:

            versions = get_versions(session, source.url)

            if versions:
                prefix = versions[0]["filename"].split("_")[0]
                prefix = f"{prefix}_"  # eg 'transdevblazefield_'
                for filename in os.listdir(settings.DATA_DIR):
                    if filename.startswith(prefix):
                        if not any(
                            filename == version["filename"] for version in versions
                        ):
                            os.remove(os.path.join(settings.DATA_DIR, filename))
            else:
                sleep(2)
                continue

            new_versions = any(version["modified"] for version in versions)

            command.source, _ = DataSource.objects.get_or_create(
                {"name": source.name}, url=source.url
            )

            if new_versions or operator_name:
                logger.info(source.name)

                operators = list(source.operators.values_list("noc", flat=True))

                command.source.datetime = timezone.now()
                command.region_id = source.region_id
                command.service_ids = set()
                command.route_ids = set()
                command.garages = {}

                for version in versions:  # newest first
                    if version["modified"] or operator_name:
                        logger.info(version)
                        handle_file(command, version["filename"], qualify_filename=True)

                clean_up(operators, sources)

                operator_ids = get_operator_ids(command.source)
                logger.info(f"  {operator_ids}")

                foreign_operators = [o for o in operator_ids if o not in operators]
                logger.info(f"  {foreign_operators}")

            # even if there are no new versions, delete old routes from expired versions
            old_routes = command.source.route_set
            for version in versions:
                old_routes = old_routes.filter(~Q(code__startswith=version["filename"]))
            old_routes = old_routes.delete()
            if not new_versions:
                if old_routes[0]:
                    logger.info(source.name)
                else:
                    sleep(2)
                    continue
            logger.info(f" {old_routes=}")

            # mark old services as not current
            old_services = command.source.service_set.filter(current=True, route=None)
            logger.info(f"  old services: {old_services.update(current=False)}")

            if new_versions or operator_name:
                command.finish_services()

                command.source.save()

        command.debrief()
