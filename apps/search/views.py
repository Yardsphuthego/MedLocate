from math import isfinite
from urllib.parse import urlencode
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from apps.accounts.access import SEARCH_ROLES, require_staff
from apps.accounts.models import User
from apps.facilities.models import Facility
from apps.medicines.models import Medicine
from .services import search_stock


@login_required
def medicine_search(request):
    require_staff(request.user, SEARCH_ROLES)
    data = request.POST if request.method == 'POST' else request.GET
    query = data.get('q', '').strip()[:160]
    area = data.get('area', '').strip()[:160]
    lat = lon = None
    error = ''
    # Coordinates are accepted only in a POST body and are never stored.
    if request.method == 'POST' and (data.get('lat') or data.get('lon')):
        try:
            lat, lon = float(data.get('lat')), float(data.get('lon'))
            if not (isfinite(lat) and isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
        except (TypeError, ValueError):
            lat = lon = None
            error = 'Invalid coordinates. Results are shown without distance.'
    origin = data.get('origin', '')
    facilities = Facility.objects.filter(status=Facility.Status.ACTIVE).order_by('name')
    if origin:
        start = facilities.filter(pk=int(origin)).first() if origin.isdecimal() else None
        if start:
            lat, lon = start.latitude, start.longitude
    results = search_stock(query, lat, lon) if query else []
    if area:
        results = [r for r in results if area.casefold() in (r['item'].facility.address + ' ' + r['item'].facility.name).casefold()]
    for row in results:
        facility = row['item'].facility
        if facility.latitude is not None and facility.longitude is not None:
            dest = f'{facility.latitude},{facility.longitude}'
            row['directions_url'] = 'https://www.google.com/maps/dir/?' + urlencode({'api': 1, 'destination': dest})
            row['map_url'] = 'https://www.openstreetmap.org/?' + urlencode({'mlat': str(facility.latitude), 'mlon': str(facility.longitude)}) + '#map=16/' + dest.replace(',', '/')
    return render(request, 'search/search.html', {'query': query, 'area': area, 'origin': origin, 'facilities': facilities, 'results': results, 'error': error})


@login_required
def medicine_identify(request):
    require_staff(request.user, SEARCH_ROLES | {User.Role.PHARMACY})
    query = request.GET.get('code', '').strip()[:160]
    matches = Medicine.objects.filter(active=True).filter(
        Q(barcode__iexact=query) | Q(code__iexact=query) | Q(name__icontains=query) | Q(generic_name__icontains=query)
    ).distinct()[:20] if query else []
    return render(request, 'search/identify.html', {'query': query, 'matches': matches, 'can_search': request.user.primary_role in SEARCH_ROLES})
