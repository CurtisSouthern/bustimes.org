from pathlib import Path
from unittest import mock

import fakeredis
import time_machine
from django.core.cache import cache
from django.test import TestCase, override_settings
from vcr import use_cassette

from busstops.models import (
    AdminArea,
    DataSource,
    Locality,
    Operator,
    OperatorCode,
    Region,
    Service,
    StopPoint,
)
from bustimes.models import Calendar, Garage, Route, StopTime, Trip

from ...models import Livery, Vehicle, VehicleJourney
from ..commands import import_bod_avl


class BusOpenDataVehicleLocationsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        region = Region.objects.create(id="EA")
        Operator.objects.bulk_create(
            [
                Operator(noc="WHIP", region=region),
                Operator(noc="TGTC", region=region),
                Operator(noc="HAMS", region=region),
                Operator(noc="UNOE", region=region),
                Operator(noc="UNIB", region=region),
                Operator(noc="FBRI", region=region, parent="First"),
                Operator(noc="FECS", region=region, parent="First"),
                Operator(noc="NCTP", region=region),
                Operator(noc="NIBS", region=region),
                Operator(noc="TCVW", region=region, name="National Express Coventry"),
                Operator(
                    noc="TNXB", region=region, name="National Express West Midlands"
                ),
            ]
        )
        Vehicle.objects.bulk_create(
            [
                Vehicle(operator_id="NCTP", code="2929", name="Jeff"),
                Vehicle(operator_id="FECS", code="11111"),
            ]
        )
        cls.source = DataSource.objects.create(
            name="Bus Open Data",
            url="https://data.bus-data.dft.gov.uk/api/v1/datafeed/",
        )
        OperatorCode.objects.bulk_create(
            [
                OperatorCode(operator_id="HAMS", source=cls.source, code="HAMSTRA"),
                OperatorCode(operator_id="TGTC", source=cls.source, code="FOO"),
                OperatorCode(operator_id="WHIP", source=cls.source, code="FOO"),
                OperatorCode(operator_id="UNOE", source=cls.source, code="UNOE"),
                OperatorCode(operator_id="UNOE", source=cls.source, code="UNIB"),
                OperatorCode(operator_id="TCVW", source=cls.source, code="CV"),
                OperatorCode(operator_id="TNXB", source=cls.source, code="CV"),
            ]
        )

        suffolk = AdminArea.objects.create(
            region=region, id=1, atco_code=390, name="Suffolk"
        )
        southwold = Locality.objects.create(admin_area=suffolk, name="Southwold")
        StopPoint.objects.create(
            atco_code="390071066",
            locality=southwold,
            active=True,
            common_name="Kings Head",
        )
        StopPoint.objects.create(atco_code="0500CCITY544", active=False)

        service_u = Service.objects.create(line_name="U")
        service_u.operator.add("WHIP")
        cls.service_c = Service.objects.create(line_name="c")
        cls.service_c.operator.add("HAMS")
        route_u = Route.objects.create(
            service=service_u, source=cls.source, code="u", line_name="UU"
        )
        garage = Garage.objects.create(code="GY", name="Great Yarmouth")
        # route_c = Route.objects.create(service=service_c, source=cls.source, code='c')
        cls.trip = Trip.objects.create(
            route=route_u,
            start="09:23:00",
            end="10:50:00",
            destination_id="0500CCITY544",
            garage=garage,
            operator_id="TCVW",
        )
        # calendar = Calendar.objects.create(mon=True, tue=True, wed=True, thu=True,
        #                                    fri=True, sat=True, sun=True, start_date='2020-10-20')
        # Trip.objects.create(route=route_c, start='15:32:00', end='23:00:00', calendar=calendar)

    def test_get_operator(self):
        command = import_bod_avl.Command()
        command.source = self.source
        # command.get_operator.cache_clear()

        self.assertEqual(command.get_operator("HAMS").get().noc, "HAMS")
        self.assertEqual(command.get_operator("HAMSTRA").get().noc, "HAMS")
        self.assertEqual(command.get_operator("UNOE").get().noc, "UNOE")

        # should ignore operator with id 'UNIB' in favour of one with OperatorCode:
        self.assertEqual(command.get_operator("UNIB").get().noc, "UNOE")

        self.assertEqual(
            list(command.get_operator("FOO").values("noc")),
            [{"noc": "WHIP"}, {"noc": "TGTC"}],
        )

    @time_machine.travel("2020-05-01", tick=False)
    def test_new_bod_avl_a(self):
        command = import_bod_avl.Command()
        command.source = self.source
        # command.get_operator.cache_clear()

        with override_settings(
            CACHES={
                "default": {
                    "BACKEND": "django.core.cache.backends.redis.RedisCache",
                    "LOCATION": "redis://",
                    "OPTIONS": {"connection_class": fakeredis.FakeConnection},
                }
            }
        ):
            redis_client = fakeredis.FakeStrictRedis(version=7)

            with mock.patch(
                "vehicles.management.import_live_vehicles.redis_client", redis_client
            ):
                with mock.patch(
                    "vehicles.management.commands.import_bod_avl.redis_client",
                    redis_client,
                ):
                    with use_cassette(
                        str(Path(__file__).resolve().parent / "vcr" / "bod_avl.yaml")
                    ) as cassette:
                        command.update()

                        cassette.rewind()

                        with self.assertNumQueries(0):
                            command.update()

            self.assertEqual(841, len(command.identifiers))

            # status page

            response = self.client.get("/status")

        self.assertContains(
            response,
            """
            <tr>
                <td>00:00:00</td>
                <td>15:14:46</td>
                <td>-7312486.261274</td>
                <td>841</td>
                <td>841</td>
            </tr>""",
        )
        self.assertContains(
            response,
            """
            <tr>
                <td>00:00:00</td>
                <td>15:14:46</td>
                <td>-7312486.261274</td>
                <td>841</td>
                <td>0</td>
            </tr>""",
        )

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.redis.RedisCache",
                "LOCATION": "redis://",
                "OPTIONS": {"connection_class": fakeredis.FakeConnection},
            }
        }
    )
    @time_machine.travel("2020-10-17T08:34:09", tick=False)
    def test_new_bod_avl_b(self):
        items = [
            {
                "RecordedAtTime": "2020-10-17T08:34:00+00:00",
                "ItemIdentifier": "13505681-c482-451d-a089-ee805e196e7e",
                "ValidUntilTime": "2020-10-24T14:19:46.982911",
                "MonitoredVehicleJourney": {
                    "LineRef": "U",
                    "DirectionRef": "INBOUND",
                    "PublishedLineName": "U",
                    "OperatorRef": "WHIP",
                    "OriginRef": "0500CCITY536",
                    "OriginName": "Dame Mary Archer Wa",
                    "DestinationRef": "0500CCITY544",
                    "DestinationName": "Eddington Sainsbury",
                    "OriginAimedDepartureTime": "2020-06-17T08:23:00+00:00",
                    "VehicleLocation": {
                        "Longitude": "0.141533",
                        "Latitude": "52.1727219",
                        "VehicleJourneyRef": "UNKNOWN",
                    },
                    "VehicleRef": "WHIP-106",
                },
            },
            {
                "ItemIdentifier": "3d723567-dbd6-424c-a3e5-8bbc4932c8b8",
                "RecordedAtTime": "2020-10-30T05:06:29+00:00",
                "ValidUntilTime": "2020-10-30T05:11:31.887243",
                "MonitoredVehicleJourney": {
                    "LineRef": "TGTC:PD1050400:19:242",
                    "PublishedLineName": "843X",
                    "OriginRef": "43000575801",
                    "OriginName": "843X Roughley",
                    "VehicleRef": "SN56 AFE",
                    "OperatorRef": "TGTC",
                    "DestinationRef": "43000280301",
                    "DestinationName": "843X Soho Road",
                    "VehicleLocation": {
                        "Latitude": "52.4972115",
                        "Longitude": "-1.9283381",
                    },
                },
            },
            {
                "ItemIdentifier": "87043019-595c-4269-b4de-a359ae17a474",
                "RecordedAtTime": "2020-10-15T07:46:08+00:00",
                "ValidUntilTime": "2020-10-15T18:02:11.033673",
                "MonitoredVehicleJourney": {
                    "LineRef": "C",
                    "BlockRef": "503",
                    "VehicleRef": "DW18-HAM",
                    "OperatorRef": "HAMSTRA",
                    "DirectionRef": "outbound",
                    "DestinationRef": "2400103099",
                    "VehicleLocation": {"Latitude": "51.2135", "Longitude": "0.285348"},
                    "Bearing": "92.0",
                    "PublishedLineName": "C",
                    "VehicleJourneyRef": "C_20201015_05_53",
                },
                "Extensions": {
                    "VehicleJourney": {
                        "DriverRef": "1038",
                        "Operational": {
                            "TicketMachine": {
                                "JourneyCode": "1532",
                                "TicketMachineServiceCode": "258",
                            }
                        },
                        "VehicleUniqueId": "T2-1",
                    }
                },
            },
        ]

        command = import_bod_avl.Command()
        command.source = self.source
        command.source.datetime = command.get_datetime(
            {"RecordedAtTime": "2020-10-15T07:46:08+00:00"}
        )
        # command.get_operator.cache_clear()

        redis_client = fakeredis.FakeStrictRedis(version=7)

        with mock.patch(
            "vehicles.management.import_live_vehicles.redis_client", redis_client
        ):
            with mock.patch(
                "vehicles.management.commands.import_bod_avl.redis_client", redis_client
            ):
                with mock.patch(
                    "vehicles.management.commands.import_bod_avl.Command.get_items",
                    return_value=items,
                ):
                    with self.assertNumQueries(41):
                        wait = command.update()
                    self.assertEqual(11, wait)

                    with self.assertNumQueries(0):
                        wait = command.update()
                    self.assertEqual(11, wait)

                    items[0]["RecordedAtTime"] = "2020-10-30T05:09:00+00:00"
                    with self.assertNumQueries(1):
                        command.update()

                    items[0]["RecordedAtTime"] = "2020-10-30T05:10:00+00:00"
                    items[0]["OriginAimedDepartureTime"] = "2020-10-30T09:00:00+00:00"
                    with self.assertNumQueries(1):
                        wait = command.update()

        journeys = VehicleJourney.objects.all()

        self.assertEqual(3, journeys.count())

        journey = journeys[1]
        self.assertEqual(journey.route_name, "843X")
        self.assertEqual(journey.destination, "Soho Road")
        self.assertEqual(journey.vehicle.reg, "SN56AFE")

        journey = journeys[2]
        self.assertEqual(journey.vehicle.operator_id, "HAMS")
        self.assertEqual(journey.vehicle.reg, "DW18HAM")
        self.assertEqual(journey.vehicle.reg, "DW18HAM")

        # test operator map
        with mock.patch("vehicles.views.redis_client", redis_client):
            with self.assertNumQueries(1):
                response = self.client.get("/vehicles.json?operator=HAMS")
        json = response.json()
        self.assertEqual(
            json,
            [
                {
                    "id": journey.vehicle_id,
                    "block": "503",
                    "coordinates": [0.285348, 51.2135],
                    "vehicle": {
                        "url": "/vehicles/hams-dw18-ham",
                        "name": "T2-1 - DW18 HAM",
                    },
                    "heading": 92.0,
                    "datetime": "2020-10-15T07:46:08Z",
                    "destination": "",
                    "service_id": self.service_c.id,
                    "service": {"line_name": "C", "url": "/services/c"},
                }
            ],
        )

        response = self.client.get("/operators/hams/map")
        self.assertContains(response, 'OPERATOR_ID="HAMS";')
        self.assertContains(response, "/operators/hams/map")

        # test other maps
        with mock.patch("vehicles.views.redis_client", redis_client):
            with self.assertNumQueries(0):
                response = self.client.get(
                    f"/vehicles.json?service={self.service_c.id},-2"
                )
            self.assertEqual(response.json(), json)

            with self.assertNumQueries(1):
                response = self.client.get("/vehicles.json")
            json = response.json()
            self.assertEqual(len(json), 3)

            # trip progress

            StopPoint.objects.create(
                atco_code="a", latlong="POINT (0.14 52.17)", active=True
            )
            StopPoint.objects.create(
                atco_code="b", latlong="POINT (0.15 52.20)", active=True
            )

            a = StopTime.objects.create(trip=self.trip, stop_id="a", arrival="25:00:00")
            StopTime.objects.create(trip=self.trip, stop_id="b", arrival="25:01:00")

            response = self.client.get(f"/vehicles.json?trip={self.trip.id}")
            json = response.json()
            self.assertEqual(len(json), 3)
            self.assertEqual(
                json[0]["progress"],
                {
                    "id": a.id,
                    "sequence": 0,
                    "prev_stop": a.stop_id,
                    "next_stop": "b",
                    "progress": 0.097,
                },
            )
            self.assertEqual(json[0]["delay"], 27962)

            with self.assertNumQueries(0):
                response = self.client.get("/vehicles.json?service=ff")
            self.assertEqual(response.status_code, 400)

            # test cache
            self.assertIs(False, cache.get("TGTC:843X:43000280301"))
            self.assertIsNone(cache.get("HAMS:C:2400103099"))
            self.assertIsNone(cache.get("WHIP:U:0500CCITY544"))

            # test history view
            whippet_journey = VehicleJourney.objects.get(vehicle__operator="WHIP")

            with time_machine.travel("2020-06-17"):
                with self.assertNumQueries(9):
                    response = self.client.get(whippet_journey.get_absolute_url())

                # with patch("django.core.cache.cache.set") as mock_cache_set:
                #     response = self.client.get(whippet_journey.get_absolute_url())
                #     mock_cache_set.assert_called_with(
                #         f"vehicle:{whippet_journey.vehicle_id}:dates",
                #         [date(2020, 6, 17)],
                #         86400.0
                #     )

            self.assertContains(
                response, '<a href="/services/u/vehicles?date=2020-06-17">UU</a>'
            )
            self.assertContains(
                response, f"""<a href="#journeys/{whippet_journey.id}">09:23</a>"""
            )
            self.assertContains(response, "<p>Great Yarmouth</p>")  # garage

            with self.assertNumQueries(5):
                response = self.client.get("/services/u/vehicles?date=2020-06-17")
            self.assertContains(response, "<p>Great Yarmouth</p>")  # garage

            response = self.client.get("/operators/whip/debug")
            self.assertContains(response, '<a href="/services/u">U</a>')
            self.assertContains(response, '<a href="/services/u/vehicles">')

    def test_handle_item(self):
        command = import_bod_avl.Command()
        command.source = self.source
        # command.get_operator.cache_clear()

        redis_client = fakeredis.FakeStrictRedis(version=7)

        with mock.patch(
            "vehicles.management.import_live_vehicles.redis_client", redis_client
        ):
            command.handle_item(
                {
                    "Extensions": {
                        "VehicleJourney": {"DriverRef": "105", "VehicleUniqueId": "104"}
                    },
                    "ItemIdentifier": "2cb5543a-add1-4e14-ae7a-a1ee730d9814",
                    "RecordedAtTime": "2020-11-28T12:58:25+00:00",
                    "ValidUntilTime": "2020-11-28T13:04:06.989808",
                    "MonitoredVehicleJourney": {
                        "LineRef": "146",
                        "BlockRef": "2",
                        "VehicleRef": "BB62_BUS",
                        "OperatorRef": "BDRB",
                        "DirectionRef": "inbound",
                        "VehicleLocation": {
                            "Latitude": "52.62269",
                            "Longitude": "1.296443",
                        },
                        "PublishedLineName": "146",
                        "VehicleJourneyRef": "146_20201128_12_58",
                    },
                }
            )
            command.save()
            command.handle_item(
                {
                    "RecordedAtTime": "2020-11-28T15:07:06+00:00",
                    "ItemIdentifier": "26ff29be-0d0a-4f5e-8160-bec0d831b681",
                    "ValidUntilTime": "2020-11-28T15:12:56.049069",
                    "MonitoredVehicleJourney": {
                        "LineRef": "146",
                        "DirectionRef": "inbound",
                        "PublishedLineName": "146",
                        "OperatorRef": "BDRB",
                        "DestinationRef": "390071066",
                        "VehicleLocation": {
                            "Longitude": "1.675893",
                            "Latitude": "52.328398",
                        },
                        "BlockRef": "2",
                        "VehicleJourneyRef": "146_20201128_12_58",
                        "VehicleRef": "BB62_BUS",
                    },
                }
            )
            command.save()

        journey = VehicleJourney.objects.get()
        self.assertEqual(journey.direction, "inbound")
        self.assertEqual(journey.destination, "Southwold")

        with mock.patch("vehicles.views.redis_client", redis_client):
            response = self.client.get(f"/journeys/{journey.id}.json")
        self.assertEqual(
            response.json(),
            {
                "code": "146_20201128_12_58",
                "current": True,
                "datetime": "2020-11-28T12:58:25Z",
                "destination": "Southwold",
                "direction": "inbound",
                "route_name": "146",
                "locations": [
                    {
                        "coordinates": [1.296442985534668, 52.62268829345703],
                        "datetime": "2020-11-28T12:58:25Z",
                        "delta": None,
                        "direction": None,
                    },
                    {
                        "coordinates": [1.675892949104309, 52.328399658203125],
                        "datetime": "2020-11-28T15:07:06Z",
                        "delta": None,
                        "direction": 142,
                    },
                ],
            },
        )

        vehicle = journey.vehicle

        with mock.patch("vehicles.views.redis_client", redis_client):
            with self.assertNumQueries(6):
                response = self.client.get(journey.get_absolute_url())
            self.assertContains(response, "146")
            self.assertContains(response, ">Southwold<")
            self.assertContains(response, f'<a href="#journeys/{journey.id}">Map</a>')

            with self.assertNumQueries(0):
                response = self.client.get(
                    "/vehicles.json?xmax=984.375&xmin=694.688&ymax=87.043&ymin=-89.261"
                )
            self.assertEqual(response.status_code, 400)

            with mock.patch("vehicles.views.redis_client.geosearch", return_value=[]):
                with self.assertNumQueries(0):
                    response = self.client.get(
                        "/vehicles.json?ymax=52.3&xmax=1.7&ymin=52.3&xmin=1.6"
                    )
            self.assertEqual(response.json(), [])

            with mock.patch(
                "vehicles.views.redis_client.geosearch", return_value=[vehicle.id]
            ):
                with self.assertNumQueries(1):
                    response = self.client.get(
                        "/vehicles.json?ymax=52.4&xmax=1.7&ymin=52.3&xmin=1.6"
                    )
            self.assertEqual(
                response.json(),
                [
                    {
                        "id": vehicle.id,
                        "block": "2",
                        "coordinates": [1.675893, 52.328398],
                        "vehicle": {
                            "url": "/vehicles/none-bb62-bus",
                            "name": "104 - BB62 BUS",
                        },
                        "heading": 142,
                        "datetime": "2020-11-28T15:07:06Z",
                        "destination": "Southwold",
                        "service": {"line_name": "146"},
                    }
                ],
            )

            with self.assertNumQueries(1):
                response = self.client.get("/vehicles.json")
            self.assertEqual(
                response.json(),
                [
                    {
                        "id": vehicle.id,
                        "block": "2",
                        "coordinates": [1.675893, 52.328398],
                        "vehicle": {
                            "url": "/vehicles/none-bb62-bus",
                            "name": "104 - BB62 BUS",
                        },
                        "heading": 142,
                        "datetime": "2020-11-28T15:07:06Z",
                        "destination": "Southwold",
                        "service": {"line_name": "146"},
                    }
                ],
            )

    def test_units(self):
        command = import_bod_avl.Command()
        command.source = self.source
        # command.get_operator.cache_clear()
        item = {
            "Extensions": {
                "VehicleJourney": {
                    "DriverRef": "65559",
                    "Operational": {
                        "TicketMachine": {
                            "JourneyCode": "1215",
                            "TicketMachineServiceCode": "m1",
                        }
                    },
                    "VehicleUniqueId": "2929",
                }
            },
            "ItemIdentifier": "c5da91a4-e7c8-45f2-aedb-1699997282dc",
            "RecordedAtTime": "2021-10-10T10:58:51+00:00",
            "ValidUntilTime": "2021-10-10T11:04:02.957172",
            "MonitoredVehicleJourney": {
                "LineRef": "m1",
                "BlockRef": "65559",
                "VehicleRef": "2929",
                "OperatorRef": "FBRI",
                "DirectionRef": "outbound",
                "DestinationRef": "010000008",
                "VehicleLocation": {"Latitude": "51.527146", "Longitude": "-2.596353"},
                "PublishedLineName": "m1",
                "VehicleJourneyRef": "m1_20211010_10_58",
            },
        }
        vehicle, created = command.get_vehicle(item)
        self.assertFalse(created)
        self.assertEqual(vehicle.name, "Jeff")

        journey = command.get_journey(item, vehicle)
        self.assertEqual("m1_20211010_10_58", journey.code)
        self.assertEqual("outbound", journey.direction)

        item["MonitoredVehicleJourney"]["VehicleRef"] = "11111"
        vehicle, created = command.get_vehicle(item)
        self.assertFalse(created)
        self.assertEqual(vehicle.code, "11111")
        # self.assertEqual(vehicle.fleet_code, "2929")

        item["MonitoredVehicleJourney"]["VehicleRef"] = "FBRI-502_-_DK09_DZH"
        vehicle, created = command.get_vehicle(item)
        self.assertTrue(created)

        self.assertEqual("DK09DZH", vehicle.reg)
        self.assertEqual("502_-_DK09_DZH", vehicle.code)
        self.assertEqual("502", vehicle.fleet_code)
        self.assertEqual("502", vehicle.fleet_number)

    @time_machine.travel("2021-03-05T14:20:40+00:00")
    def test_handle_extensions(self):
        command = import_bod_avl.Command()
        command.source = self.source
        # command.get_operator.cache_clear()

        item = {
            "Extensions": {
                "VehicleJourney": {
                    "DriverRef": "98119",
                    "Operational": {
                        "TicketMachine": {
                            "JourneyCode": "1426",
                            "TicketMachineServiceCode": "42",
                        }
                    },
                    "SeatedCapacity": "27",
                    "SeatedOccupancy": "0",
                    "VehicleUniqueId": "626",
                    "WheelchairCapacity": "1",
                    "OccupancyThresholds": "14,16",
                    "WheelchairOccupancy": "0",
                }
            },
            "ItemIdentifier": "4f61f0ab-0976-41e1-a899-044bb78618e4",
            "RecordedAtTime": "2021-03-05T14:26:43+00:00",
            "ValidUntilTime": "2021-03-05T14:32:12.638839",
            "MonitoredVehicleJourney": {
                "Bearing": "189.0",
                "LineRef": "42",
                "BlockRef": "52",
                "Occupancy": "seatsAvailable",
                "VehicleRef": "626",
                "OperatorRef": "GNEL",
                "DirectionRef": "inbound",
                "DestinationRef": "41000010WALB",
                "VehicleLocation": {
                    "Latitude": "55.084628",
                    "Longitude": "-1.586568",
                },
                "PublishedLineName": "42",
                "VehicleJourneyRef": "4237",
            },
        }

        redis_client = fakeredis.FakeStrictRedis(version=7)

        with mock.patch(
            "vehicles.management.import_live_vehicles.redis_client", redis_client
        ):
            command.handle_item(item)
            command.save()

        vehicle = Vehicle.objects.get(code="626")

        with mock.patch("vehicles.views.redis_client", redis_client):
            response = self.client.get("/vehicles.json")

        self.assertEqual(
            response.json(),
            [
                {
                    "id": vehicle.id,
                    "block": "52",
                    "coordinates": [-1.586568, 55.084628],
                    "vehicle": {
                        "url": "/vehicles/none-626",
                        "name": "626",
                    },
                    "heading": 189.0,
                    "datetime": "2021-03-05T14:26:43Z",
                    "destination": "",
                    "service": {"line_name": "42"},
                    "seats": "27 free",
                    "wheelchair": "free",
                }
            ],
        )

    @time_machine.travel("2021-05-08T13:00+00:00")
    @mock.patch(
        "vehicles.management.import_live_vehicles.redis_client",
        fakeredis.FakeStrictRedis(version=7),
    )
    def test_invalid_location(self):
        command = import_bod_avl.Command()
        command.source = self.source
        # command.get_operator.cache_clear()

        item = {
            "RecordedAtTime": "2021-05-08T12:54:36+00:00",
            "ItemIdentifier": "db82c74d-e2ac-48f4-8963-4cea2d706b6d",
            "ValidUntilTime": "2021-05-08T12:59:47.376621",
            "MonitoredVehicleJourney": {
                "LineRef": "8",
                "DirectionRef": "OUTBOUND",
                "PublishedLineName": "8",
                "OperatorRef": "SCHI",
                "OriginRef": "670030036",
                "OriginName": "Stratton Road",
                "DestinationRef": "670030036",
                "DestinationName": "Stratton Road",
                "OriginAimedDepartureTime": "2021-05-08T12:30:00+00:00",
                "VehicleLocation": {
                    "Longitude": "149.2244263",
                    "Latitude": "87.8245926",  # greater than 85.05112878
                },
                "Bearing": "0.0",
                "VehicleJourneyRef": "2029",
                "VehicleRef": "SCHI-21210",
            },
            "Extensions": None,
        }
        command.handle_item(item)
        command.save()

        journey = VehicleJourney.objects.get()
        self.assertEqual(item, journey.vehicle.latest_journey_data)

        item = {
            "Extensions": None,
            "ItemIdentifier": "1708f9be-0585-4b68-bc2d-c6fb84ebb983",
            "MonitoredVehicleJourney": {
                "DestinationName": "Theatre Royal",
                "DestinationRef": "036006218220",
                "DirectionRef": "OUTBOUND",
                "LineRef": "WindsorEtonCircular",
                "OperatorRef": "Awan",
                "OriginAimedDepartureTime": "2022-07-09T17:00:00+00:00",
                "OriginName": "Theatre Royal",
                "OriginRef": "036006218220",
                "PublishedLineName": "WindsorEtonCircular",
                "VehicleLocation": {"Latitude": "0.0", "Longitude": "0.0"},
                "VehicleRef": None,
            },
            "RecordedAtTime": "2022-07-09T17:03:26+00:00",
            "ValidUntilTime": "2022-07-11T00:20:56.514340",
        }
        command.handle_item(item)

    def test_tfl(self):
        command = import_bod_avl.Command()
        command.source = self.source
        # command.get_operator.cache_clear()

        also = Operator.objects.create(noc="ALSO", name="Arriva London North")
        alno = Operator.objects.create(noc="ALNO", name="Arriva London South")
        OperatorCode.objects.create(operator=also, source=self.source, code="TFLO"),
        OperatorCode.objects.create(operator=alno, source=self.source, code="TFLO"),

        service = Service.objects.create(line_name="498", current=True)
        Route.objects.create(line_name="498", service=service, source=self.source)
        service.operator.set([also, alno])

        livery = Livery.objects.create(id=262, name="TfL", published=True)

        item = {
            "RecordedAtTime": "2022-05-23T12:15:47+00:00",
            "ItemIdentifier": "701f4d34-e231-40c8-b303-ee2500e05baa",
            "ValidUntilTime": "2022-05-23T12:21:28.747249",
            "MonitoredVehicleJourney": {
                "LineRef": "124",
                "DirectionRef": "2",
                "PublishedLineName": "498",
                "OperatorRef": "TFLO",
                # "OriginRef": "1500BD1",
                "OriginName": "Brentwood Sainsbury s",
                # "DestinationRef": "1500IM1041",
                "DestinationName": "Holiday Inn",
                "OriginAimedDepartureTime": "2022-05-23T12:08:00+00:00",
                "VehicleLocation": {"Longitude": "0.285472", "Latitude": "51.61536"},
                "Bearing": "225.0",
                "VehicleJourneyRef": "393473",
                "VehicleRef": "SN16OLO",
            },
            "Extensions": None,
        }

        redis_client = fakeredis.FakeStrictRedis(version=7)
        with mock.patch(
            "vehicles.management.import_live_vehicles.redis_client", redis_client
        ):
            command.handle_item(item)
            command.save()

        journey = VehicleJourney.objects.get()

        self.assertEqual(journey.service, service)

        vehicle = journey.vehicle
        self.assertEqual(vehicle.livery, livery)
        self.assertEqual(vehicle.reg, "SN16OLO")

    @mock.patch(
        "vehicles.management.import_live_vehicles.redis_client",
        fakeredis.FakeStrictRedis(version=7),
    )
    def test_ambiguous_operator(self):
        command = import_bod_avl.Command()
        command.source = self.source
        # command.get_operator.cache_clear()

        vehicle = Vehicle.objects.create(
            operator_id="TNXB", code="4407", fleet_code="4407", fleet_number=4407
        )

        command.handle_item(
            {
                "RecordedAtTime": "2022-05-23T09:19:56+00:00",
                "ItemIdentifier": "8fa84dbe-e4f7-45ed-abbc-8709de59b7e9",
                "ValidUntilTime": "2022-05-23T12:36:03.702621",
                "MonitoredVehicleJourney": {
                    "LineRef": "DEAD",
                    "FramedVehicleJourneyRef": {
                        "DataFrameRef": "2022-05-23",
                        "DatedVehicleJourneyRef": "0",
                    },
                    "PublishedLineName": "DEAD",
                    "OperatorRef": "CV",
                    "VehicleLocation": {
                        "Longitude": "-1.505448",
                        "Latitude": "52.421363",
                    },
                    "Bearing": "205.0",
                    "VehicleRef": "CV-4407",
                },
                "Extensions": None,
            }
        )
        command.handle_item(
            {
                "RecordedAtTime": "2022-05-23T12:30:32+00:00",
                "ItemIdentifier": "7da087e7-0143-4738-9951-36eb6b190932",
                "ValidUntilTime": "2022-05-23T12:36:03.780564",
                "MonitoredVehicleJourney": {
                    "LineRef": "C19",
                    "FramedVehicleJourneyRef": {
                        "DataFrameRef": "2022-05-23",
                        "DatedVehicleJourneyRef": "15",
                    },
                    "PublishedLineName": "C19",
                    "OperatorRef": "CV",
                    "VehicleLocation": {
                        "Longitude": "-1.52882",
                        "Latitude": "52.392785",
                    },
                    "Bearing": "210.0",
                    "VehicleRef": "CV-840",
                },
                "Extensions": None,
            }
        )
        command.save()

        journey_1, journey_2 = VehicleJourney.objects.all()

        self.assertEqual(journey_1.vehicle, vehicle)
        self.assertEqual(
            journey_1.vehicle.operator.name, "National Express West Midlands"
        )

        self.assertEqual(journey_2.vehicle.reg, "")
        self.assertEqual(journey_2.vehicle.operator.name, "National Express Coventry")

    @mock.patch(
        "vehicles.management.import_live_vehicles.redis_client",
        fakeredis.FakeStrictRedis(version=7),
    )
    def test_timezone_correction(self):
        command = import_bod_avl.Command()
        command.source = self.source
        # command.get_operator.cache_clear()

        command.handle_item(
            {
                "Extensions": {
                    "VehicleJourney": {
                        "Operational": {
                            "TicketMachine": {
                                "JourneyCode": "0000",
                                "TicketMachineServiceCode": "140_new",
                            }
                        },
                        "VehicleUniqueId": "KX59 CYY",
                    }
                },
                "ItemIdentifier": "6429b06c-9503-4338-b2b7-848c067111d2",
                "RecordedAtTime": "2022-06-08T08:06:14+00:00",
                "ValidUntilTime": "2022-06-08T08:11:45.252372",
                "MonitoredVehicleJourney": {
                    "LineRef": "140",
                    "BlockRef": "5",
                    "OriginRef": "100000021770",
                    "OriginName": "Station_Forecourt",
                    "VehicleRef": "B15",
                    "OperatorRef": "LTLS",
                    "DirectionRef": "outbound",
                    "DestinationRef": "100051712",
                    "DestinationName": "Railway_Station",
                    "VehicleLocation": {
                        "Latitude": "53.100548",
                        "Longitude": "-1.369669",
                    },
                    "PublishedLineName": "140",
                    "FramedVehicleJourneyRef": {
                        "DataFrameRef": "2022-06-08",
                        "DatedVehicleJourneyRef": "0905",
                    },
                    "OriginAimedDepartureTime": "2022-06-08T09:05:00+00:00",
                    "DestinationAimedArrivalTime": "2022-06-08T10:00:00+00:00",
                },
            }
        )
        journey = VehicleJourney.objects.get(route_name="140")
        self.assertEqual(journey.code, "0905")
        self.assertEqual(str(journey.datetime), "2022-06-08 08:05:00+00:00")

        command.handle_item(
            {
                "Extensions": {
                    "VehicleJourney": {
                        "Operational": {
                            "TicketMachine": {
                                "JourneyCode": "1000",
                                "TicketMachineServiceCode": "K91",
                            }
                        },
                        "VehicleUniqueId": "33318",
                    }
                },
                "ItemIdentifier": "c711ef6f-9277-459b-8ec9-dad2bab92eb8",
                "RecordedAtTime": "2022-06-08T08:59:32+00:00",
                "ValidUntilTime": "2022-06-08T09:05:01.790363",
                "MonitoredVehicleJourney": {
                    "LineRef": "91",
                    "BlockRef": "521802",
                    "OriginRef": "0800COC30493",
                    "OriginName": "Truro_College_Bus_Park",
                    "VehicleRef": "FCWL-33318-WK18CHD",
                    "OperatorRef": "FCWL",
                    "DirectionRef": "outbound",
                    "DestinationRef": "0800COC31523",
                    "DestinationName": "Newquay_bus_station",
                    "VehicleLocation": {
                        "Latitude": "50.263596",
                        "Longitude": "-5.100816",
                    },
                    "PublishedLineName": "91",
                    "FramedVehicleJourneyRef": {
                        "DataFrameRef": "2022-06-08",
                        "DatedVehicleJourneyRef": "9",
                    },
                    "OriginAimedDepartureTime": "2022-06-08T10:00:00+00:00",
                    "DestinationAimedArrivalTime": "2022-06-08T11:22:00+00:00",
                },
            }
        )
        journey = VehicleJourney.objects.get(route_name="91")
        self.assertEqual(journey.code, "9")
        self.assertEqual(str(journey.datetime), "2022-06-08 09:00:00+00:00")

        command.handle_item(
            {
                "Extensions": {
                    "VehicleJourney": {
                        "Operational": {
                            "TicketMachine": {
                                "JourneyCode": "0000",
                                "TicketMachineServiceCode": "A4_AB",
                            }
                        },
                        "VehicleUniqueId": "006",
                    }
                },
                "ItemIdentifier": "9c6035e0-d8db-473c-b74b-b33a96305eea",
                "RecordedAtTime": "2022-06-07T22:54:07+00:00",
                "ValidUntilTime": "2022-06-07T22:59:21.477067",
                "MonitoredVehicleJourney": {
                    "Bearing": "278.0",
                    "LineRef": "A4",
                    "BlockRef": "906",
                    "OriginRef": "0190NSZ01245",
                    "OriginName": "Airport_Terminal",
                    "VehicleRef": "BBCL-A506",
                    "OperatorRef": "BBCL",
                    "DirectionRef": "inbound",
                    "DestinationRef": "0180BAC01279",
                    "DestinationName": "Dorchester_Street",
                    "VehicleLocation": {
                        "Latitude": "51.38666",
                        "Longitude": "-2.709386",
                    },
                    "PublishedLineName": "A4",
                    "FramedVehicleJourneyRef": {
                        "DataFrameRef": "2022-06-07",
                        "DatedVehicleJourneyRef": "2022",
                    },
                    "OriginAimedDepartureTime": "2022-06-07T00:00:00+00:00",
                    "DestinationAimedArrivalTime": "2022-06-07T00:49:00+00:00",
                },
            }
        )
        journey = VehicleJourney.objects.get(route_name="A4")
        self.assertEqual(journey.code, "2022")
        # TODO: should realise "0000" is midnight and adjust departure time
        self.assertEqual(str(journey.datetime), "2022-06-07 00:00:00+00:00")

    def test_debugger(self):
        service = Service.objects.create(line_name="21C")
        service.operator.add("NIBS")
        route = Route.objects.create(service=service, source=self.source)
        calendar = Calendar.objects.create(
            mon=True,
            tue=True,
            wed=True,
            thu=True,
            fri=True,
            sat=True,
            sun=True,
            start_date="2021-01-01",
        )
        trip = Trip.objects.create(
            start="18:08:000",
            end="19:00:00",
            route=route,
            calendar=calendar,
            inbound=True,
        )

        response = self.client.post(
            "/vehicles/debug",
            {
                "data": """{
"Extensions": null,
"ItemIdentifier": "86cc7f7f-d80d-4e49-beae-0ca20f90ed68",
"RecordedAtTime": "2021-12-30T18:02:49+00:00",
"ValidUntilTime": "2021-12-30T18:08:26.472197",
"MonitoredVehicleJourney": {
"Bearing": "328.0",
"LineRef": "21C",
"BlockRef": "7550",
"VehicleRef": "nibs_443_-_YX10_FEU",
"OperatorRef": "NIBS",
"DirectionRef": "inbound",
"VehicleLocation": {
"Latitude": "51.712366",
"Longitude": "0.245008"
},
"PublishedLineName": "21C",
"VehicleJourneyRef": "1808"
}
}"""
            },
        )

        self.assertEqual(response.context["result"]["journey"].code, "1808")
        self.assertEqual(response.context["result"]["journey"].service, service)
        self.assertEqual(response.context["result"]["journey"].trip, trip)

    def test_debugger_error(self):
        response = self.client.post("/vehicles/debug", {"data": "trdgserawse/"})
        self.assertIn(
            "Expecting value: line 1 column 1 (char 0)",
            str(response.context["form"].errors),
        )
