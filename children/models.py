from django.conf import settings
from django.db import models
from django.utils import timezone


class Child(models.Model):
    """兒童基本資料

    刻意做薄：只保留「問卷適用規則」判斷得用到的最小欄位（年齡、追蹤狀態），
    不試圖成為完整的病歷主檔。院方日後若提供共用的兒童主檔，本 model 會退化
    成對接用的識別映射，屆時 medical_no 就是接點。
    """

    name = models.CharField("姓名", max_length=100)
    birth_date = models.DateField("出生日期", help_text="用於計算月齡，供問卷適用規則比對")
    national_id = models.CharField("身分證（選填）", max_length=20, blank=True)
    medical_no = models.CharField(
        "病歷號", max_length=50, blank=True, db_index=True,
        help_text="院內識別碼；日後對接共用兒童主檔時作為接點",
    )
    guardian = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="主要照顧者帳號",
        related_name="children",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        help_text="家長端登入後據此判斷可填答哪些兒童的問卷",
    )
    tracking_status = models.CharField(
        "追蹤狀態", max_length=50, blank=True, db_index=True,
        choices=(
            ("", "請選擇"),
            ("一般", "一般"),
            ("氣喘追蹤", "氣喘追蹤"),
            ("早療追蹤", "早療追蹤"),
            ("其他", "其他"),
        ),
    )
    is_active = models.BooleanField("啟用", default=True)
    created_at = models.DateTimeField("建立時間", auto_now_add=True)

    class Meta:
        verbose_name = "兒童"
        verbose_name_plural = "兒童"
        ordering = ["name", "birth_date"]

    def __str__(self):
        return f"{self.name}（{self.birth_date:%Y-%m-%d}）"

    def age_months(self, as_of=None):
        """回傳指定日期當下的足月數，供 EligibilityRule 的月齡區間比對。

        刻意接受 as_of 參數而非寫成 property：判斷「這份問卷當時該不該填」
        有時得回推到過去某個時間點，而不是永遠用今天。
        """
        as_of = as_of or timezone.localdate()
        months = (as_of.year - self.birth_date.year) * 12 + (as_of.month - self.birth_date.month)
        if as_of.day < self.birth_date.day:
            months -= 1
        return max(months, 0)
