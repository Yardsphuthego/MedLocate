from django.urls import path
from .views import medicine_search

urlpatterns = [path("search/", medicine_search, name="medicine_search")]
