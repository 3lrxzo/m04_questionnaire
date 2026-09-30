from datetime import timedelta

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from children.models import Child
from .models import ParentProfile

User = get_user_model()


class ParentAuthenticationForm(AuthenticationForm):
    username = forms.CharField(
        label="身分證",
        help_text="請輸入註冊時使用的身分證字號。",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "身分證"
        self.fields["username"].help_text = "請輸入註冊時使用的身分證字號。"


class ParentProfileForm(forms.ModelForm):
    phone_number = forms.CharField(label="電話號碼", max_length=30)
    password1 = forms.CharField(
        label="新密碼（不修改請留空）", required=False, initial="",
        widget=forms.PasswordInput,
    )
    password2 = forms.CharField(
        label="確認新密碼", required=False, initial="",
        widget=forms.PasswordInput,
    )

    class Meta:
        model = User
        fields = ("first_name", "username", "email")
        labels = {
            "first_name": "姓名",
            "username": "身分證",
            "email": "電子郵件",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = (
            ParentProfile.objects.filter(user_id=self.instance.pk).first()
            if self.instance.pk else None
        )
        if profile:
            self.fields["phone_number"].initial = profile.phone_number
        self.fields["username"].help_text = "此身分證字號也是你的登入帳號。"
        self.order_fields(("first_name", "username", "phone_number", "email", "password1", "password2"))

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 or password2:
            if password1 != password2:
                self.add_error("password2", "兩次輸入的密碼不一致。")
            elif password1:
                validate_password(password1, self.instance)
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password1")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        profile, _ = ParentProfile.objects.get_or_create(user=user)
        profile.phone_number = self.cleaned_data["phone_number"]
        if commit:
            profile.save()
        return user


class ParentRegistrationForm(UserCreationForm):
    """家長註冊。沿用 Django 內建 User，僅多收 email。

    院方 APP 介接後家長身分會改由 APP 帶入，這個表單只供展示與測試。
    """

    username = forms.CharField(
        label="身分證", max_length=150, required=True,
        help_text="請輸入本人身分證字號；註冊後將作為登入帳號。",
    )
    email = forms.EmailField(label="電子郵件", required=True)
    phone_number = forms.CharField(label="電話號碼", max_length=30, required=True)
    full_name = forms.CharField(label="姓名", max_length=60, required=True)
    password1 = forms.CharField(
        label="密碼", strip=False, widget=forms.PasswordInput,
        help_text=None,
    )
    password2 = forms.CharField(
        label="確認密碼", strip=False, widget=forms.PasswordInput,
        help_text="請再次輸入相同密碼以確認。",
    )

    class Meta:
        model = User
        fields = ("full_name", "username", "phone_number", "email")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["full_name"]
        if commit:
            user.save()
            ParentProfile.objects.update_or_create(
                user=user,
                defaults={"phone_number": self.cleaned_data["phone_number"]},
            )
        return user


class ChildForm(forms.ModelForm):
    class Meta:
        model = Child
        fields = ("name", "national_id", "birth_date", "tracking_status")
        widgets = {
            "birth_date": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date"},
            ),
        }
        labels = {
            "national_id": "身分證",
            "tracking_status": "追蹤狀態",
        }
        help_texts = {
            "name": "若姓名尚未確定，請填「XXX之子」或「XXX之女」。",
            "national_id": "出生未超過60天可留空；出生超過60天則必須填寫。",
        }

    def clean(self):
        cleaned_data = super().clean()
        birth_date = cleaned_data.get("birth_date")
        national_id = cleaned_data.get("national_id")
        if (
            birth_date
            and (timezone.localdate() - birth_date) > timedelta(days=60)
            and not national_id
        ):
            self.add_error("national_id", "孩子出生已超過60天，請填寫身分證。")
        return cleaned_data
