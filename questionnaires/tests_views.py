"""家長端入口頁測試。"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from children.models import Child

from .models import (
    EligibilityRule, Question, Questionnaire, QuestionnaireResponse,
    QuestionnaireVersion, Section, Tier,
)


class ChildHomeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.parent = User.objects.create_user("parent", password="pw")
        self.other_parent = User.objects.create_user("other", password="pw")

        tier, _ = Tier.objects.get_or_create(code="tier1", defaults={"name": "Tier 1", "order": 1})
        self.q = Questionnaire.objects.create(name="每日健康檢核", tier=tier)
        self.version = QuestionnaireVersion.objects.create(questionnaire=self.q, version_number=1)
        section = Section.objects.create(version=self.version, title="每日", order=1)
        Question.objects.create(
            section=section, prompt="今天好嗎？", question_type=Question.Type.TEXT, order=1,
        )
        EligibilityRule.objects.create(version=self.version, min_age_months=0, max_age_months=120)
        self.version.publish()

        self.child = Child.objects.create(
            name="小明", birth_date=timezone.localdate() - timedelta(days=365 * 3),
            guardian=self.parent,
        )

    def test_unrecorded_questionnaire_shows_as_pending(self):
        self.client.force_login(self.parent)
        res = self.client.get(reverse("questionnaires:child-home", args=[self.child.id]))
        self.assertContains(res, "每日健康檢核")
        self.assertContains(res, "未記錄")
        self.assertContains(res, "開始填答")

    def test_in_progress_shows_continue(self):
        QuestionnaireResponse.objects.create(child=self.child, version=self.version)
        self.client.force_login(self.parent)
        res = self.client.get(reverse("questionnaires:child-home", args=[self.child.id]))
        self.assertContains(res, "未完成")
        self.assertContains(res, "繼續填答")

    def test_completed_moves_to_history(self):
        r = QuestionnaireResponse.objects.create(child=self.child, version=self.version)
        r.mark_completed()
        self.client.force_login(self.parent)
        res = self.client.get(reverse("questionnaires:child-home", args=[self.child.id]))
        self.assertContains(res, "目前沒有需要填寫的問卷")
        self.assertContains(res, "已完成")

    def test_other_parent_cannot_view_this_child(self):
        self.client.force_login(self.other_parent)
        res = self.client.get(reverse("questionnaires:child-home", args=[self.child.id]))
        self.assertEqual(res.status_code, 404)

    def test_parent_can_edit_owned_child_profile(self):
        self.client.force_login(self.parent)
        url = reverse("questionnaires:child-edit", args=[self.child.id])
        original_birth_date = self.child.birth_date
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "編輯孩子資料")
        self.assertContains(response, f'value="{original_birth_date:%Y-%m-%d}"')
        response = self.client.post(url, {
            "name": "小明更新", "national_id": "A123456789",
            "birth_date": original_birth_date.isoformat(),
            "tracking_status": "氣喘追蹤",
        })
        self.assertRedirects(response, reverse("questionnaires:child-home", args=[self.child.id]))
        self.child.refresh_from_db()
        self.assertEqual(self.child.name, "小明更新")
        self.assertEqual(self.child.national_id, "A123456789")
        self.assertEqual(self.child.birth_date, original_birth_date)
        self.assertEqual(self.child.guardian, self.parent)

    def test_parent_cannot_edit_another_parents_child(self):
        self.client.force_login(self.other_parent)
        response = self.client.get(reverse("questionnaires:child-edit", args=[self.child.id]))
        self.assertEqual(response.status_code, 404)

    def test_staff_can_view_any_child(self):
        User = get_user_model()
        staff = User.objects.create_user("staff", password="pw", is_staff=True)
        self.client.force_login(staff)
        res = self.client.get(reverse("questionnaires:child-home", args=[self.child.id]))
        self.assertEqual(res.status_code, 200)

    def test_parent_home_lists_children(self):
        Child.objects.create(
            name="小華", birth_date=timezone.localdate() - timedelta(days=365 * 5),
            guardian=self.parent,
        )
        self.client.force_login(self.parent)
        res = self.client.get(reverse("questionnaires:parent-home"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "小明")
        self.assertContains(res, "小華")

    def test_parent_home_shows_profile_link_when_no_children(self):
        User = get_user_model()
        childless = User.objects.create_user("childless", password="pw")
        self.client.force_login(childless)
        res = self.client.get(reverse("questionnaires:parent-home"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "尚未新增孩子資料")
        self.assertContains(res, reverse("accounts:profile"))

    def test_parent_can_open_fill_page_without_token(self):
        self.client.force_login(self.parent)
        url = reverse("questionnaires:fill", args=[self.version.id]) + f"?child={self.child.id}"
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "每日健康檢核")
        self.assertContains(res, 'data-child-id="%s"' % self.child.id)

    def test_requires_login(self):
        res = self.client.get(reverse("questionnaires:child-home", args=[self.child.id]))
        self.assertEqual(res.status_code, 302)
        self.assertIn("/accounts/login/", res["Location"])
