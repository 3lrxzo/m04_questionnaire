from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin

from accounts.forms import ChildForm
from children.models import Child

from .logic import get_pending_questionnaires
from .models import QuestionnaireResponse, QuestionnaireVersion

STATE_LABEL = {"in_progress": "未完成", "unrecorded": "未記錄"}


def landing(request):
    """首頁：選擇進入家長端或醫護人員端。"""
    return render(request, "questionnaires/landing.html")


def _children_for(request):
    """使用者可看到的兒童。

    第一階段：超級使用者／幕僚看全部（方便測試），一般帳號看自己名下的。
    院方 APP 介接後，家長身分會直接對應到 guardian，這裡就只留下後者。
    """
    qs = Child.objects.filter(is_active=True)
    if request.user.is_superuser or request.user.is_staff:
        return qs
    return qs.filter(guardian=request.user)


@login_required
def parent_home(request):
    """家長端主頁：名下孩子清單 + 新增孩子入口。"""
    children = list(_children_for(request))
    if not children:
        return redirect("questionnaires:child-add")
    return render(request, "questionnaires/parent_home.html", {"children": children})


@login_required
def child_add(request):
    """家長登錄孩子資料。"""
    if request.method == "POST":
        form = ChildForm(request.POST)
        if form.is_valid():
            child = form.save(commit=False)
            child.guardian = request.user
            child.save()
            return redirect("questionnaires:child-home", child_id=child.id)
    else:
        form = ChildForm()
    return render(request, "questionnaires/child_form.html", {"form": form})


@login_required
def child_edit(request, child_id):
    """Allow a parent to update a child's profile without exposing other children."""
    child = get_object_or_404(_children_for(request), pk=child_id)
    if request.method == "POST":
        form = ChildForm(request.POST, instance=child)
        if form.is_valid():
            form.save()
            return redirect("questionnaires:child-home", child_id=child.id)
    else:
        form = ChildForm(instance=child)
    return render(request, "questionnaires/child_form.html", {
        "form": form, "child": child, "editing": True,
    })


@login_required
def child_home(request, child_id):
    """單一健康問卷入口（正式文件（五）（七））。

    由系統依適用規則決定「當次應呈現」哪些問卷，家長不需知道 version id。
    同時顯示未完成／未記錄狀態與已完成的歷史紀錄。
    """
    child = get_object_or_404(_children_for(request), pk=child_id)

    pending = []
    for item in get_pending_questionnaires(child):
        version = item["version"]
        pending.append({
            "version": version,
            "questionnaire_name": version.questionnaire.name,
            "tier": version.questionnaire.tier,
            "state": item["state"],
            "state_label": STATE_LABEL.get(item["state"], item["state"]),
        })

    completed = (
        QuestionnaireResponse.objects
        .filter(child=child, status=QuestionnaireResponse.Status.COMPLETED)
        .select_related("version__questionnaire")
        .order_by("-completed_at")[:20]
    )

    return render(request, "questionnaires/child_home.html", {
        "child": child,
        "pending": pending,
        "completed": completed,
    })


@xframe_options_sameorigin  # 供編輯器右欄的預覽 iframe 內嵌（同源）
@login_required
def fill_page(request, version_id):
    """家長端填答頁的外殼。實際的題目呈現與分支邏輯在前端 Vue 元件，
    schema 由 /api/questionnaires/<id>/schema/ 載入。

    ?preview=1 ：預覽模式，允許看草稿、不寫入任何填答（正式文件（三））。
    ?child=<id>：指定填答對象；正式介接後改由登入身分推導。
    """
    preview = request.GET.get("preview") == "1"

    version_qs = QuestionnaireVersion.objects.select_related("questionnaire")
    if not preview:
        version_qs = version_qs.filter(status=QuestionnaireVersion.Status.PUBLISHED)
    version = get_object_or_404(version_qs, pk=version_id)

    return render(request, "questionnaires/fill.html", {
        "version": version,
        "preview": preview,
        "child_id": request.GET.get("child", ""),
    })
