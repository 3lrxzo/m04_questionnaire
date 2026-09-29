"""DRF serializers。

分兩組：
  1. schema 組 —— 把一個問卷版本攤平成 Vue 一次載入所需的 JSON
  2. response 組 —— 填答紀錄的建立、讀回、暫存
"""

from rest_framework import serializers

from children.models import Child

from .models import (
    Answer, BranchRule, EligibilityRule, Option, Question,
    QuestionnaireResponse, QuestionnaireVersion, Section,
)
from .logic import get_pending_questionnaires


# ---------------------------------------------------------------------------
# schema：問卷版本 → Vue
# ---------------------------------------------------------------------------

class OptionSchemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Option
        fields = ("id", "label", "value", "order")


class QuestionSchemaSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = (
            "id", "section_id", "prompt", "help_text", "question_type",
            "required", "order", "config", "options",
        )

    def get_options(self, obj):
        active = [o for o in obj.options.all() if o.is_active]
        return OptionSchemaSerializer(sorted(active, key=lambda o: o.order), many=True).data


class SectionSchemaSerializer(serializers.ModelSerializer):
    questions = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = ("id", "title", "description", "order", "questions")

    def get_questions(self, obj):
        active = [q for q in obj.questions.all() if q.is_active]
        return QuestionSchemaSerializer(sorted(active, key=lambda q: q.order), many=True).data


class BranchRuleSchemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = BranchRule
        fields = (
            "id", "trigger_question_id", "trigger_operator", "trigger_value",
            "action", "target_section_id", "target_question_id", "target_questionnaire_id",
        )


class EligibilityRuleSchemaSerializer(serializers.ModelSerializer):
    class Meta:
        model = EligibilityRule
        fields = ("min_age_months", "max_age_months", "tracking_status", "condition_json")


class VersionSchemaSerializer(serializers.ModelSerializer):
    """一次載入用的完整 schema。分支規則獨立成一份陣列，讓前端自行套用
    可見性邏輯，不必每答一題就打 server（《開發規劃書》第二節）。"""

    questionnaire_id = serializers.IntegerField(source="questionnaire.id", read_only=True)
    questionnaire_name = serializers.CharField(source="questionnaire.name", read_only=True)
    tier = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()
    branch_rules = serializers.SerializerMethodField()
    eligibility_rules = EligibilityRuleSchemaSerializer(many=True, read_only=True)

    class Meta:
        model = QuestionnaireVersion
        fields = (
            "id", "questionnaire_id", "questionnaire_name", "tier",
            "version_number", "status", "sections", "branch_rules", "eligibility_rules",
        )

    def get_tier(self, obj):
        tier = obj.questionnaire.tier
        return {"code": tier.code, "name": tier.name} if tier else None

    def get_sections(self, obj):
        active = [s for s in obj.sections.all() if s.is_active]
        return SectionSchemaSerializer(sorted(active, key=lambda s: s.order), many=True).data

    def get_branch_rules(self, obj):
        rules = BranchRule.objects.filter(trigger_question__section__version=obj)
        return BranchRuleSchemaSerializer(rules, many=True).data


# ---------------------------------------------------------------------------
# response：填答紀錄
# ---------------------------------------------------------------------------

class ResponseCreateSerializer(serializers.Serializer):
    child = serializers.PrimaryKeyRelatedField(queryset=Child.objects.filter(is_active=True))
    version = serializers.PrimaryKeyRelatedField(
        queryset=QuestionnaireVersion.objects.filter(
            status=QuestionnaireVersion.Status.PUBLISHED
        )
    )

    def validate(self, attrs):
        child, version = attrs["child"], attrs["version"]
        pending_ids = {
            item["version"].id for item in get_pending_questionnaires(child)
        }
        if version.id not in pending_ids:
            raise serializers.ValidationError(
                "此問卷目前不適用、尚未由前一份問卷觸發，或尚未到填答時間。"
            )
        return attrs

    def create(self, validated_data):
        # 已有未完成紀錄就接續它，不重複開（呼應「暫存續填」，也讓
        # one_in_progress_response_per_child_version 不會撞唯一索引）
        existing = QuestionnaireResponse.objects.filter(
            child=validated_data["child"],
            version=validated_data["version"],
            status=QuestionnaireResponse.Status.IN_PROGRESS,
        ).first()
        if existing:
            return existing
        return QuestionnaireResponse.objects.create(**validated_data)


class ResponseReadSerializer(serializers.ModelSerializer):
    """續填時取回已填內容。answers 為 {question_id: value} 方便前端直接展開。"""

    answers = serializers.SerializerMethodField()
    questionnaire_name = serializers.CharField(source="version.questionnaire.name", read_only=True)

    class Meta:
        model = QuestionnaireResponse
        fields = (
            "id", "child", "version", "questionnaire_name", "status",
            "source", "started_at", "updated_at", "completed_at", "answers",
        )

    def get_answers(self, obj):
        return {a.question_id: a.value for a in obj.answers.all()}


class AutosaveSerializer(serializers.Serializer):
    """暫存單題或多題。answers：{question_id: value}。"""

    answers = serializers.DictField(child=serializers.JSONField(), allow_empty=False)

    def validate_answers(self, value):
        response = self.context["response"]
        valid_qids = set(
            Question.objects.filter(section__version=response.version)
            .values_list("id", flat=True)
        )
        cleaned = {}
        for raw_qid, answer in value.items():
            try:
                qid = int(raw_qid)
            except (TypeError, ValueError):
                raise serializers.ValidationError(f"題目 id「{raw_qid}」不是有效數字。")
            if qid not in valid_qids:
                raise serializers.ValidationError(f"題目 {qid} 不屬於這份問卷版本。")
            cleaned[qid] = answer
        return cleaned

    def save(self):
        response = self.context["response"]
        for qid, answer in self.validated_data["answers"].items():
            Answer.objects.update_or_create(
                response=response, question_id=qid, defaults={"value": answer},
            )
        response.save(update_fields=["updated_at"])
        return response
