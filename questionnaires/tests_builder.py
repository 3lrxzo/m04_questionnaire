"""問卷編輯器 API（B1）測試。"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    BranchRule, Option, Question, Questionnaire, QuestionnaireVersion, Section, Tier,
)


class BuilderApiTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.staff = User.objects.create_user("staff", password="pw", is_staff=True)
        self.plain = User.objects.create_user("plain", password="pw")
        self.client.force_login(self.staff)
        Tier.objects.get_or_create(code="tier1", defaults={"name": "Tier 1", "order": 1})

    # --- 建立問卷 ---------------------------------------------------------

    def test_create_questionnaire_opens_v1_draft(self):
        res = self.client.post(
            reverse("builder:api-questionnaires"),
            data={"name": "氣喘週追蹤"}, content_type="application/json",
        )
        self.assertEqual(res.status_code, 201)
        q = Questionnaire.objects.get(name="氣喘週追蹤")
        self.assertEqual(q.created_by, self.staff)
        self.assertEqual(q.versions.count(), 1)
        self.assertEqual(q.versions.first().status, QuestionnaireVersion.Status.DRAFT)
        self.assertEqual(q.versions.first().created_by, self.staff)
        self.assertEqual(res.json()["created_by_name"], self.staff.username)
        self.assertIn("created_at", res.json())
        self.assertEqual(res.json()["versions"][0]["published_by_name"], "未記錄")
        self.assertIn("created_at", res.json()["versions"][0])

    def test_non_staff_forbidden(self):
        self.client.force_login(self.plain)
        res = self.client.get(reverse("builder:api-questionnaires"))
        self.assertIn(res.status_code, (401, 403))

    # --- 題組 / 題目 / 選項 建立 -----------------------------------------

    def _new_version(self):
        q = Questionnaire.objects.create(name="測試問卷")
        return QuestionnaireVersion.objects.create(questionnaire=q, version_number=1)

    def test_build_section_question_option_chain(self):
        version = self._new_version()

        r = self.client.post(
            reverse("builder:api-section-create", args=[version.id]),
            data={"title": "每日必填"}, content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        section_id = r.json()["id"]
        self.assertEqual(r.json()["order"], 1)

        r = self.client.post(
            reverse("builder:api-question-create", args=[section_id]),
            data={"prompt": "今天是否有發燒？", "question_type": "single"},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        question_id = r.json()["id"]

        r = self.client.post(
            reverse("builder:api-option-create", args=[question_id]),
            data={"label": "沒有"}, content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["value"], "opt1")  # 自動產生

        r = self.client.post(
            reverse("builder:api-option-create", args=[question_id]),
            data={"label": "有", "value": "yes"}, content_type="application/json",
        )
        self.assertEqual(r.json()["value"], "yes")

    def test_version_builder_returns_full_tree(self):
        version = self._new_version()
        section = Section.objects.create(version=version, title="s", order=1)
        Question.objects.create(section=section, prompt="q", question_type="text", order=1)

        r = self.client.get(reverse("builder:api-version", args=[version.id]))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["is_editable"])
        self.assertEqual(len(data["sections"]), 1)
        self.assertEqual(len(data["sections"][0]["questions"]), 1)

    def test_builder_page_shows_applicability_and_schedule_controls(self):
        version = self._new_version()
        response = self.client.get(reverse("builder:editor", args=[version.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "適用時期")
        self.assertContains(response, "首次使用")
        self.assertContains(response, "日常")
        self.assertContains(response, "階段性")
        self.assertContains(response, "特定追蹤期間")
        self.assertContains(response, "填答頻率")
        self.assertContains(response, "建議填答時點")

    # --- 已發布版本鎖定 -------------------------------------------------

    def test_cannot_add_section_to_published_version(self):
        version = self._new_version()
        Section.objects.create(version=version, title="s", order=1)
        Question.objects.create(
            section=version.sections.first(), prompt="q", question_type="text", order=1,
        )
        version.publish()

        r = self.client.post(
            reverse("builder:api-section-create", args=[version.id]),
            data={"title": "偷加"}, content_type="application/json",
        )
        self.assertEqual(r.status_code, 409)
        self.assertIn("複製為新版本", r.json()["detail"])

    def test_cannot_edit_question_of_published_version(self):
        version = self._new_version()
        section = Section.objects.create(version=version, title="s", order=1)
        q = Question.objects.create(section=section, prompt="原題", question_type="text", order=1)
        version.publish()

        r = self.client.patch(
            reverse("builder:api-question-detail", args=[q.id]),
            data={"prompt": "改過"}, content_type="application/json",
        )
        self.assertEqual(r.status_code, 409)
        q.refresh_from_db()
        self.assertEqual(q.prompt, "原題")

    # --- 分支規則 -----------------------------------------------------

    def test_create_branch_rule_and_reject_multiple_targets(self):
        version = self._new_version()
        s1 = Section.objects.create(version=version, title="s1", order=1)
        s2 = Section.objects.create(version=version, title="s2", order=2)
        q = Question.objects.create(section=s1, prompt="發燒?", question_type="single", order=1)

        r = self.client.post(
            reverse("builder:api-rule-create", args=[version.id]),
            data={
                "trigger_question": q.id, "trigger_operator": "eq",
                "trigger_value": "yes", "action": "show", "target_section": s2.id,
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIn("顯示", r.json()["description"])

        r = self.client.post(
            reverse("builder:api-rule-create", args=[version.id]),
            data={
                "trigger_question": q.id, "trigger_operator": "eq", "trigger_value": "yes",
                "action": "show", "target_section": s2.id, "target_question": q.id,
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_create_and_edit_scheduling_rule_through_builder(self):
        version = self._new_version()
        rule_url = reverse("builder:api-eligibility-create", args=[version.id])
        r = self.client.post(
            rule_url,
            data={
                "min_age_months": 3, "max_age_months": 72,
                "tracking_status": "氣喘追蹤",
                "condition_json": {
                    "period": "first_visit",
                    "frequency": "daily", "timing": "morning",
                    "start_date": "2026-10-01", "end_date": "2026-12-31",
                },
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201, r.content)
        rule_id = r.json()["id"]
        self.assertEqual(r.json()["condition_json"]["period"], "first_visit")
        self.assertEqual(r.json()["condition_json"]["frequency"], "daily")

        r = self.client.patch(
            reverse("builder:api-eligibility-detail", args=[rule_id]),
            data={"condition_json": {"frequency": "weekly", "timing": "after_visit"}},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["condition_json"]["frequency"], "weekly")

        r = self.client.patch(
            reverse("builder:api-eligibility-detail", args=[rule_id]),
            data={"condition_json": {"period": "invalid"}},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 400)

    def test_supported_periods_can_be_saved_through_builder(self):
        version = self._new_version()
        rule_url = reverse("builder:api-eligibility-create", args=[version.id])
        periods = ("any", "first_visit", "daily", "phase", "tracking_period")

        for period in periods:
            with self.subTest(period=period):
                response = self.client.post(
                    rule_url,
                    data={"condition_json": {"period": period}},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 201, response.content)
                self.assertEqual(response.json()["condition_json"]["period"], period)

    def test_builder_exposes_other_questionnaires_as_branch_targets(self):
        version = self._new_version()
        target = Questionnaire.objects.create(name="下一階段")
        r = self.client.get(reverse("builder:api-version", args=[version.id]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["target_questionnaires"][0]["id"], target.id)

    # --- 排序 --------------------------------------------------------

    def test_reorder_sections_and_questions(self):
        version = self._new_version()
        a = Section.objects.create(version=version, title="A", order=1)
        b = Section.objects.create(version=version, title="B", order=2)
        q1 = Question.objects.create(section=a, prompt="q1", question_type="text", order=1)
        q2 = Question.objects.create(section=a, prompt="q2", question_type="text", order=2)

        r = self.client.post(
            reverse("builder:api-reorder", args=[version.id]),
            data={"sections": [b.id, a.id], "questions": {str(a.id): [q2.id, q1.id]}},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        a.refresh_from_db(); b.refresh_from_db()
        q1.refresh_from_db(); q2.refresh_from_db()
        self.assertEqual((b.order, a.order), (1, 2))
        self.assertEqual((q2.order, q1.order), (1, 2))

    # --- 發布 / 複製 ------------------------------------------------

    def test_publish_and_clone_flow(self):
        version = self._new_version()
        section = Section.objects.create(version=version, title="s", order=1)
        Question.objects.create(section=section, prompt="q", question_type="text", order=1)

        r = self.client.post(reverse("builder:api-version-publish", args=[version.id]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "published")

        r = self.client.post(reverse("builder:api-version-clone", args=[version.id]))
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["version_number"], 2)
        self.assertEqual(r.json()["status"], "draft")
        cloned_version = QuestionnaireVersion.objects.get(pk=r.json()["id"])
        self.assertEqual(cloned_version.created_by, self.staff)

    def test_publishing_version_records_publisher(self):
        version = self._new_version()
        section = Section.objects.create(version=version, title="題組", order=1)
        Question.objects.create(
            section=section, prompt="題目", question_type="text", order=1,
        )

        response = self.client.post(
            reverse("builder:api-version-publish", args=[version.id]),
        )
        self.assertEqual(response.status_code, 200, response.content)
        version.refresh_from_db()
        self.assertEqual(version.published_by, self.staff)

        questionnaire_response = self.client.get(
            reverse("builder:api-questionnaires"),
        )
        self.assertEqual(
            questionnaire_response.json()[0]["versions"][0]["published_by_name"],
            self.staff.username,
        )

    def test_publish_empty_version_rejected(self):
        version = self._new_version()
        r = self.client.post(reverse("builder:api-version-publish", args=[version.id]))
        self.assertEqual(r.status_code, 400)
