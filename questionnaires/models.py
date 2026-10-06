"""問卷管理系統的資料模型。

設計主軸（來自《系統功能與功能架構設計 V1.0》）：
問卷內容不寫死於程式碼，全部由後台資料驅動；Tier 0～Tier 5 是第一階段的
最低支援情境，不是系統上限。因此凡是「兒科部日後可能想自己新增」的東西
（分類、分層、題型選項、分支條件），都以資料表而非程式常數表達。
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction


# ---------------------------------------------------------------------------
# 分類與分層：以資料維護，而非程式常數
# ---------------------------------------------------------------------------

class Category(models.Model):
    """問卷分類（健康管理／日常追蹤／疾病／心理／功能…）"""

    code = models.CharField("代碼", max_length=30, unique=True)
    name = models.CharField("名稱", max_length=100)
    order = models.PositiveIntegerField("排序", default=0)
    is_active = models.BooleanField("啟用", default=True)

    class Meta:
        verbose_name = "問卷分類"
        verbose_name_plural = "問卷分類"
        ordering = ["order", "code"]

    def __str__(self):
        return self.name


class Tier(models.Model):
    """分層（Tier）

    正式文件（四）明訂「後台應可新增新的問卷類型、分類或層級，無須因新增
    問卷而重新開發 APP 程式」，所以 Tier 不能是 TextChoices 常數 ——
    否則新增 Tier 6 就得改程式碼、重新部署，直接違反該條要求。
    Tier 0～Tier 5 由初始資料（fixture）建立。
    """

    code = models.CharField("代碼", max_length=30, unique=True, help_text="例如 tier1")
    name = models.CharField("名稱", max_length=100, help_text="例如 Tier 1 日常低負擔健康檢核")
    order = models.PositiveIntegerField("排序", default=0)
    description = models.TextField("應用定位說明", blank=True)
    is_active = models.BooleanField("啟用", default=True)

    class Meta:
        verbose_name = "分層（Tier）"
        verbose_name_plural = "分層（Tier）"
        ordering = ["order", "code"]

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# 問卷主檔與版本
# ---------------------------------------------------------------------------

class Questionnaire(models.Model):
    """問卷主檔 —— 只存名稱／分類／Tier 等中繼資料，題目屬於各個版本"""

    name = models.CharField("問卷名稱", max_length=200)
    description = models.TextField("說明", blank=True)
    category = models.ForeignKey(
        Category, verbose_name="分類", related_name="questionnaires",
        null=True, blank=True, on_delete=models.PROTECT,
    )
    tier = models.ForeignKey(
        Tier, verbose_name="分層", related_name="questionnaires",
        null=True, blank=True, on_delete=models.PROTECT,
        help_text="可留空：問卷不必然隸屬於某個 Tier",
    )
    is_active = models.BooleanField("啟用", default=True)
    created_at = models.DateTimeField("建立時間", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="建立者", related_name="created_questionnaires",
        null=True, blank=True, on_delete=models.SET_NULL,
    )

    class Meta:
        verbose_name = "問卷"
        verbose_name_plural = "問卷"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def current_published_version(self):
        """取目前生效的已發布版本（版號最大者）。

        分支規則指向 Questionnaire 而非特定版本，觸發時就是走這裡取版本，
        以符合正式文件（八）「發布 V2 後，新的填答使用 V2」。
        """
        return (
            self.versions.filter(status=QuestionnaireVersion.Status.PUBLISHED)
            .order_by("-version_number")
            .first()
        )


class QuestionnaireVersion(models.Model):
    """問卷版本 —— 已發布版本不可覆寫，改版即建新版本"""

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PUBLISHED = "published", "已發布"
        RETIRED = "retired", "已停用"

    questionnaire = models.ForeignKey(
        Questionnaire, verbose_name="問卷", related_name="versions", on_delete=models.CASCADE,
    )
    version_number = models.PositiveIntegerField("版本號")
    status = models.CharField("狀態", max_length=20, choices=Status.choices, default=Status.DRAFT)
    change_note = models.TextField("改版說明", blank=True)
    published_at = models.DateTimeField("發布時間", null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="發布者",
        related_name="published_questionnaire_versions",
        null=True, blank=True, on_delete=models.SET_NULL,
    )
    retired_at = models.DateTimeField("停用時間", null=True, blank=True)
    created_at = models.DateTimeField("建立時間", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="建立者", related_name="created_questionnaire_versions",
        null=True, blank=True, on_delete=models.SET_NULL,
    )

    class Meta:
        verbose_name = "問卷版本"
        verbose_name_plural = "問卷版本"
        ordering = ["questionnaire", "-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["questionnaire", "version_number"],
                name="unique_version_number_per_questionnaire",
            ),
        ]

    def __str__(self):
        return f"{self.questionnaire.name} v{self.version_number}（{self.get_status_display()}）"

    # 允許的狀態轉換。刻意沒有任何一條路可以回到「草稿」——
    # 否則只要把已發布版本改回草稿就能繞過內容鎖，整套版本保護形同虛設。
    ALLOWED_TRANSITIONS = {
        Status.DRAFT: {Status.PUBLISHED},
        Status.PUBLISHED: {Status.RETIRED},
        Status.RETIRED: set(),
    }

    @property
    def is_editable(self):
        """只有草稿可以改內容。這是整個系統最重要的一條約束。"""
        return self.status == self.Status.DRAFT

    def save(self, *args, **kwargs):
        if self.pk:
            previous = (
                QuestionnaireVersion.objects
                .filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            if previous is not None and previous != self.status:
                if self.status not in self.ALLOWED_TRANSITIONS.get(previous, set()):
                    raise ValidationError(
                        f"不允許的狀態轉換：{self.Status(previous).label} → "
                        f"{self.Status(self.status).label}。"
                        f"已發布的版本不可退回草稿，請改用「複製為新版本」。"
                    )
        super().save(*args, **kwargs)

    @transaction.atomic
    def publish(self, published_by=None):
        from django.utils import timezone

        if self.status != self.Status.DRAFT:
            raise ValidationError(f"只有草稿可以發布，此版本目前為「{self.get_status_display()}」。")
        if not Question.objects.filter(section__version=self).exists():
            raise ValidationError("此版本尚無任何題目，無法發布。")
        self.status = self.Status.PUBLISHED
        self.published_at = timezone.now()
        self.published_by = published_by
        self.save(update_fields=["status", "published_at", "published_by"])

    @transaction.atomic
    def retire(self):
        from django.utils import timezone

        if self.status != self.Status.PUBLISHED:
            raise ValidationError("只有已發布的版本可以停用。")
        self.status = self.Status.RETIRED
        self.retired_at = timezone.now()
        self.save(update_fields=["status", "retired_at"])

    @transaction.atomic
    def clone_as_new_draft(self, created_by=None):
        """深拷貝本版本的全部內容成為新的草稿版本。

        這是「修改已發布問卷」的唯一正當途徑：正式文件（八）要求既有填答
        必須永遠指向當時的版本，所以不能就地改，只能複製後改新版。
        """
        next_number = (
            QuestionnaireVersion.objects
            .filter(questionnaire_id=self.questionnaire_id)
            .aggregate(models.Max("version_number"))["version_number__max"] or 0
        ) + 1

        new_version = QuestionnaireVersion.objects.create(
            questionnaire_id=self.questionnaire_id,
            version_number=next_number,
            status=self.Status.DRAFT,
            change_note=f"複製自 v{self.version_number}",
            created_by=created_by or self.created_by or self.questionnaire.created_by,
        )

        section_map, question_map = {}, {}
        for section in self.sections.all():
            new_section = Section.objects.create(
                version=new_version, title=section.title,
                description=section.description, order=section.order,
                is_active=section.is_active,
            )
            section_map[section.pk] = new_section
            for question in section.questions.all():
                new_question = Question.objects.create(
                    section=new_section, prompt=question.prompt,
                    help_text=question.help_text, question_type=question.question_type,
                    required=question.required, order=question.order,
                    is_active=question.is_active, config=question.config,
                )
                question_map[question.pk] = new_question
                for option in question.options.all():
                    Option.objects.create(
                        question=new_question, label=option.label,
                        value=option.value, order=option.order,
                        is_active=option.is_active,
                    )

        for rule in BranchRule.objects.filter(trigger_question__section__version=self):
            BranchRule.objects.create(
                trigger_question=question_map[rule.trigger_question_id],
                trigger_operator=rule.trigger_operator,
                trigger_value=rule.trigger_value,
                action=rule.action,
                target_section=section_map.get(rule.target_section_id),
                target_question=question_map.get(rule.target_question_id),
                # 跨問卷觸發指向另一份問卷主檔，原樣沿用
                target_questionnaire=rule.target_questionnaire,
            )

        for rule in self.eligibility_rules.all():
            EligibilityRule.objects.create(
                version=new_version,
                min_age_months=rule.min_age_months,
                max_age_months=rule.max_age_months,
                tracking_status=rule.tracking_status,
                condition_json=rule.condition_json,
            )

        return new_version


# ---------------------------------------------------------------------------
# 版本內容：受「已發布不可覆寫」保護
# ---------------------------------------------------------------------------

class VersionScopedModel(models.Model):
    """隸屬於某個問卷版本的內容物件（題組／題目／選項／分支／適用規則）。

    正式文件（八）（九）（十）反覆要求「已發布版本不得直接覆寫」。這個檢查
    放在 model 層而不是只在 Admin 設 readonly —— 因為 Admin 只是眾多入口
    之一，shell、DRF、日後的 HTMX 後台頁面都繞得過去。改一份已發布問卷的
    題目文字，等同於默默竄改歷史填答的語意（Answer 只存答案值，題目文字
    是跟著 Question 走的），這是無聲的資料毀損，必須從源頭擋。

    已知邊界：queryset.update() 與 loaddata 會繞過 save()。前者請避免用於
    版本內容；後者是刻意保留的，測試資料 fixture 需要直接載入已發布版本。
    """

    class Meta:
        abstract = True

    def owning_version(self):
        raise NotImplementedError

    def _assert_editable(self):
        version = self.owning_version()
        if version is not None and not version.is_editable:
            raise ValidationError(
                f"{version} 已非草稿狀態，內容不可修改。"
                f"請改用「複製為新版本」建立草稿後再編輯。"
            )

    def save(self, *args, **kwargs):
        self._assert_editable()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._assert_editable()
        super().delete(*args, **kwargs)


class Section(VersionScopedModel):
    """題組 —— 一組相關題目，也是條件式追問的觸發單位"""

    version = models.ForeignKey(
        QuestionnaireVersion, verbose_name="問卷版本",
        related_name="sections", on_delete=models.CASCADE,
    )
    title = models.CharField("題組名稱", max_length=200)
    description = models.TextField("說明", blank=True)
    order = models.PositiveIntegerField("排序", default=0)
    is_active = models.BooleanField("啟用", default=True)

    class Meta:
        verbose_name = "題組"
        verbose_name_plural = "題組"
        ordering = ["version", "order"]

    def __str__(self):
        return self.title

    def owning_version(self):
        return self.version


class Question(VersionScopedModel):
    class Type(models.TextChoices):
        SINGLE = "single", "單選"
        MULTI = "multi", "複選"
        NUMBER = "number", "數值"
        TEXT = "text", "簡短文字"
        SCALE = "scale", "量表"
        DATETIME = "datetime", "日期／時間"

    section = models.ForeignKey(
        Section, verbose_name="題組", related_name="questions", on_delete=models.CASCADE,
    )
    prompt = models.CharField("題目", max_length=500)
    help_text = models.CharField("補充說明", max_length=500, blank=True)
    question_type = models.CharField("題型", max_length=20, choices=Type.choices)
    required = models.BooleanField("必填", default=True)
    order = models.PositiveIntegerField("排序", default=0)
    is_active = models.BooleanField("啟用", default=True)
    config = models.JSONField(
        "題型設定", default=dict, blank=True,
        help_text="依題型放置額外設定，例如數值題的 "
                  '{"min": 35, "max": 42, "step": 0.1, "unit": "°C"}；'
                  '量表題的 {"min": 0, "max": 10}。'
                  "刻意用 JSON 而非開一堆欄位，避免為少數題型撐大資料表",
    )

    class Meta:
        verbose_name = "題目"
        verbose_name_plural = "題目"
        ordering = ["section", "order"]

    def __str__(self):
        return self.prompt

    def owning_version(self):
        return self.section.version


class Option(VersionScopedModel):
    """選項（單選／複選／量表用）"""

    question = models.ForeignKey(
        Question, verbose_name="題目", related_name="options", on_delete=models.CASCADE,
    )
    label = models.CharField("選項文字", max_length=200)
    value = models.CharField("選項值", max_length=100, help_text="存入填答紀錄的實際值，分支條件也比對此值")
    order = models.PositiveIntegerField("排序", default=0)
    is_active = models.BooleanField("啟用", default=True)

    class Meta:
        verbose_name = "選項"
        verbose_name_plural = "選項"
        ordering = ["question", "order"]
        constraints = [
            models.UniqueConstraint(fields=["question", "value"], name="unique_option_value_per_question"),
        ]

    def __str__(self):
        return self.label

    def owning_version(self):
        return self.question.section.version


class BranchRule(VersionScopedModel):
    """分支條件

    正式文件（三）列了兩條「必要」需求：分支要能決定「後續題目、題組或
    指定問卷是否顯示」，以及「依前一層或前一問卷結果觸發下一 Tier 或指定
    問卷」。所以觸發目標有三種，三者擇一（由 DB CheckConstraint 強制）。
    """

    class Operator(models.TextChoices):
        EQ = "eq", "等於"
        NEQ = "neq", "不等於"
        IN = "in", "屬於（逗號分隔多值）"
        GT = "gt", "大於"
        GTE = "gte", "大於等於"
        LT = "lt", "小於"
        LTE = "lte", "小於等於"
        ANSWERED = "answered", "已作答（不論答什麼）"

    class Action(models.TextChoices):
        SHOW = "show", "顯示"
        HIDE = "hide", "隱藏"

    trigger_question = models.ForeignKey(
        Question, verbose_name="觸發題目", related_name="triggers", on_delete=models.CASCADE,
    )
    trigger_operator = models.CharField(
        "比較方式", max_length=20, choices=Operator.choices, default=Operator.EQ,
    )
    trigger_value = models.CharField(
        "觸發值", max_length=200, blank=True,
        help_text="比對 Option.value；數值題直接填數字；「已作答」不需填",
    )
    action = models.CharField("動作", max_length=20, choices=Action.choices, default=Action.SHOW)

    target_section = models.ForeignKey(
        Section, verbose_name="目標題組", related_name="triggered_by",
        null=True, blank=True, on_delete=models.CASCADE,
    )
    target_question = models.ForeignKey(
        Question, verbose_name="目標題目", related_name="targeted_by",
        null=True, blank=True, on_delete=models.CASCADE,
    )
    target_questionnaire = models.ForeignKey(
        Questionnaire, verbose_name="目標問卷", related_name="triggered_by",
        null=True, blank=True, on_delete=models.SET_NULL,
        help_text="跨問卷／跨 Tier 承接。刻意指向問卷主檔而非特定版本，"
                  "觸發時才取當下已發布的最新版",
    )

    class Meta:
        verbose_name = "分支條件"
        verbose_name_plural = "分支條件"
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(target_section__isnull=False, target_question__isnull=True,
                             target_questionnaire__isnull=True)
                    | models.Q(target_section__isnull=True, target_question__isnull=False,
                               target_questionnaire__isnull=True)
                    | models.Q(target_section__isnull=True, target_question__isnull=True,
                               target_questionnaire__isnull=False)
                ),
                name="branchrule_exactly_one_target",
                violation_error_message="目標題組／目標題目／目標問卷必須且只能擇一填寫。",
            ),
        ]

    def __str__(self):
        target = self.target_section or self.target_question or self.target_questionnaire
        if self.trigger_operator == self.Operator.ANSWERED:
            cond = "有作答"
        else:
            # 觸發值若對應到某個選項，顯示該選項文字而非內部值（opt2）
            label = next(
                (o.label for o in self.trigger_question.options.all()
                 if o.value == self.trigger_value),
                self.trigger_value,
            )
            cond = f"{self.get_trigger_operator_display()} {label}"
        return f"若「{self.trigger_question}」{cond} → {self.get_action_display()}「{target}」"

    def owning_version(self):
        return self.trigger_question.section.version


class EligibilityRule(VersionScopedModel):
    """適用規則 —— 控制「何時、對誰」呈現此問卷"""

    PERIOD_CHOICES = (
        ("any", "不限"),
        ("first_visit", "首次使用"),
        ("daily", "日常"),
        ("phase", "階段性"),
        ("tracking_period", "特定追蹤期間"),
    )

    version = models.ForeignKey(
        QuestionnaireVersion, verbose_name="問卷版本",
        related_name="eligibility_rules", on_delete=models.CASCADE,
    )
    min_age_months = models.PositiveIntegerField("最小月齡", null=True, blank=True)
    max_age_months = models.PositiveIntegerField("最大月齡", null=True, blank=True)
    tracking_status = models.CharField(
        "追蹤狀態", max_length=50, blank=True, help_text="留空表示不限；需與 Child.tracking_status 相符",
    )
    condition_json = models.JSONField(
        "其他條件", default=dict, blank=True,
        help_text="Builder 以表單設定適用起訖日與填答頻率。",
    )

    class Meta:
        verbose_name = "適用規則"
        verbose_name_plural = "適用規則"

    def __str__(self):
        parts = []
        if self.min_age_months is not None or self.max_age_months is not None:
            parts.append(f"{self.min_age_months or 0}～{self.max_age_months if self.max_age_months is not None else '不限'} 個月")
        if self.tracking_status:
            parts.append(f"追蹤狀態={self.tracking_status}")
        return "；".join(parts) or "不限"

    def owning_version(self):
        return self.version


# ---------------------------------------------------------------------------
# 填答紀錄
# ---------------------------------------------------------------------------

class QuestionnaireResponse(models.Model):
    """一次完整的填答紀錄

    注意「未記錄」不是這裡的狀態值 —— 正式文件（三）（七）要求區分
    已完成／未完成／未記錄三態，但「未記錄」的定義是「依適用規則應該填、
    卻連一筆紀錄都沒開始」，那是查詢時推導出來的，不是存在資料庫的欄位。
    推導邏輯見 questionnaires/logic.py。
    """

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "未完成"
        COMPLETED = "completed", "已完成"

    child = models.ForeignKey(
        "children.Child", verbose_name="兒童",
        related_name="questionnaire_responses", on_delete=models.CASCADE,
    )
    version = models.ForeignKey(
        QuestionnaireVersion, verbose_name="問卷版本",
        related_name="responses",
        # PROTECT 而非 CASCADE：問卷停用或改版時，既有填答紀錄與其版本
        # 關聯必須完好保留（正式文件（九）第 2 點）
        on_delete=models.PROTECT,
    )
    status = models.CharField("狀態", max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)
    source = models.CharField("資料來源", max_length=50, default="parent", help_text="家長／照顧者填報")
    started_at = models.DateTimeField("開始時間", auto_now_add=True)
    updated_at = models.DateTimeField("最後更新", auto_now=True)
    completed_at = models.DateTimeField("完成時間", null=True, blank=True)

    class Meta:
        verbose_name = "填答紀錄"
        verbose_name_plural = "填答紀錄"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["child", "status"]),
            models.Index(fields=["version", "status"]),
        ]
        constraints = [
            # 同一份問卷版本，同一個兒童最多只能有一筆未完成的紀錄，
            # 否則「暫存續填」會不知道該接哪一筆
            models.UniqueConstraint(
                fields=["child", "version"],
                condition=models.Q(status="in_progress"),
                name="one_in_progress_response_per_child_version",
            ),
        ]

    def __str__(self):
        return f"{self.child} / {self.version}（{self.get_status_display()}）"

    @transaction.atomic
    def mark_completed(self):
        from django.utils import timezone

        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])


class Answer(models.Model):
    """單題填答內容"""

    response = models.ForeignKey(
        QuestionnaireResponse, verbose_name="填答紀錄",
        related_name="answers", on_delete=models.CASCADE,
    )
    question = models.ForeignKey(
        Question, verbose_name="題目",
        # 同上：題目不可因問卷改版而消失，否則歷史填答會失去語意
        on_delete=models.PROTECT,
    )
    value = models.JSONField(
        "答案", help_text="依題型彈性存值：單選為字串、複選為陣列、數值為數字、日期為 ISO 字串",
    )
    answered_at = models.DateTimeField("作答時間", auto_now=True)

    class Meta:
        verbose_name = "填答內容"
        verbose_name_plural = "填答內容"
        ordering = ["response", "question__section__order", "question__order"]
        constraints = [
            models.UniqueConstraint(fields=["response", "question"], name="unique_answer_per_question"),
        ]

    def __str__(self):
        return f"{self.question}：{self.value}"
