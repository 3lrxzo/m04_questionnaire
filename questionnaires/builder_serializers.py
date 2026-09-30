"""問卷編輯器（後台 staff 用）的 serializers。

與 serializers.py（家長端唯讀 schema）分開：這裡是可寫的，且只作用於
草稿版本。
"""

from rest_framework import serializers
from datetime import date

from .models import (
    BranchRule, Category, EligibilityRule, Option, Question,
    Questionnaire, QuestionnaireVersion, Section, Tier,
)


class OptionEditSerializer(serializers.ModelSerializer):
    # value 可留空，建立時自動以 opt1/opt2… 產生（醫護通常只想填「選項文字」）
    value = serializers.CharField(max_length=100, required=False, allow_blank=True)

    class Meta:
        model = Option
        fields = ("id", "label", "value", "order", "is_active")
        read_only_fields = ("id",)


class BranchRuleEditSerializer(serializers.ModelSerializer):
    # 給前端顯示用的人類可讀描述
    description = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = BranchRule
        fields = (
            "id", "trigger_question", "trigger_operator", "trigger_value", "action",
            "target_section", "target_question", "target_questionnaire", "description",
        )
        read_only_fields = ("id", "description")

    def validate(self, attrs):
        targets = [
            attrs.get("target_section", getattr(self.instance, "target_section", None)),
            attrs.get("target_question", getattr(self.instance, "target_question", None)),
            attrs.get("target_questionnaire", getattr(self.instance, "target_questionnaire", None)),
        ]
        if sum(1 for t in targets if t is not None) != 1:
            raise serializers.ValidationError("跳題目標必須且只能指定一個（題組／題目／問卷）。")
        return attrs


class QuestionEditSerializer(serializers.ModelSerializer):
    options = OptionEditSerializer(many=True, read_only=True)

    class Meta:
        model = Question
        fields = (
            "id", "section", "prompt", "help_text", "question_type",
            "required", "order", "is_active", "config", "options",
        )
        read_only_fields = ("id", "section", "options")


class SectionEditSerializer(serializers.ModelSerializer):
    questions = QuestionEditSerializer(many=True, read_only=True)

    class Meta:
        model = Section
        fields = ("id", "version", "title", "description", "order", "is_active", "questions")
        read_only_fields = ("id", "version", "questions")


class EligibilityRuleEditSerializer(serializers.ModelSerializer):
    class Meta:
        model = EligibilityRule
        fields = ("id", "version", "min_age_months", "max_age_months",
                  "tracking_status", "condition_json")
        read_only_fields = ("id", "version")

    def validate(self, attrs):
        min_age = attrs.get("min_age_months", getattr(self.instance, "min_age_months", None))
        max_age = attrs.get("max_age_months", getattr(self.instance, "max_age_months", None))
        if min_age is not None and max_age is not None and min_age > max_age:
            raise serializers.ValidationError("最大月齡不可小於最小月齡。")
        conditions = attrs.get("condition_json", getattr(self.instance, "condition_json", {})) or {}
        if not isinstance(conditions, dict):
            raise serializers.ValidationError({"condition_json": "適用條件必須是 JSON 物件。"})
        period = conditions.get("period", "any")
        frequency = conditions.get("frequency", "any")
        timing = conditions.get("timing", "any")
        if period not in {value for value, _label in EligibilityRule.PERIOD_CHOICES}:
            raise serializers.ValidationError({"condition_json": "適用時期不在支援範圍。"})
        if frequency not in {"any", "once", "daily", "weekly", "monthly"}:
            raise serializers.ValidationError({"condition_json": "填答頻率不在支援範圍。"})
        if timing not in {"any", "morning", "afternoon", "evening", "before_visit", "after_visit"}:
            raise serializers.ValidationError({"condition_json": "填答時點不在支援範圍。"})
        try:
            start = date.fromisoformat(conditions["start_date"]) if conditions.get("start_date") else None
            end = date.fromisoformat(conditions["end_date"]) if conditions.get("end_date") else None
        except (TypeError, ValueError):
            raise serializers.ValidationError({"condition_json": "適用期間日期格式錯誤。"})
        if start and end and end < start:
            raise serializers.ValidationError({"condition_json": "適用迄日不可早於起日。"})
        return attrs


class VersionBuilderSerializer(serializers.ModelSerializer):
    """編輯器載入用的完整結構（含草稿可編輯資訊）。"""

    questionnaire_name = serializers.CharField(source="questionnaire.name", read_only=True)
    questionnaire_id = serializers.IntegerField(source="questionnaire.id", read_only=True)
    is_editable = serializers.BooleanField(read_only=True)
    sections = serializers.SerializerMethodField()
    branch_rules = serializers.SerializerMethodField()
    eligibility_rules = EligibilityRuleEditSerializer(many=True, read_only=True)
    target_questionnaires = serializers.SerializerMethodField()

    class Meta:
        model = QuestionnaireVersion
        fields = (
            "id", "questionnaire_id", "questionnaire_name", "version_number",
            "status", "is_editable", "change_note", "sections", "branch_rules",
            "eligibility_rules", "target_questionnaires",
        )
        read_only_fields = fields

    def get_sections(self, obj):
        sections = obj.sections.order_by("order").prefetch_related("questions__options")
        return SectionEditSerializer(sections, many=True).data

    def get_branch_rules(self, obj):
        rules = (
            BranchRule.objects
            .filter(trigger_question__section__version=obj)
            .select_related("target_section", "target_question", "target_questionnaire")
        )
        return BranchRuleEditSerializer(rules, many=True).data

    def get_target_questionnaires(self, obj):
        questionnaires = (
            Questionnaire.objects.filter(is_active=True)
            .exclude(pk=obj.questionnaire_id)
            .select_related("tier")
            .order_by("name")
        )
        return [
            {
                "id": questionnaire.id,
                "name": questionnaire.name,
                "tier_name": questionnaire.tier.name if questionnaire.tier else "",
            }
            for questionnaire in questionnaires
        ]


class QuestionnaireListSerializer(serializers.ModelSerializer):
    versions = serializers.SerializerMethodField()
    tier_name = serializers.CharField(source="tier.name", read_only=True, default=None)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Questionnaire
        fields = ("id", "name", "description", "category", "category_name",
                  "tier", "tier_name", "is_active", "created_at", "created_by_name", "versions")

    def get_created_by_name(self, obj):
        return obj.created_by.get_username() if obj.created_by else "未記錄"

    def get_versions(self, obj):
        return [
            {
                "id": v.id,
                "version_number": v.version_number,
                "status": v.status,
                "status_label": v.get_status_display(),
                "created_at": v.created_at,
                "published_by_name": v.published_by.get_username() if v.published_by else "未記錄",
                "published_at": v.published_at,
            }
            for v in obj.versions.order_by("version_number")
        ]


class QuestionnaireCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Questionnaire
        fields = ("id", "name", "description", "category", "tier")

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        questionnaire = super().create(validated_data)
        QuestionnaireVersion.objects.create(
            questionnaire=questionnaire,
            version_number=1,
            created_by=validated_data.get("created_by"),
        )
        return questionnaire
