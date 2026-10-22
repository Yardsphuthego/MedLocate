from django.urls import path
from .views import medicine_search, medicine_identify

urlpatterns = [
    path("identify/", medicine_identify, name="medicine_identify"),path("search/", medicine_search, name="medicine_search")]
