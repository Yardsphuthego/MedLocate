from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import SearchHistory


@admin.register(SearchHistory)
class SearchHistoryAdmin(ModelAdmin):
    pass
