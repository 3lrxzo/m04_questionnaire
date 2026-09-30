"""問卷編輯器的後端 API（後台 staff 用）。

與家長端 api_views.py 的差異：
- 權限 IsAdminUser（is_staff）
- 可寫，但只作用於草稿版本；非草稿的寫入回 409 + 白話訊息
- model 層仍有 VersionScopedModel 把關，這裡是為了給前端乾淨的錯誤
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .builder_serializers import (
    BranchRuleEditSerializer,
    EligibilityRuleEditSerializer,
    OptionEditSerializer,
    QuestionEditSerializer,
    QuestionnaireCreateSerializer,
    QuestionnaireListSerializer,
    SectionEditSerializer,
    VersionBuilderSerializer,
)
from .models import (
    BranchRule, EligibilityRule, Option, Question,
    Questionnaire, QuestionnaireVersion, Section,
)


class BuilderBase:
    permission_classes = [IsAdminUser]


def _draft_or_409(version):
    """草稿才可編輯，否則回一個會被 DRF 轉成 409 的例外。"""
    if not version.is_editable:
        raise Conflict(
            f"這是「{version.get_status_display()}」版本，內容已鎖定。"
            f"請先「複製為新版本」再編輯。"
        )


class Conflict(Exception):
    pass


class DraftWriteMixin(BuilderBase):
    """建立/更新/刪除前，確認所屬版本是草稿。"""

    def _version_of_target(self):
        raise NotImplementedError

    def perform_create(self, serializer):
        _draft_or_409(self._version_of_target())
        try:
            serializer.save()
        except DjangoValidationError as exc:
            raise Conflict("；".join(exc.messages))

    def perform_update(self, serializer):
        _draft_or_409(self._version_of_target())
        try:
            serializer.save()
        except DjangoValidationError as exc:
            raise Conflict("；".join(exc.messages))

    def perform_destroy(self, instance):
        _draft_or_409(self._version_of_target())
        try:
            instance.delete()
        except DjangoValidationError as exc:
            raise Conflict("；".join(exc.messages))

    def handle_exception(self, exc):
        if isinstance(exc, Conflict):
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return super().handle_exception(exc)


# ---------------------------------------------------------------------------
# 問卷主檔 / 版本
# ---------------------------------------------------------------------------

class QuestionnaireListCreateView(BuilderBase, generics.ListCreateAPIView):
    queryset = Questionnaire.objects.select_related("tier", "category").prefetch_related("versions")

    def get_serializer_class(self):
        return QuestionnaireCreateSerializer if self.request.method == "POST" else QuestionnaireListSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        questionnaire = serializer.save()
        out = QuestionnaireListSerializer(questionnaire)
        return Response(out.data, status=status.HTTP_201_CREATED)


class VersionBuilderView(BuilderBase, generics.RetrieveAPIView):
    queryset = QuestionnaireVersion.objects.select_related("questionnaire")
    serializer_class = VersionBuilderSerializer
    lookup_url_kwarg = "version_id"


class VersionPublishView(BuilderBase, APIView):
    def post(self, request, version_id):
        version = get_object_or_404(QuestionnaireVersion, pk=version_id)
        try:
            version.publish(published_by=request.user)
        except DjangoValidationError as exc:
            return Response({"detail": "；".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(VersionBuilderSerializer(version).data)


class VersionCloneView(BuilderBase, APIView):
    def post(self, request, version_id):
        version = get_object_or_404(QuestionnaireVersion, pk=version_id)
        new_version = version.clone_as_new_draft(created_by=request.user)
        return Response(VersionBuilderSerializer(new_version).data, status=status.HTTP_201_CREATED)


class VersionRetireView(BuilderBase, APIView):
    def post(self, request, version_id):
        version = get_object_or_404(QuestionnaireVersion, pk=version_id)
        try:
            version.retire()
        except DjangoValidationError as exc:
            return Response({"detail": "；".join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(VersionBuilderSerializer(version).data)


# ---------------------------------------------------------------------------
# 題組
# ---------------------------------------------------------------------------

class SectionCreateView(DraftWriteMixin, generics.CreateAPIView):
    serializer_class = SectionEditSerializer

    def _version(self):
        return get_object_or_404(QuestionnaireVersion, pk=self.kwargs["version_id"])

    def _version_of_target(self):
        return self._version()

    def perform_create(self, serializer):
        version = self._version()
        _draft_or_409(version)
        next_order = (version.sections.count() + 1)
        serializer.save(version=version, order=serializer.validated_data.get("order") or next_order)


class SectionDetailView(DraftWriteMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Section.objects.select_related("version")
    serializer_class = SectionEditSerializer
    lookup_url_kwarg = "section_id"

    def _version_of_target(self):
        return self.get_object().version


# ---------------------------------------------------------------------------
# 題目
# ---------------------------------------------------------------------------

class QuestionCreateView(DraftWriteMixin, generics.CreateAPIView):
    serializer_class = QuestionEditSerializer

    def _section(self):
        return get_object_or_404(Section.objects.select_related("version"), pk=self.kwargs["section_id"])

    def _version_of_target(self):
        return self._section().version

    def perform_create(self, serializer):
        section = self._section()
        _draft_or_409(section.version)
        next_order = section.questions.count() + 1
        serializer.save(section=section, order=serializer.validated_data.get("order") or next_order)


class QuestionDetailView(DraftWriteMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Question.objects.select_related("section__version")
    serializer_class = QuestionEditSerializer
    lookup_url_kwarg = "question_id"

    def _version_of_target(self):
        return self.get_object().section.version


# ---------------------------------------------------------------------------
# 選項
# ---------------------------------------------------------------------------

class OptionCreateView(DraftWriteMixin, generics.CreateAPIView):
    serializer_class = OptionEditSerializer

    def _question(self):
        return get_object_or_404(
            Question.objects.select_related("section__version"), pk=self.kwargs["question_id"]
        )

    def _version_of_target(self):
        return self._question().section.version

    def perform_create(self, serializer):
        question = self._question()
        _draft_or_409(question.section.version)
        next_order = question.options.count() + 1
        value = serializer.validated_data.get("value") or f"opt{next_order}"
        serializer.save(question=question, order=serializer.validated_data.get("order") or next_order,
                        value=value)


class OptionDetailView(DraftWriteMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Option.objects.select_related("question__section__version")
    serializer_class = OptionEditSerializer
    lookup_url_kwarg = "option_id"

    def _version_of_target(self):
        return self.get_object().question.section.version


# ---------------------------------------------------------------------------
# 分支規則
# ---------------------------------------------------------------------------

class BranchRuleCreateView(DraftWriteMixin, generics.CreateAPIView):
    serializer_class = BranchRuleEditSerializer

    def _version(self):
        return get_object_or_404(QuestionnaireVersion, pk=self.kwargs["version_id"])

    def _version_of_target(self):
        return self._version()


class BranchRuleDetailView(DraftWriteMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = BranchRule.objects.select_related("trigger_question__section__version")
    serializer_class = BranchRuleEditSerializer
    lookup_url_kwarg = "rule_id"

    def _version_of_target(self):
        return self.get_object().trigger_question.section.version


# ---------------------------------------------------------------------------
# 適用規則
# ---------------------------------------------------------------------------

class EligibilityCreateView(DraftWriteMixin, generics.CreateAPIView):
    serializer_class = EligibilityRuleEditSerializer

    def _version(self):
        return get_object_or_404(QuestionnaireVersion, pk=self.kwargs["version_id"])

    def _version_of_target(self):
        return self._version()

    def perform_create(self, serializer):
        version = self._version()
        _draft_or_409(version)
        serializer.save(version=version)


class EligibilityDetailView(DraftWriteMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = EligibilityRule.objects.select_related("version")
    serializer_class = EligibilityRuleEditSerializer
    lookup_url_kwarg = "rule_id"

    def _version_of_target(self):
        return self.get_object().version


# ---------------------------------------------------------------------------
# 批次排序
# ---------------------------------------------------------------------------

class ReorderView(DraftWriteMixin, APIView):
    """一次套用題組與題目的新順序。

    body: {
      "sections": [id, id, ...],                 # 題組新順序
      "questions": { "<section_id>": [id, ...] }  # 各題組內題目新順序
    }
    """

    def _version(self):
        return get_object_or_404(QuestionnaireVersion, pk=self.kwargs["version_id"])

    def _version_of_target(self):
        return self._version()

    @transaction.atomic
    def post(self, request, version_id):
        version = self._version()
        _draft_or_409(version)

        section_ids = request.data.get("sections", [])
        for order, sid in enumerate(section_ids, start=1):
            Section.objects.filter(pk=sid, version=version).update(order=order)

        for sid, question_ids in request.data.get("questions", {}).items():
            for order, qid in enumerate(question_ids, start=1):
                Question.objects.filter(pk=qid, section_id=sid, section__version=version).update(order=order)

        return Response(VersionBuilderSerializer(version).data)
