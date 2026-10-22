from math import asin, cos, radians, sin, sqrt
from django.db.models import Q
from django.utils import timezone
from apps.inventory.models import InventoryItem
from apps.medicines.models import Medicine


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(lambda value: radians(float(value)), (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(min(1, max(0, a))))


def search_stock(query, latitude=None, longitude=None):
    medicines = Medicine.objects.filter(active=True).filter(
        Q(name__icontains=query) | Q(generic_name__icontains=query) |
        Q(code__iexact=query) | Q(barcode__iexact=query) | Q(aliases__name__icontains=query)
    ).distinct()
    items = InventoryItem.objects.filter(
        medicine__in=medicines, quantity__gt=0, facility__status="active"
    ).filter(Q(expiry_date__isnull=True) | Q(expiry_date__gte=timezone.localdate())).select_related("facility", "medicine")
    results = []
    for item in items:
        distance = None
        if latitude is not None and longitude is not None and item.facility.latitude is not None:
            distance = haversine_km(latitude, longitude, item.facility.latitude, item.facility.longitude)
        results.append({"item": item, "distance_km": distance})
    freshness_order = {"fresh": 0, "aging": 1, "stale": 2}
    if latitude is not None and longitude is not None:
        return sorted(results, key=lambda row: (row["distance_km"] is None, row["distance_km"] or 0))
    return sorted(results, key=lambda row: (freshness_order[row["item"].freshness], row["distance_km"] is None, row["distance_km"] or 0))
