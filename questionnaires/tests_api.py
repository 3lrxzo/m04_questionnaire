"""家長端填答 API 的端對端測試（《開發規劃書》第六節五個端點）。

用發燒示範情境貫穿：schema → 開始填答 → autosave → 依分支追問 → 完成。
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from children.models import Child

from .models import (
    BranchRule, EligibilityRule, Option, Question, Questionnaire,
    QuestionnaireResponse, QuestionnaireVersion, Section, Tier,
)


class ApiFixtureMixin:
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("parent", password="pw")
        self.client.force_login(self.user)

        tier, _ = Tier.objects.get_or_create(code="tier1", defaults={"name": "Tier 1", "order": 1})
        self.questionnaire = Questionnaire.objects.create(name="每日健康檢核", tier=tier)
        self.version = QuestionnaireVersion.objects.create(
            questionnaire=self.questionnaire, version_number=1
        )

        daily = Section.objects.create(version=self.version, title="每日必填", order=1)
        self.fever = Question.objects.create(
            section=daily, prompt="今天是否有發燒？",
            question_type=Question.Type.SINGLE, order=1, required=True,
        )
        Option.objects.create(question=self.fever, label="沒有", value="no", order=1)
        Option.objects.create(question=self.fever, label="有", value="yes", order=2)

        self.followup = Section.objects.create(version=self.version, title="發燒追問", order=2)
        self.temp = Question.objects.create(
            section=self.followup, prompt="最高體溫？",
            question_type=Question.Type.NUMBER, order=1, required=True,
            config={"min": 35, "max": 42, "step": 0.1, "unit": "°C"},
        )
        BranchRule.objects.create(
            trigger_question=self.fever, trigger_operator=BranchRule.Operator.EQ,
            trigger_value="yes", action=BranchRule.Action.SHOW, target_section=self.followup,
        )
        EligibilityRule.objects.create(version=self.version, min_age_months=0, max_age_months=72)
        self.version.publish()

        self.child = Child.objects.create(
            name="小明", birth_date=timezone.localdate() - timedelta(days=365 * 3),
        )


class SchemaEndpointTests(ApiFixtureMixin, TestCase):
    def test_published_schema_returns_full_tree(self):
        url = reverse("questionnaires:api-version-schema", args=[self.version.id])
        data = self.client.get(url).json()

        self.assertEqual(data["questionnaire_name"], "每日健康檢核")
        self.assertEqual(data["version_number"], 1)
        self.assertEqual(len(data["sections"]), 2)
        self.assertEqual(len(data["sections"][0]["questions"][0]["options"]), 2)
        self.assertEqual(len(data["branch_rules"]), 1)
        self.assertEqual(data["branch_rules"][0]["trigger_value"], "yes")

    def test_draft_schema_hidden_without_preview(self):
        draft = self.version.clone_as_new_draft()
        url = reverse("questionnaires:api-version-schema", args=[draft.id])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(url + "?preview=1").status_code, 200)

    def test_inactive_question_excluded_from_schema(self):
        # 停用題目前須先複製成草稿（發布版鎖住）
        draft = self.version.clone_as_new_draft()
        q = Question.objects.get(section__version=draft, prompt="最高體溫？")
        q.is_active = False
        q.save()
        url = reverse("questionnaires:api-version-schema", args=[draft.id])
        data = self.client.get(url + "?preview=1").json()
        followup = next(s for s in data["sections"] if s["title"] == "發燒追問")
        self.assertEqual(followup["questions"], [])


class ResponseFlowTests(ApiFixtureMixin, TestCase):
    def _start(self):
        return self.client.post(
            reverse("questionnaires:api-response-create"),
            data={"child": self.child.id, "version": self.version.id},
            content_type="application/json",
        )

    def test_start_creates_response(self):
        res = self._start()
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual(body["status"], "in_progress")
        self.assertEqual(body["answers"], {})

    def test_start_twice_returns_same_in_progress_response(self):
        first = self._start().json()
        second = self._start().json()
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(QuestionnaireResponse.objects.filter(child=self.child).count(), 1)

    def test_start_rejects_unpublished_version(self):
        draft = self.version.clone_as_new_draft()
        res = self.client.post(
            reverse("questionnaires:api-response-create"),
            data={"child": self.child.id, "version": draft.id},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

    def test_autosave_persists_and_detail_reads_back(self):
        rid = self._start().json()["id"]
        res = self.client.patch(
            reverse("questionnaires:api-response-autosave", args=[rid]),
            data={"answers": {str(self.fever.id): "yes"}},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)

        detail = self.client.get(
            reverse("questionnaires:api-response-detail", args=[rid])
        ).json()
        self.assertEqual(detail["answers"][str(self.fever.id)], "yes")

    def test_autosave_rejects_question_from_another_version(self):
        rid = self._start().json()["id"]
        other_q = Question.objects.create(
            section=Section.objects.create(
                version=QuestionnaireVersion.objects.create(
                    questionnaire=Questionnaire.objects.create(name="別的問卷"),
                    version_number=1,
                ),
                title="x", order=1,
            ),
            prompt="無關題", question_type=Question.Type.TEXT, order=1,
        )
        res = self.client.patch(
            reverse("questionnaires:api-response-autosave", args=[rid]),
            data={"answers": {str(other_q.id): "x"}},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 400)

    def test_complete_blocked_when_visible_required_missing(self):
        rid = self._start().json()["id"]
        # 答「有」→ 追問題組變必填且可見，但沒填體溫
        self.client.patch(
            reverse("questionnaires:api-response-autosave", args=[rid]),
            data={"answers": {str(self.fever.id): "yes"}},
            content_type="application/json",
        )
        res = self.client.post(reverse("questionnaires:api-response-complete", args=[rid]))
        self.assertEqual(res.status_code, 400)
        self.assertIn(self.temp.id, res.json()["missing_question_ids"])

    def test_complete_succeeds_when_followup_not_triggered(self):
        rid = self._start().json()["id"]
        self.client.patch(
            reverse("questionnaires:api-response-autosave", args=[rid]),
            data={"answers": {str(self.fever.id): "no"}},
            content_type="application/json",
        )
        res = self.client.post(reverse("questionnaires:api-response-complete", args=[rid]))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "completed")

    def test_complete_succeeds_when_followup_filled(self):
        rid = self._start().json()["id"]
        self.client.patch(
            reverse("questionnaires:api-response-autosave", args=[rid]),
            data={"answers": {str(self.fever.id): "yes", str(self.temp.id): 38.5}},
            content_type="application/json",
        )
        res = self.client.post(reverse("questionnaires:api-response-complete", args=[rid]))
        self.assertEqual(res.status_code, 200)
        response = QuestionnaireResponse.objects.get(pk=rid)
        self.assertEqual(response.status, QuestionnaireResponse.Status.COMPLETED)
        self.assertIsNotNone(response.completed_at)

    def test_completion_returns_triggered_next_questionnaire(self):
        source = self.version.clone_as_new_draft()
        self.version = source
        self.fever = Question.objects.get(section__version=source, prompt="今天是否有發燒？")
        self.temp = Question.objects.get(section__version=source, prompt="最高體溫？")
        tier2, _ = Tier.objects.get_or_create(code="tier2", defaults={"name": "Tier 2", "order": 2})
        next_questionnaire = Questionnaire.objects.create(name="進階評估", tier=tier2)
        next_version = QuestionnaireVersion.objects.create(
            questionnaire=next_questionnaire, version_number=1,
        )
        next_section = Section.objects.create(version=next_version, title="評估", order=1)
        Question.objects.create(
            section=next_section, prompt="症狀", question_type=Question.Type.TEXT, order=1,
        )
        next_version.publish()
        BranchRule.objects.create(
            trigger_question=self.fever, trigger_operator="eq", trigger_value="yes",
            action="show", target_questionnaire=next_questionnaire,
        )
        source.publish()

        rid = self._start().json()["id"]
        self.client.patch(
            reverse("questionnaires:api-response-autosave", args=[rid]),
            data={"answers": {str(self.fever.id): "yes", str(self.temp.id): 38.5}},
            content_type="application/json",
        )
        result = self.client.post(
            reverse("questionnaires:api-response-complete", args=[rid]),
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["next_questionnaires"][0]["version_id"], next_version.id)

    def test_autosave_blocked_after_completion(self):
        rid = self._start().json()["id"]
        self.client.patch(
            reverse("questionnaires:api-response-autosave", args=[rid]),
            data={"answers": {str(self.fever.id): "no"}},
            content_type="application/json",
        )
        self.client.post(reverse("questionnaires:api-response-complete", args=[rid]))
        res = self.client.patch(
            reverse("questionnaires:api-response-autosave", args=[rid]),
            data={"answers": {str(self.fever.id): "yes"}},
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 409)

    def test_requires_authentication(self):
        self.client.logout()
        res = self.client.get(
            reverse("questionnaires:api-version-schema", args=[self.version.id])
        )
        self.assertIn(res.status_code, (401, 403))
