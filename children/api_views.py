from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.urls import reverse
from django.core import signing

from .models import Child
from questionnaires.logic import get_pending_questionnaires
@require_GET
def child_by_uid(request):
    uid = request.GET.get("uid")

    # 1. 檢查有沒有傳 UID
    if not uid:
        return JsonResponse(
            {
                "success": False,
                "message": "缺少 uid",
            },
            status=400,
        )

    # 2. 用 UID 找兒童
    try:
        child = Child.objects.get(uid=uid)
    except Child.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "message": "找不到此 UID 對應的兒童",
            },
            status=404,
        )

    # 3. 找出這個兒童目前需要填寫的問卷
    pending = get_pending_questionnaires(child)

    # 4. 先直接把結果整理成 JSON
    questionnaires = []

    for item in pending:
        state = item["state"]

        if state == "in_progress":
            state_label = "未完成"
        elif state == "unrecorded":
            state_label = "未記錄"
        else:
            state_label = state

        version = item["version"]

        # 建立 APP -> Web 的短效簽章 Token
        token = signing.dumps(
            {
                "uid": child.uid,
                "version_id": version.id,
            },
            salt="questionnaire-fill",
        )

        fill_path = reverse(
            "questionnaires:fill",
            kwargs={"version_id": version.id}
        )

        fill_url = request.build_absolute_uri(
            f"{fill_path}?token={token}"
        )
        questionnaires.append({
            "version_id": version.id,
            "questionnaire_name": version.questionnaire.name,
            "state": state,
            "state_label": state_label,
            "fill_url": fill_url,
        })

    # 5. 回傳給 APP
    return JsonResponse(
        {
            "success": True,
            "child": {
                "uid": child.uid,
                "birth_date": (
                    child.birth_date.isoformat()
                    if child.birth_date
                    else None
                ),
                "age_months": child.age_months(),
            },
            "questionnaires": questionnaires,
        },
        json_dumps_params={
            "ensure_ascii": False
        }
    )