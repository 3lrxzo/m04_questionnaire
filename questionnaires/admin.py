"""問卷管理後台。

第一階段的後台就用客製化的 Django Admin（《開發規劃書》第七節 Phase 1），
Phase 2 再視情況改成 HTMX 頁面。

三層結構（版本 → 題組 → 題目 → 選項／分支）超過 Django 原生 inline 能
巢狀的深度，因此採「每一層各自有 changelist，並用 list_filter 往上收斂」
的做法，不額外引入 nested-inline 套件。
"""

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.html import format_html

from .models import (
    Answer,
    BranchRule,
    Category,
    EligibilityRule,
    Option,
    Question,
    Questionnaire,
    QuestionnaireResponse,
    QuestionnaireVersion,
    Section,
    Tier,
)


class EligibilityRuleAdminForm(forms.ModelForm):
    period = forms.ChoiceField(
        label="適用時期",
        choices=EligibilityRule.PERIOD_CHOICES,
    )
    frequency = forms.ChoiceField(
        label="填答頻率",
        choices=(("any", "不限"), ("once", "一次"), ("daily", "每日"),
                 ("weekly", "每週"), ("monthly", "每月")),
    )
    timing = forms.ChoiceField(
        label="建議填答時點",
        choices=(("any", "不限時點"), ("morning", "早上"), ("afternoon", "下午"),
                 ("evening", "晚上"), ("before_visit", "就診前"), ("after_visit", "就診後")),
    )
    start_date = forms.DateField(label="適用期間起日", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(label="適用期間迄日", required=False, widget=forms.DateInput(attrs={"type": "date"}))

    class Meta:
        model = EligibilityRule
        fields = ("version", "min_age_months", "max_age_months", "tracking_status")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        conditions = (self.instance.condition_json or {}) if self.instance.pk else {}
        self.fields["period"].initial = conditions.get("period", "any")
        self.fields["frequency"].initial = conditions.get("frequency", "any")
        self.fields["timing"].initial = conditions.get("timing", "any")
        self.fields["start_date"].initial = conditions.get("start_date") or None
        self.fields["end_date"].initial = conditions.get("end_date") or None

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "適用迄日不可早於起日。")
        conditions = dict(self.instance.condition_json or {})
        conditions.update({
            "period": cleaned.get("period", "any"),
            "frequency": cleaned.get("frequency", "any"),
            "timing": cleaned.get("timing", "any"),
            "start_date": start.isoformat() if start else "",
            "end_date": end.isoformat() if end else "",
        })
        self.instance.condition_json = conditions
        return cleaned


# ---------------------------------------------------------------------------
# 依所屬版本是否為草稿，決定後台能否編輯
# ---------------------------------------------------------------------------

class LockWhenPublishedMixin:
    """內容物件（題組／題目／選項／分支／適用規則）的後台編輯權限，
    跟著所屬問卷版本的狀態走。model 層已會擋（見 VersionScopedModel），
    這裡是為了讓畫面直接顯示成唯讀，不要讓使用者填完才被拒。"""

    def _version_of(self, obj):
        if obj is None:
            return None
        return obj.owning_version()

    def _is_locked(self, obj):
        version = self._version_of(obj)
        return version is not None and not version.is_editable

    def has_change_permission(self, request, obj=None):
        if self._is_locked(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if self._is_locked(obj):
            return False
        return super().has_delete_permission(request, obj)


class LockableInline(LockWhenPublishedMixin, admin.TabularInline):
    """inline 版：obj 是「父物件」（例如 SectionInline 掛在 VersionAdmin 上時，
    obj 是 QuestionnaireVersion）。"""

    extra = 0

    def _version_of(self, obj):
        # 父物件本身可能就是版本，或是能導出版本的內容物件
        if obj is None:
            return None
        if isinstance(obj, QuestionnaireVersion):
            return obj
        if hasattr(obj, "owning_version"):
            return obj.owning_version()
        return None

    def has_add_permission(self, request, obj=None):
        if self._is_locked(obj):
            return False
        return super().has_add_permission(request, obj)


# ---------------------------------------------------------------------------
# 分類與分層
# ---------------------------------------------------------------------------

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("name", "code")


@admin.register(Tier)
class TierAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "order", "is_active")
    list_editable = ("order", "is_active")
    search_fields = ("name", "code")


