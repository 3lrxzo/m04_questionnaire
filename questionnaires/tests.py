"""版本不可覆寫與分支目標約束的回歸測試。

這兩件事是《系統功能與功能架構設計 V1.0》第（八）（九）（十）節反覆
要求的核心約束，一旦破功就是無聲的歷史資料毀損（改一份已發布問卷的
題目文字，既有填答的語意會跟著變，但沒有任何錯誤訊息）。因此獨立成
測試，避免日後重構時被摘掉。
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from .models import (
    BranchRule, Option, Question, Questionnaire, QuestionnaireResponse,
    QuestionnaireVersion, Section, Tier,
)


class VersionFixtureMixin:
    def build_draft_version(self):
        # Tier 0～5 由 migration 0002 建立，測試 DB 也會有，故用 get_or_create
        tier, _ = Tier.objects.get_or_create(
            code="tier1", defaults={"name": "Tier 1 日常低負擔健康檢核", "order": 1},
        )
        questionnaire = Questionnaire.objects.create(name="每日健康檢核", tier=tier)
        version = QuestionnaireVersion.objects.create(questionnaire=questionnaire, version_number=1)
        section = Section.objects.create(version=version, title="每日必填", order=1)
        fever = Question.objects.create(
            section=section, prompt="孩子今天是否有發燒？",
            question_type=Question.Type.SINGLE, order=1,
        )
        Option.objects.create(question=fever, label="沒有", value="no", order=1)
        Option.objects.create(question=fever, label="有", value="yes", order=2)
        followup = Section.objects.create(version=version, title="發燒追問", order=2)
        Question.objects.create(
            section=followup, prompt="最高體溫？",
            question_type=Question.Type.NUMBER, order=1,
            config={"min": 35, "max": 42, "step": 0.1, "unit": "°C"},
        )
        BranchRule.objects.create(
            trigger_question=fever, trigger_value="yes", target_section=followup,
        )
        return version, section, fever, followup


class PublishedVersionIsImmutableTests(VersionFixtureMixin, TestCase):
    def setUp(self):
        self.version, self.section, self.fever, self.followup = self.build_draft_version()

    def test_draft_content_is_editable(self):
        self.fever.prompt = "改過的題目"
        self.fever.save()
        self.assertEqual(Question.objects.get(pk=self.fever.pk).prompt, "改過的題目")

    def test_cannot_edit_question_of_published_version(self):
        self.version.publish()
        self.fever.prompt = "被竄改的題目"
        with self.assertRaises(ValidationError):
            self.fever.save()
        self.assertEqual(Question.objects.get(pk=self.fever.pk).prompt, "孩子今天是否有發燒？")

    def test_cannot_edit_option_of_published_version(self):
        self.version.publish()
        option = self.fever.options.first()
        option.label = "被竄改的選項"
        with self.assertRaises(ValidationError):
            option.save()

    def test_cannot_add_question_to_published_version(self):
        self.version.publish()
        with self.assertRaises(ValidationError):
            Question.objects.create(
                section=self.section, prompt="偷加的題目",
                question_type=Question.Type.TEXT, order=99,
            )

    def test_cannot_delete_section_of_published_version(self):
        self.version.publish()
        with self.assertRaises(ValidationError):
            self.followup.delete()

    def test_publish_requires_at_least_one_question(self):
        empty = QuestionnaireVersion.objects.create(
            questionnaire=self.version.questionnaire, version_number=99,
        )
        with self.assertRaises(ValidationError):
            empty.publish()

    def test_cannot_publish_twice(self):
        self.version.publish()
        with self.assertRaises(ValidationError):
            self.version.publish()

    def test_cannot_revert_published_to_draft(self):
        """把已發布版本改回草稿就能繞過內容鎖，必須擋在狀態轉換這關。"""
        self.version.publish()
        self.version.status = QuestionnaireVersion.Status.DRAFT
        with self.assertRaises(ValidationError):
            self.version.save()
        self.assertEqual(
            QuestionnaireVersion.objects.get(pk=self.version.pk).status,
            QuestionnaireVersion.Status.PUBLISHED,
        )

    def test_cannot_revert_retired_to_draft(self):
        self.version.publish()
        self.version.retire()
        self.version.status = QuestionnaireVersion.Status.DRAFT
        with self.assertRaises(ValidationError):
            self.version.save()

    def test_cannot_reactivate_retired_version(self):
        self.version.publish()
        self.version.retire()
        self.version.status = QuestionnaireVersion.Status.PUBLISHED
        with self.assertRaises(ValidationError):
            self.version.save()

    def test_draft_to_published_transition_is_allowed(self):
        self.version.status = QuestionnaireVersion.Status.PUBLISHED
        self.version.save()
        self.assertEqual(
            QuestionnaireVersion.objects.get(pk=self.version.pk).status,
            QuestionnaireVersion.Status.PUBLISHED,
        )


class CloneAsNewDraftTests(VersionFixtureMixin, TestCase):
    def setUp(self):
        self.version, self.section, self.fever, self.followup = self.build_draft_version()
        self.version.publish()

    def test_clone_copies_whole_tree_and_is_editable(self):
        v2 = self.version.clone_as_new_draft()

        self.assertEqual(v2.version_number, 2)
        self.assertEqual(v2.status, QuestionnaireVersion.Status.DRAFT)
        self.assertEqual(v2.sections.count(), 2)
        self.assertEqual(Question.objects.filter(section__version=v2).count(), 2)
        self.assertEqual(Option.objects.filter(question__section__version=v2).count(), 2)

        question = Question.objects.filter(section__version=v2, prompt=self.fever.prompt).get()
        question.prompt = "v2 改過的題目"
        question.save()  # 草稿，不應拋錯

    def test_clone_rewires_branch_rules_to_the_new_version(self):
        v2 = self.version.clone_as_new_draft()
        rule = BranchRule.objects.get(trigger_question__section__version=v2)

        # 分支必須指向新版本自己的題組，不能還指著 v1 的
        self.assertEqual(rule.target_section.version_id, v2.pk)
        self.assertEqual(rule.trigger_question.section.version_id, v2.pk)
        self.assertNotEqual(rule.target_section_id, self.followup.pk)

    def test_editing_clone_does_not_affect_the_published_original(self):
        v2 = self.version.clone_as_new_draft()
        question = Question.objects.filter(section__version=v2, prompt=self.fever.prompt).get()
        question.prompt = "v2 改過的題目"
        question.save()

        self.assertEqual(Question.objects.get(pk=self.fever.pk).prompt, "孩子今天是否有發燒？")


class AdminSmokeTests(VersionFixtureMixin, TestCase):
    """後台頁面能開、發布 action 能跑、已發布版本的內容 inline 轉唯讀。"""

    def setUp(self):
        self.version, self.section, self.fever, self.followup = self.build_draft_version()
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", "admin@example.com", "pw-for-test")
        self.client.force_login(self.admin)

    def test_key_admin_pages_load(self):
        for name in [
            "admin:questionnaires_questionnaire_changelist",
            "admin:questionnaires_questionnaireversion_changelist",
            "admin:questionnaires_section_changelist",
            "admin:questionnaires_question_changelist",
            "admin:questionnaires_questionnaireresponse_changelist",
            "admin:children_child_changelist",
        ]:
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_tier_zero_through_five_are_seeded(self):
        self.assertEqual(
            set(Tier.objects.filter(code__startswith="tier").values_list("code", flat=True)),
            {f"tier{i}" for i in range(6)},
        )

    def test_response_admin_supports_requested_filters(self):
        from django.contrib.admin.sites import site

        response_admin = site._registry[QuestionnaireResponse]
        self.assertTrue({
            "child", "status", "started_at", "version__questionnaire__tier",
            "version__questionnaire", "version__version_number",
        }.issubset(set(response_admin.list_filter)))
        self.assertEqual(response_admin.date_hierarchy, "started_at")

    def test_version_change_page_loads_for_draft_and_published(self):
        url = reverse("admin:questionnaires_questionnaireversion_change", args=[self.version.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.version.publish()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "複製為新版本")

    def test_eligibility_admin_form_presents_scheduling_controls(self):
        from questionnaires.admin import EligibilityRuleAdminForm

        form = EligibilityRuleAdminForm(data={
            "version": self.version.pk,
            "min_age_months": "",
            "max_age_months": "",
            "tracking_status": "",
            "period": "first_visit",
            "frequency": "weekly",
            "timing": "after_visit",
            "start_date": "2026-10-01",
            "end_date": "2026-12-31",
        })
        self.assertIn("frequency", form.fields)
        self.assertIn("period", form.fields)
        self.assertIn("timing", form.fields)
        self.assertIn("start_date", form.fields)
        self.assertIn("end_date", form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        rule = form.save()
        self.assertEqual(rule.condition_json["period"], "first_visit")
        self.assertEqual(rule.condition_json["frequency"], "weekly")
        self.assertEqual(rule.condition_json["timing"], "after_visit")

    def test_eligibility_admin_form_supports_all_period_choices(self):
        from questionnaires.admin import EligibilityRuleAdminForm

        for period in ("any", "first_visit", "daily", "phase", "tracking_period"):
            with self.subTest(period=period):
                form = EligibilityRuleAdminForm(data={
                    "version": self.version.pk,
                    "min_age_months": "",
                    "max_age_months": "",
                    "tracking_status": "",
                    "period": period,
                    "frequency": "any",
                    "timing": "any",
                    "start_date": "",
                    "end_date": "",
                })
                self.assertTrue(form.is_valid(), form.errors)

    def test_publish_action_publishes(self):
        url = reverse("admin:questionnaires_questionnaireversion_changelist")
        self.client.post(url, {
            "action": "action_publish",
            "_selected_action": [str(self.version.pk)],
        })
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, QuestionnaireVersion.Status.PUBLISHED)

    def test_clone_action_creates_draft(self):
        self.version.publish()
        url = reverse("admin:questionnaires_questionnaireversion_changelist")
        self.client.post(url, {
            "action": "action_clone",
            "_selected_action": [str(self.version.pk)],
        })
        self.assertEqual(self.version.questionnaire.versions.count(), 2)
        self.assertTrue(
            self.version.questionnaire.versions.filter(
                version_number=2, status=QuestionnaireVersion.Status.DRAFT
            ).exists()
        )

    def test_section_inline_is_readonly_once_published(self):
        from questionnaires.admin import QuestionnaireVersionAdmin
        from django.contrib.admin.sites import site

        self.version.publish()
        version_admin = QuestionnaireVersionAdmin(QuestionnaireVersion, site)
        section_inline = next(
            inline for inline in version_admin.get_inline_instances(_request(self.admin))
            if inline.model is Section
        )
        self.assertFalse(section_inline.has_add_permission(_request(self.admin), self.version))
        self.assertFalse(section_inline.has_change_permission(_request(self.admin), self.version))


def _request(user):
    from django.test import RequestFactory

    request = RequestFactory().get("/")
    request.user = user
    return request


class SeedDataTests(TestCase):
    def test_tier_seed_migration_created_tier_0_through_5(self):
        codes = set(Tier.objects.values_list("code", flat=True))
        self.assertTrue({"tier0", "tier1", "tier2", "tier3", "tier4", "tier5"}.issubset(codes))

    def test_seed_demo_questionnaire_builds_fever_branch(self):
        from django.core.management import call_command
        from io import StringIO

        call_command("seed_demo_questionnaire", "--publish", stdout=StringIO())

        questionnaire = Questionnaire.objects.get(name="每日健康檢核（示範）")
        version = questionnaire.current_published_version()
        self.assertIsNotNone(version)

        fever = Question.objects.get(section__version=version, prompt="孩子今天是否有發燒？")
        followup = Section.objects.get(version=version, title="發燒追問")
        rule = BranchRule.objects.get(trigger_question=fever)

        self.assertEqual(rule.trigger_value, "yes")
        self.assertEqual(rule.action, BranchRule.Action.SHOW)
        self.assertEqual(rule.target_section_id, followup.pk)

    def test_seed_demo_questionnaire_is_idempotent(self):
        from django.core.management import call_command
        from io import StringIO

        call_command("seed_demo_questionnaire", stdout=StringIO())
        call_command("seed_demo_questionnaire", stdout=StringIO())
        self.assertEqual(
            Questionnaire.objects.filter(name="每日健康檢核（示範）").count(), 1
        )


class BranchRuleTargetConstraintTests(VersionFixtureMixin, TestCase):
    def setUp(self):
        self.version, self.section, self.fever, self.followup = self.build_draft_version()

    def _create(self, **kwargs):
        with transaction.atomic():
            return BranchRule.objects.create(
                trigger_question=self.fever, trigger_value="yes", **kwargs
            )

    def test_rejects_multiple_targets(self):
        with self.assertRaises(IntegrityError):
            self._create(
                target_section=self.followup,
                target_questionnaire=self.version.questionnaire,
            )

    def test_rejects_no_target(self):
        with self.assertRaises(IntegrityError):
            self._create()

    def test_accepts_exactly_one_target(self):
        self.assertIsNotNone(self._create(target_section=self.followup))
        self.assertIsNotNone(self._create(target_question=self.fever))
        self.assertIsNotNone(self._create(target_questionnaire=self.version.questionnaire))
