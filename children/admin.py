from django.contrib import admin

from .models import Child


@admin.register(Child)
class ChildAdmin(admin.ModelAdmin):
    list_display = (
        "name", "national_id", "birth_date", "age_months_display",
        "tracking_status", "guardian", "is_active",
    )
    list_filter = ("is_active", "tracking_status")
    search_fields = ("name", "national_id", "medical_no")
    autocomplete_fields = ("guardian",)
    readonly_fields = ("created_at",)

    @admin.display(description="目前月齡")
    def age_months_display(self, obj):
        return f"{obj.age_months()} 個月"