# ---------------------------------------------------------------------------
# 問卷主檔 → 版本
# ---------------------------------------------------------------------------

class QuestionnaireVersionInline(admin.TabularInline):
    model = QuestionnaireVersion
    extra = 0
    fields = ("version_number", "status", "change_note", "published_at", "retired_at")
    readonly_fields = ("version_number", "status", "published_at", "retired_at")
    show_change_link = True
    ordering = ("-version_number",)

    def has_add_permission(self, request, obj=None):
        # 新版本一律透過「複製為新版本」action 產生，不手動新增
        return False


@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "tier", "is_active", "latest_version_display", "created_at")
    list_filter = ("is_active", "category", "tier")
    search_fields = ("name", "description")
    readonly_fields = ("created_at",)
    inlines = [QuestionnaireVersionInline]

    @admin.display(description="最新版本")
    def latest_version_display(self, obj):
        version = obj.versions.order_by("-version_number").first()
        if version is None:
            return "尚無版本"
        return f"v{version.version_number}（{version.get_status_display()}）"

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # 建立問卷主檔時，若尚無任何版本，順手開一個 v1 草稿
        questionnaire = form.instance
        if not questionnaire.versions.exists():
            QuestionnaireVersion.objects.create(questionnaire=questionnaire, version_number=1)
            messages.info(request, "已自動建立 v1 草稿，可點入版本開始設計題目。")


# ---------------------------------------------------------------------------
# 版本 → 題組 + 適用規則
# ---------------------------------------------------------------------------

class SectionInline(LockableInline):
    model = Section
    fields = ("title", "order", "is_active")
    show_change_link = True
    ordering = ("order",)


class EligibilityRuleInline(LockableInline):
    model = EligibilityRule
    form = EligibilityRuleAdminForm
    fields = ("min_age_months", "max_age_months", "tracking_status",
              "period", "frequency", "timing", "start_date", "end_date")


