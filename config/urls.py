from children import api_views

"""M04 URL 設定。"""

from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),

    # APP -> Web：透過 UID 查詢兒童
    path(
        "api/child/",
        api_views.child_by_uid,
        name="child_by_uid",
    ),

    # 原本問卷系統
    path("", include("questionnaires.builder_urls")),
    path("", include("questionnaires.urls")),
]