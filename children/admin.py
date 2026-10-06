from django.conf import settings
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path

from .models import Child
from .services.golden_baby_sync import sync_children


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

    change_list_template = "admin/children/child/change_list.html"

    @admin.display(description="目前月齡")
    def age_months_display(self, obj):
        return f"{obj.age_months()} 個月"

    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path(
                "golden-baby-sync/",
                self.admin_site.admin_view(self.golden_baby_sync_view),
                name="children_child_golden_baby_sync",
            ),
        ]

        return custom_urls + urls

    def golden_baby_sync_view(self, request):
        # 真正執行同步
        if request.method == "POST":
            try:
                result = sync_children(dry_run=False)

                self.message_user(
                    request,
                    (
                        f"金寶貝同步完成："
                        f"新增 {result['created']} 筆、"
                        f"更新 {result['updated']} 筆、"
                        f"略過 {result['skipped']} 筆。"
                    ),
                    level=messages.SUCCESS,
                )

                return redirect("admin:children_child_changelist")

            except Exception as exc:
                self.message_user(
                    request,
                    f"金寶貝同步失敗：{exc}",
                    level=messages.ERROR,
                )

                return redirect("admin:children_child_changelist")

        # GET 只做預覽，不修改資料庫
        try:
            result = sync_children(dry_run=True)
            error = None
        except Exception as exc:
            result = None
            error = str(exc)

        context = {
            **self.admin_site.each_context(request),
            "title": "金寶貝兒童資料同步",
            "result": result,
            "error": error,
            "opts": self.model._meta,

            # 顯示目前金寶貝 API 模式
            "golden_baby_mock": settings.GOLDEN_BABY_API_MOCK,
        }

        return render(
            request,
            "admin/children/child/golden_baby_sync.html",
            context,
        )