@admin.register(QuestionnaireVersion)
class QuestionnaireVersionAdmin(admin.ModelAdmin):
    list_display = ("questionnaire", "version_number", "status", "published_at", "created_at")
    list_filter = ("status", "questionnaire__tier", "questionnaire__category")
    search_fields = ("questionnaire__name",)
    readonly_fields = ("version_number", "status", "published_at", "retired_at", "created_at")
    inlines = [SectionInline, EligibilityRuleInline]
    actions = ["action_publish", "action_retire", "action_clone"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # 版本主檔的中繼欄位（change_note）永遠可編輯；內容鎖在 inline 上處理
        return super().has_change_permission(request, obj)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if object_id:
            version = self.get_object(request, object_id)
            if version and not version.is_editable:
                messages.info(
                    request,
                    format_html(
                        "此版本已鎖定，不能新增或修改適用規則。請先到<a href=\"{}\">問卷版本列表</a>，"
                        "選取此版本並執行「複製為新版本（草稿）」，再到新草稿中調整規則。",
                        reverse("admin:questionnaires_questionnaireversion_changelist"),
                    ),
                )
        return super().changeform_view(request, object_id, form_url, extra_context)

    @admin.action(description="發布選取的版本")
    def action_publish(self, request, queryset):
        done, failed = 0, []
        for version in queryset:
            try:
                version.publish()
                done += 1
            except ValidationError as exc:
                failed.append(f"{version}：{'; '.join(exc.messages)}")
        if done:
            self.message_user(request, f"已發布 {done} 個版本。", messages.SUCCESS)
        for msg in failed:
            self.message_user(request, msg, messages.ERROR)

    @admin.action(description="停用選取的版本")
    def action_retire(self, request, queryset):
        done, failed = 0, []
        for version in queryset:
            try:
                version.retire()
                done += 1
            except ValidationError as exc:
                failed.append(f"{version}：{'; '.join(exc.messages)}")
        if done:
            self.message_user(request, f"已停用 {done} 個版本。", messages.SUCCESS)
        for msg in failed:
            self.message_user(request, msg, messages.ERROR)

    @admin.action(description="複製為新版本（草稿）")
    def action_clone(self, request, queryset):
        created = []
        for version in queryset:
            new_version = version.clone_as_new_draft()
            created.append(str(new_version))
        self.message_user(
            request,
            f"已建立 {len(created)} 個新草稿版本：{'、'.join(created)}",
            messages.SUCCESS,
        )


# ---------------------------------------------------------------------------
# 題組 → 題目
# ---------------------------------------------------------------------------

class QuestionInline(LockableInline):
    model = Question
    fields = ("prompt", "question_type", "required", "order", "is_active")
    show_change_link = True
    ordering = ("order",)


@admin.register(Section)
class SectionAdmin(LockWhenPublishedMixin, admin.ModelAdmin):
    list_display = ("title", "version", "order", "is_active", "question_count")
    list_filter = ("version__status", "version__questionnaire")
    search_fields = ("title", "version__questionnaire__name")
    inlines = [QuestionInline]

    @admin.display(description="題目數")
    def question_count(self, obj):
        return obj.questions.count()


# ---------------------------------------------------------------------------
# 題目 → 選項 + 分支條件
# ---------------------------------------------------------------------------

class OptionInline(LockableInline):
    model = Option
    fields = ("label", "value", "order", "is_active")
    ordering = ("order",)


class BranchRuleInline(LockableInline):
    model = BranchRule
    fk_name = "trigger_question"
    fields = ("trigger_operator", "trigger_value", "action",
              "target_section", "target_question", "target_questionnaire")


@admin.register(Question)
class QuestionAdmin(LockWhenPublishedMixin, admin.ModelAdmin):
    list_display = ("prompt", "section", "question_type", "required", "order", "is_active")
    list_filter = ("question_type", "required", "is_active",
                   "section__version__status", "section__version__questionnaire")
    search_fields = ("prompt", "section__title")
    inlines = [OptionInline, BranchRuleInline]


@admin.register(Option)
class OptionAdmin(LockWhenPublishedMixin, admin.ModelAdmin):
    list_display = ("label", "value", "question", "order", "is_active")
    list_filter = ("question__section__version__questionnaire",)
    search_fields = ("label", "value", "question__prompt")


@admin.register(BranchRule)
class BranchRuleAdmin(LockWhenPublishedMixin, admin.ModelAdmin):
    list_display = ("__str__", "trigger_question", "action")
    list_filter = ("action", "trigger_operator",
                   "trigger_question__section__version__questionnaire")
    search_fields = ("trigger_question__prompt",)


@admin.register(EligibilityRule)
class EligibilityRuleAdmin(LockWhenPublishedMixin, admin.ModelAdmin):
    list_display = ("version", "min_age_months", "max_age_months", "tracking_status")
    list_filter = ("version__status", "version__questionnaire")
    form = EligibilityRuleAdminForm
    fields = ("version", "min_age_months", "max_age_months", "tracking_status",
              "period", "frequency", "timing", "start_date", "end_date")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "version":
            kwargs["queryset"] = QuestionnaireVersion.objects.filter(
                status=QuestionnaireVersion.Status.DRAFT
            ).select_related("questionnaire")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


# ---------------------------------------------------------------------------
# 填答紀錄
# ---------------------------------------------------------------------------

class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    fields = ("question", "value", "answered_at")
    readonly_fields = ("question", "value", "answered_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(QuestionnaireResponse)
class QuestionnaireResponseAdmin(admin.ModelAdmin):
    # 正式文件（三）：依兒童、問卷、日期、Tier、版本及完成狀態進行查詢
    list_display = ("child", "questionnaire_name", "version", "status",
                    "started_at", "completed_at", "source")
    list_filter = (
        "child",
        "status",
        "started_at",
        "version__questionnaire__tier",
        "version__questionnaire",
        "version__version_number",
    )
    search_fields = ("child__name", "child__medical_no", "version__questionnaire__name")
    date_hierarchy = "started_at"
    readonly_fields = ("child", "version", "source", "started_at", "updated_at", "completed_at")
    inlines = [AnswerInline]

    @admin.display(description="問卷", ordering="version__questionnaire__name")
    def questionnaire_name(self, obj):
        return obj.version.questionnaire.name

    def has_add_permission(self, request):
        # 填答紀錄由家長端 API 建立，後台只供查詢追蹤
        return False
