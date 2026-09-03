from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from apps.accounts.models import User
from .models import SearchHistory
from .services import search_stock


def medicine_search(request):
    if request.user.is_authenticated and request.user.primary_role != User.Role.PATIENT:
        raise PermissionDenied

    query = request.GET.get("q", "").strip()
    lat = request.GET.get("lat") or None
    lon = request.GET.get("lon") or None
    results = []
    error = ""
    if query:
        try:
            results = search_stock(query, lat, lon)
        except (TypeError, ValueError):
            error = "Location coordinates were invalid; results are shown without distance."
            results = search_stock(query)
        if request.user.is_authenticated:
            profile = getattr(request.user, "patient_profile", None)
            if profile is None or profile.retain_search_history:
                SearchHistory.objects.create(patient=request.user, query=query)
    return render(request, "search/search.html", {"query": query, "results": results, "error": error})
