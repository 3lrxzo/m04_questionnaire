from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.db.models import Q


admin.site.unregister(User)


@admin.register(User)
class RestrictedUserAdmin(UserAdmin):
    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        if obj is not None and (obj.is_staff or obj.is_superuser):
            return request.user.is_superuser
        return super().has_change_permission(request, obj)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not request.user.is_superuser:
            queryset = queryset.exclude(Q(is_staff=True) | Q(is_superuser=True))
        return queryset

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser:
            return fieldsets
        protected_fields = {
            "is_staff", "is_superuser", "groups", "user_permissions", "date_joined",
        }

        def flatten(fields):
            for field in fields:
                if isinstance(field, (tuple, list)):
                    yield from flatten(field)
                else:
                    yield field

        return tuple(
            fieldset for fieldset in fieldsets
            if not protected_fields.intersection(flatten(fieldset[1]["fields"]))
        )
