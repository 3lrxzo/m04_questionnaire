"""家長端填答頁用的 JSON API（《開發規劃書》第六節）。

    GET   /api/questionnaires/<version_id>/schema/   載入完整問卷 schema
    POST  /api/responses/                            開始填答
    GET   /api/responses/<id>/                       續填時取回已填內容
    PATCH /api/responses/<id>/autosave/              暫存單題／單題組
    POST  /api/responses/<id>/complete/              完成送出

權限：目前沿用 settings 的 IsAuthenticated（DRF 原廠預設 AllowAny 對兒童
健康資料不可接受）。家長端實際的身分驗證方式待院方 APP 介接規格確定後
再收斂，屆時把「家長只能存取自己名下兒童」的規則補在 get_queryset。
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from .logic import compute_visibility, get_pending_questionnaires
from .models import Question, QuestionnaireResponse, QuestionnaireVersion
from .serializers import (
    AutosaveSerializer,
    ResponseCreateSerializer,
    ResponseReadSerializer,
    VersionSchemaSerializer,
)


class VersionSchemaView(RetrieveAPIView):
    serializer_class = VersionSchemaSerializer
    lookup_url_kwarg = "version_id"

    def get_queryset(self):
        qs = QuestionnaireVersion.objects.select_related("questionnaire__tier")
        # ?preview=1：允許讀草稿，供後台發布前預覽（正式文件（三）必要項）
        if self.request.query_params.get("preview") == "1":
            return qs
        return qs.filter(status=QuestionnaireVersion.Status.PUBLISHED)


class ResponseCreateView(APIView):
    def post(self, request):
        serializer = ResponseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        response = serializer.save()
        return Response(
            ResponseReadSerializer(response).data,
            status=status.HTTP_201_CREATED,
        )


class ResponseDetailView(RetrieveAPIView):
    serializer_class = ResponseReadSerializer
    queryset = QuestionnaireResponse.objects.select_related("version__questionnaire")
    lookup_url_kwarg = "response_id"


class ResponseAutosaveView(APIView):
    def patch(self, request, response_id):
        response = get_object_or_404(QuestionnaireResponse, pk=response_id)
        if response.status == QuestionnaireResponse.Status.COMPLETED:
            return Response(
                {"detail": "此填答已完成，不可再修改。"},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = AutosaveSerializer(data=request.data, context={"response": response})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ResponseReadSerializer(response).data)


class ResponseCompleteView(APIView):
    def post(self, request, response_id):
        response = get_object_or_404(
            QuestionnaireResponse.objects.select_related("version"), pk=response_id
        )
        if response.status == QuestionnaireResponse.Status.COMPLETED:
            return self._completed_payload(response)

        answers = {a.question_id: a.value for a in response.answers.all()}

        # 只檢查「目前可見且必填」的題目 —— 被分支隱藏的追問題不算漏答
        visibility = compute_visibility(response.version, answers)
        visible_qids = visibility["visible_question_ids"]
        required_missing = [
            q.id
            for q in Question.objects.filter(
                section__version=response.version, required=True, is_active=True
            )
            if q.id in visible_qids and _is_blank(answers.get(q.id))
        ]
        if required_missing:
            return Response(
                {"detail": "尚有必填題目未作答。", "missing_question_ids": required_missing},
                status=status.HTTP_400_BAD_REQUEST,
            )

        response.mark_completed()
        return self._completed_payload(response)

    @staticmethod
    def _completed_payload(response):
        payload = ResponseReadSerializer(response).data
        payload["next_questionnaires"] = [
            {
                "version_id": item["version"].id,
                "questionnaire_name": item["version"].questionnaire.name,
                "tier_name": (
                    item["version"].questionnaire.tier.name
                    if item["version"].questionnaire.tier else None
                ),
                "state": item["state"],
                "response_id": item["response_id"],
            }
            for item in get_pending_questionnaires(response.child)
        ]
        return Response(payload)


def _is_blank(value):
    return value is None or value == "" or value == []
