from django.conf import settings
from django.db import models


class ParentProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, related_name="parent_profile", on_delete=models.CASCADE,
    )
    phone_number = models.CharField("電話號碼", max_length=30)

    def __str__(self):
        return self.user.get_full_name() or self.user.get_username()
