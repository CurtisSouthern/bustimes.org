from django.test import TestCase
from .models import (
    Region, AdminArea, District, Locality, LiveSource, Operator, Service, StopPoint
)


class RegionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create some regions
        cls.midlands = Region.objects.create(pk='NM', name='North Midlands')
        cls.east = Region.objects.create(pk='ME', name='Middle East')
        cls.ireland = Region.objects.create(pk='IE', name='Ireland')

    def test_string(self):
        self.assertEqual(str(self.midlands), 'North Midlands')

    def test_the(self):
        "Regions with certain names should have 'the' prepended, and others shouldn't."
        self.assertEqual(self.midlands.the(), 'the North Midlands')
        self.assertEqual(self.east.the(), 'the Middle East')
        self.assertEqual(self.ireland.the(), 'Ireland')

    def test_get_absolute_url(self):
        self.assertEqual(self.midlands.get_absolute_url(), '/regions/NM')


class LiveSourceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.yorkshire = LiveSource.objects.get_or_create(name='Y')[0]
        cls.london = LiveSource.objects.get_or_create(name='TfL')[0]
        cls.dummy = LiveSource.objects.get_or_create(name='foo')[0]

    def test_string(self):
        self.assertEqual(str(self.yorkshire), 'Yorkshire')
        self.assertEqual(str(self.london), 'Transport for London')
        self.assertEqual(str(self.dummy), 'foo')


class LocalityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.midlands = Region.objects.create(pk='NM', name='North Midlands')
        cls.dorset = AdminArea.objects.create(pk='4', atco_code=2, region=cls.midlands, name='Dorset')

        cls.north_yorkshire = District.objects.create(pk='2', admin_area=cls.dorset, name='North Yorkshire')

        cls.brinton = Locality.objects.create(pk='1', admin_area=cls.dorset, name='Brinton')
        cls.york = Locality.objects.create(pk='2', admin_area=cls.dorset, name='York', qualifier_name='York')

    def test_get_qualified_name(self):
        self.assertEqual(self.brinton.get_qualified_name(), 'Brinton')
        self.assertEqual(self.york.get_qualified_name(), 'York, York')

    def test_string(self):
        self.assertEqual(str(self.brinton), 'Brinton')
        self.assertEqual(str(self.york), 'York')

        self.assertEqual(str(self.brinton.admin_area), 'Dorset')


class OperatorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.north = Region.objects.create(pk='N', name='North')
        cls.chariots = Operator.objects.create(pk='CHAR', region=cls.north,
                                               name='Ainsley\'s Chariots')

    def test_get_qualified_name(self):
        self.assertEqual(str(self.chariots), 'Ainsley\'s Chariots')


class ServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.region = Region.objects.create(id='L', name='London')
        cls.london_service = Service.objects.create(
            service_code='tfl_8-N41-_-y05', net='tfl', line_name='N41',
            date='2000-1-1', region_id='L'
        )

    def test_str(self):
        self.assertEqual(str(self.london_service), 'N41')

        self.london_service.line_name = ''
        self.assertEqual(str(self.london_service), 'tfl_8-N41-_-y05')

    def test_get_a_mode(self):
        self.assertEqual(self.london_service.get_a_mode(), 'A ')

        self.london_service.mode = 'Underground'
        self.assertEqual(self.london_service.get_a_mode(), 'An Underground')

    def test_get_traveline_url(self):
        self.assertIsNone(self.london_service.get_traveline_url())

        self.london_service.mode = 'bus'
        self.assertEqual(self.london_service.get_traveline_url(),
                         'https://tfl.gov.uk/bus/timetable/N41/')

        self.london_service.region_id = 'Y'
        self.assertEqual('http://www.yorkshiretravel.net/', self.london_service.get_traveline_url()[:31])

    def test_get_operator_number(self):
        self.assertIsNone(self.london_service.get_operator_number('MGBD'))

        self.assertEqual('11', self.london_service.get_operator_number('MEGA'))
        self.assertEqual('11', self.london_service.get_operator_number('MBGD'))

        self.assertEqual('12', self.london_service.get_operator_number('NATX'))
        self.assertEqual('12', self.london_service.get_operator_number('NXSH'))
        self.assertEqual('12', self.london_service.get_operator_number('NXAP'))

        self.assertEqual('41', self.london_service.get_operator_number('BHAT'))
        self.assertEqual('53', self.london_service.get_operator_number('ESYB'))
        self.assertEqual('20', self.london_service.get_operator_number('WAIR'))
        self.assertEqual('18', self.london_service.get_operator_number('TVSN'))


class StopPointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ballyblack_church = StopPoint.objects.create(atco_code='700000002498', locality_centre=False, active=True,
                                                         common_name='Ballyblack Church', town='Ballyblack')

    def test_get_qualified_name(self):
        self.assertEqual('Ballyblack Church', self.ballyblack_church.get_qualified_name())
        self.ballyblack_church.common_name = 'Methodist Church'
        self.assertEqual('Ballyblack Methodist Church', self.ballyblack_church.get_qualified_name())
