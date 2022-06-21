from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, pagination
from rest_framework.exceptions import APIException

from bustimes.models import Trip
from vehicles.models import Vehicle, Livery, VehicleType, VehicleJourney
from . import filters, serializers


class BadException(APIException):
    status_code = 400


class LimitedPagination(pagination.LimitOffsetPagination):
    default_limit = 20
    max_limit = 20


class VehicleViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Vehicle.objects.select_related(
        "operator", "vehicle_type", "livery"
    ).order_by("id")
    serializer_class = serializers.VehicleSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = filters.VehicleFilter


class LiveryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Livery.objects.all()
    serializer_class = serializers.LiverySerializer


class VehicleTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = VehicleType.objects.all()
    serializer_class = serializers.VehicleTypeSerializer


class TripViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Trip.objects.select_related("route__service").prefetch_related(
        "stoptime_set__stop__locality"
    )
    serializer_class = serializers.TripSerializer
    pagination_class = LimitedPagination

    def list(self, request):
        raise BadException(detail="Listing all trips is not allowed")


class VehicleJourneyViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = VehicleJourney.objects.select_related("vehicle")
    serializer_class = serializers.VehicleJourneySerializer
    pagination_class = LimitedPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = filters.VehicleJourneyFilter

    def list(self, request):
        if (
            not request.GET.get("trip")
            and not request.GET.get("vehicle")
            and not request.GET.get("service")
        ):
            raise BadException(
                detail="Listing all journeys without filtering by trip, vehicle, or service is not allowed"
            )
        return super().list(request)
