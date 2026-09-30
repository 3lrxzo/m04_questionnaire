from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from datetime import timedelta

from children.models import Child


class UserAdminPermissionTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            "root", "root@example.com", "root-test-password",
        )
        self.staff = User.objects.create_user(
            "staff", "staff@example.com", "staff-test-password", is_staff=True,
        )
        self.staff.user_permissions.set(
            Permission.objects.filter(
                content_type__app_label="auth",
                codename__in=("add_user", "change_user", "delete_user"),
            )
        )
        self.regular_user = User.objects.create_user(
            "parent", "parent@example.com", "parent-test-password",
        )

    def test_only_superuser_can_add_or_delete_users_in_admin(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("admin:auth_user_add")).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("admin:auth_user_delete", args=[self.regular_user.pk]),
                {"post": "yes"},
            ).status_code,
            403,
        )
        self.assertTrue(User.objects.filter(pk=self.regular_user.pk).exists())

    def test_only_superuser_can_change_an_admin_account(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:auth_user_change", args=[self.superuser.pk]))
        self.assertEqual(response.status_code, 302)

    def test_staff_cannot_promote_a_regular_user_to_admin(self):
        self.client.force_login(self.staff)
        change_url = reverse("admin:auth_user_change", args=[self.regular_user.pk])
        response = self.client.get(change_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="is_staff"')
        self.assertNotContains(response, 'name="is_superuser"')

        response = self.client.post(change_url, {
            "username": self.regular_user.username,
            "first_name": "",
            "last_name": "",
            "email": self.regular_user.email,
            "is_active": "on",
            "is_staff": "on",
            "is_superuser": "on",
            "_save": "儲存",
        })
        self.assertEqual(response.status_code, 302)
        self.regular_user.refresh_from_db()
        self.assertFalse(self.regular_user.is_staff)
        self.assertFalse(self.regular_user.is_superuser)

    def test_superuser_can_open_user_creation_page(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(reverse("admin:auth_user_add")).status_code, 200)


class RegistrationFlowTests(TestCase):
    def test_register_creates_user_logs_in_and_goes_to_add_child(self):
        url = reverse("accounts:register")
        register_page = self.client.get(url)
        self.assertContains(register_page, "身分證")
        self.assertContains(register_page, "註冊後將作為登入帳號")
        self.assertContains(register_page, "電話號碼")
        self.assertContains(register_page, "確認密碼")
        form_fields = list(register_page.context["form"].fields)
        self.assertEqual(
            form_fields,
            ["full_name", "username", "phone_number", "email", "password1", "password2"],
        )
        res = self.client.post(url, {
            "username": "parent01",
            "full_name": "王小明",
            "phone_number": "0912345678",
            "email": "p1@example.com",
            "password1": "veryStrongPw!23",
            "password2": "veryStrongPw!23",
        })
        self.assertRedirects(res, reverse("questionnaires:child-add"))
        user = User.objects.get(username="parent01")
        self.assertEqual(user.first_name, "王小明")
        self.assertEqual(user.email, "p1@example.com")
        self.assertEqual(user.parent_profile.phone_number, "0912345678")
        # 已登入
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_register_rejects_mismatched_passwords(self):
        res = self.client.post(reverse("accounts:register"), {
            "username": "p", "full_name": "x", "phone_number": "0911111111",
            "email": "x@example.com",
            "password1": "veryStrongPw!23", "password2": "different!45",
        })
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(username="p").exists())

    def test_login_then_logout(self):
        User.objects.create_user("parent02", password="pw12345678")
        login_url = reverse("accounts:login")
        self.assertContains(self.client.get(login_url), "身分證")
        self.assertContains(self.client.get(login_url), "註冊時使用的身分證字號")
        res = self.client.post(login_url, {
            "username": "parent02", "password": "pw12345678",
        })
        self.assertRedirects(res, reverse("questionnaires:parent-home"),
                             fetch_redirect_response=False)
        res = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(res, reverse("questionnaires:landing"),
                             fetch_redirect_response=False)


class ParentProfileTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(
            "profile-parent", password="profile-test-password",
            email="old@example.com", first_name="原姓名",
        )
        self.client.force_login(self.parent)

    def test_parent_can_update_profile_and_password(self):
        url = reverse("accounts:profile")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"]["password1"].value(), "")
        self.assertEqual(response.context["form"]["password2"].value(), "")
        self.assertNotContains(response, 'name="password1" value=')
        self.assertNotContains(response, 'name="password2" value=')

        response = self.client.post(url, {
            "first_name": "新姓名",
            "username": "A123456789",
            "phone_number": "0987654321",
            "email": "new@example.com",
            "password1": "newStrongPassword!456",
            "password2": "newStrongPassword!456",
        })
        self.assertRedirects(response, url)
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.first_name, "新姓名")
        self.assertEqual(self.parent.username, "A123456789")
        self.assertEqual(self.parent.parent_profile.phone_number, "0987654321")
        self.assertEqual(self.parent.email, "new@example.com")
        self.assertFalse(self.parent.is_staff)
        self.assertTrue(self.parent.check_password("newStrongPassword!456"))

    def test_parent_password_confirmation_must_match(self):
        url = reverse("accounts:profile")
        response = self.client.post(url, {
            "first_name": "原姓名",
            "username": "profile-parent",
            "phone_number": "0912345678",
            "email": "old@example.com",
            "password1": "newStrongPassword!456",
            "password2": "differentStrongPassword!456",
        })
        self.assertEqual(response.status_code, 200)
        self.parent.refresh_from_db()
        self.assertTrue(self.parent.check_password("profile-test-password"))

    def test_profile_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])


class ChildRegistrationTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user("parent", password="pw12345678")
        self.client.force_login(self.parent)

    def test_add_child_binds_to_current_user_and_redirects_to_child_home(self):
        res = self.client.post(reverse("questionnaires:child-add"), {
            "name": "王小寶",
            "national_id": "",
            "birth_date": (timezone.localdate() - timedelta(days=60)).isoformat(),
            "tracking_status": "",
        })
        child = Child.objects.get(name="王小寶")
        self.assertEqual(child.guardian, self.parent)
        self.assertEqual(child.national_id, "")
        self.assertRedirects(
            res, reverse("questionnaires:child-home", args=[child.id]),
            fetch_redirect_response=False,
        )

    def test_add_child_requires_login(self):
        self.client.logout()
        res = self.client.get(reverse("questionnaires:child-add"))
        self.assertEqual(res.status_code, 302)
        self.assertIn("/accounts/login/", res["Location"])

    def test_child_form_has_optional_id_and_tracking_status_choices(self):
        response = self.client.get(reverse("questionnaires:child-add"))
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertFalse(form.fields["national_id"].required)
        self.assertEqual(
            form.fields["tracking_status"].choices,
            [
                ("", "請選擇"),
                ("一般", "一般"),
                ("氣喘追蹤", "氣喘追蹤"),
                ("早療追蹤", "早療追蹤"),
                ("其他", "其他"),
            ],
        )
        self.assertContains(response, "XXX之子")
        self.assertContains(response, "出生未超過60天可留空")

    def test_child_older_than_60_days_requires_national_id(self):
        response = self.client.post(reverse("questionnaires:child-add"), {
            "name": "小寶",
            "national_id": "",
            "birth_date": (timezone.localdate() - timedelta(days=61)).isoformat(),
            "tracking_status": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "孩子出生已超過60天，請填寫身分證。")
        self.assertFalse(Child.objects.filter(name="小寶").exists())

    def test_child_exactly_60_days_old_does_not_require_national_id(self):
        response = self.client.post(reverse("questionnaires:child-add"), {
            "name": "小寶",
            "national_id": "",
            "birth_date": (timezone.localdate() - timedelta(days=60)).isoformat(),
            "tracking_status": "",
        })
        self.assertRedirects(
            response,
            reverse("questionnaires:child-home", args=[Child.objects.get(name="小寶").id]),
            fetch_redirect_response=False,
        )


class LandingTests(TestCase):
    def test_landing_is_public_and_shows_both_roles(self):
        res = self.client.get(reverse("questionnaires:landing"))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "家長")
        self.assertContains(res, "醫護人員")
