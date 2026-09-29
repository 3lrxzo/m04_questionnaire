"""問卷的執行期邏輯：分支判斷、適用規則比對、待填問卷推導。

刻意都寫成純函式、吃 model 實例、不碰 request —— 這樣後台預覽、家長端 API、
未來的排程提醒都能共用同一套判斷，不會出現「前端算一套、後端算另一套」。

《開發規劃書》第二節明訂：分支邏輯先用 Python function，不一開始上通用
rule engine。若日後分支需要多條件 AND/OR 組合，再評估是否獨立成 rule
engine，此處保持最小可用。
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from django.utils import timezone


# ---------------------------------------------------------------------------
# 單條分支條件的判斷
# ---------------------------------------------------------------------------

def _as_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_condition(operator, trigger_value, answer_value) -> bool:
    """判斷一個作答值是否滿足分支條件。

    answer_value 是家長對「觸發題目」的作答，型別依題型而定：
    單選為字串、複選為 list、數值為數字或數字字串。
    """
    from .models import BranchRule

    if operator == BranchRule.Operator.ANSWERED:
        if answer_value is None:
            return False
        if isinstance(answer_value, (list, tuple, str)):
            return len(answer_value) > 0
        return True

    if answer_value is None:
        return False

    # 複選題：任一選項命中即算命中
    if isinstance(answer_value, (list, tuple)):
        return any(
            evaluate_condition(operator, trigger_value, item) for item in answer_value
        )

    if operator == BranchRule.Operator.EQ:
        return str(answer_value) == str(trigger_value)
    if operator == BranchRule.Operator.NEQ:
        return str(answer_value) != str(trigger_value)
    if operator == BranchRule.Operator.IN:
        allowed = [v.strip() for v in str(trigger_value).split(",")]
        return str(answer_value) in allowed

    # 數值比較
    left, right = _as_number(answer_value), _as_number(trigger_value)
    if left is None or right is None:
        return False
    if operator == BranchRule.Operator.GT:
        return left > right
    if operator == BranchRule.Operator.GTE:
        return left >= right
    if operator == BranchRule.Operator.LT:
        return left < right
    if operator == BranchRule.Operator.LTE:
        return left <= right

    return False


# ---------------------------------------------------------------------------
# 一份填答的可見性計算
# ---------------------------------------------------------------------------

def compute_visibility(version, answers: dict) -> dict:
    """依目前的作答，算出這份問卷版本裡每個題組／題目該不該顯示。

    參數
        version : QuestionnaireVersion
        answers : {question_id: answer_value}

    回傳
        {
            "visible_section_ids": set(...),
            "visible_question_ids": set(...),
            "triggered_questionnaire_ids": set(...),   # 跨問卷／跨 Tier 承接
        }

    規則
    - 題組／題目預設可見；被 hide 規則命中則隱藏。
    - 但「被某條 show 規則指定為目標」的題組／題目，預設改為隱藏，
      只有對應觸發條件成立時才顯示（這對應正式文件圖 2：發燒追問題組
      平時不出現，答「有」才出現）。
    - 停用（is_active=False）的題組／題目一律不顯示。
    """
    from .models import BranchRule

    sections = list(version.sections.filter(is_active=True).prefetch_related("questions"))
    section_ids = {s.id for s in sections}
    question_ids = {
        q.id
        for s in sections
        for q in s.questions.all()
        if q.is_active
    }

    rules = list(
        BranchRule.objects
        .filter(trigger_question__section__version=version)
        .select_related("target_section", "target_question", "target_questionnaire")
    )

    # 被 show 規則指定為目標者，預設隱藏（等觸發）
    show_target_sections = {
        r.target_section_id for r in rules
        if r.action == BranchRule.Action.SHOW and r.target_section_id
    }
    show_target_questions = {
        r.target_question_id for r in rules
        if r.action == BranchRule.Action.SHOW and r.target_question_id
    }

    visible_sections = section_ids - show_target_sections
    visible_questions = question_ids - show_target_questions
    triggered_questionnaires: set[int] = set()
    hidden_questionnaires: set[int] = set()

    for rule in rules:
        answer_value = answers.get(rule.trigger_question_id)
        hit = evaluate_condition(rule.trigger_operator, rule.trigger_value, answer_value)
        if not hit:
            continue

        if rule.action == BranchRule.Action.SHOW:
            if rule.target_section_id:
                visible_sections.add(rule.target_section_id)
            if rule.target_question_id:
                visible_questions.add(rule.target_question_id)
            if rule.target_questionnaire_id:
                triggered_questionnaires.add(rule.target_questionnaire_id)
        else:  # HIDE
            visible_sections.discard(rule.target_section_id)
            visible_questions.discard(rule.target_question_id)
            if rule.target_questionnaire_id:
                hidden_questionnaires.add(rule.target_questionnaire_id)

    # 收尾：題組被隱藏時，其下題目一併隱藏
    for section in sections:
        if section.id not in visible_sections:
            for question in section.questions.all():
                visible_questions.discard(question.id)

    return {
        "visible_section_ids": visible_sections,
        "visible_question_ids": visible_questions,
        "triggered_questionnaire_ids": triggered_questionnaires,
        "hidden_questionnaire_ids": hidden_questionnaires,
    }


# ---------------------------------------------------------------------------
# 適用規則
# ---------------------------------------------------------------------------

def _matching_eligibility_rules(child, version, as_of):
    rules = list(version.eligibility_rules.all())
    if not rules:
        return None
    as_of = as_of or timezone.localdate()
    age_months = child.age_months(as_of)
    from .models import QuestionnaireResponse
    has_completed_response = None
    matched = []
    for rule in rules:
        if rule.min_age_months is not None and age_months < rule.min_age_months:
            continue
        if rule.max_age_months is not None and age_months > rule.max_age_months:
            continue
        if rule.tracking_status and rule.tracking_status != child.tracking_status:
            continue
        conditions = rule.condition_json or {}
        if conditions.get("period", "any") == "first_visit":
            if has_completed_response is None:
                has_completed_response = QuestionnaireResponse.objects.filter(
                    child=child,
                    status=QuestionnaireResponse.Status.COMPLETED,
                ).exists()
            if has_completed_response:
                continue
        start = _condition_date(conditions.get("start_date"))
        end = _condition_date(conditions.get("end_date"))
        if start and as_of < start:
            continue
        if end and as_of > end:
            continue
        matched.append(rule)
    return matched


def child_matches_version(child, version, as_of: date | None = None) -> bool:
    """兒童此刻是否符合某問卷版本的適用規則。

    一個版本可掛多條 EligibilityRule，任一條成立即視為適用（OR）。
    完全沒有規則時，視為「對所有人適用」。
    """
    rules = _matching_eligibility_rules(child, version, as_of or timezone.localdate())
    return rules is None or bool(rules)


def _condition_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _frequency_allows(version, child, as_of, rules=None):
    """Whether a questionnaire is due under its configured completion cadence."""
    from .models import QuestionnaireResponse

    rules = list(rules if rules is not None else version.eligibility_rules.all())
    if not rules or all((rule.condition_json or {}).get("frequency", "any") == "any" for rule in rules):
        return True

    completed_at = QuestionnaireResponse.objects.filter(
        child=child,
        version__questionnaire_id=version.questionnaire_id,
        status=QuestionnaireResponse.Status.COMPLETED,
        completed_at__isnull=False,
    ).values_list("completed_at", flat=True)
    completed_dates = [timezone.localtime(value).date() for value in completed_at]
    if not completed_dates:
        return True
    last_completed = max(completed_dates)

    # Eligibility rules are alternatives: any matching frequency can make it due.
    for rule in rules:
        frequency = (rule.condition_json or {}).get("frequency", "any")
        if frequency == "any":
            return True
        if frequency == "daily" and last_completed < as_of:
            return True
        if frequency == "weekly" and last_completed <= as_of - timedelta(days=7):
            return True
        if frequency == "monthly":
            year, month = last_completed.year, last_completed.month + 1
            if month > 12:
                year, month = year + 1, 1
            due_day = min(last_completed.day, calendar.monthrange(year, month)[1])
            if as_of >= date(year, month, due_day):
                return True
    return False


# ---------------------------------------------------------------------------
# 待填問卷推導 —— 「未記錄」狀態的來源
# ---------------------------------------------------------------------------

def get_pending_questionnaires(child, as_of: date | None = None) -> list:
    """回傳這名兒童此刻「應填但尚未完成」的問卷版本清單。

    正式文件（三）（七）要求 APP 區分三態：已完成／未完成／未記錄。
    「未記錄」不是資料庫欄位，而是這裡推導出來的：

        對每一份「有已發布版本」且「兒童符合適用規則」的問卷 ——
          已有 completed 紀錄        → 已完成，不列入
          已有 in_progress 紀錄      → 未完成，列入（家長可續填）
          完全沒有任何紀錄            → 未記錄，列入（家長尚未開始）

    這個函式同時服務三個地方：
      1. 家長端單一入口該顯示哪份問卷（正式文件（五）「由系統決定當次
         應呈現之問卷」）
      2. 家長端首頁的「未記錄」提醒
      3. 後台的未完成／未記錄清單查詢

    回傳 list[dict]，每筆：
        {"version": QuestionnaireVersion, "state": "in_progress"|"unrecorded",
         "response_id": int|None}

    condition_json 的排程期間與頻率亦在此處套用；完成跨問卷分支後才會
    將被指定的問卷加入待填清單。
    """
    from .models import Questionnaire, QuestionnaireResponse, QuestionnaireVersion

    as_of = as_of or timezone.localdate()
    pending = []

    published_versions = (
        QuestionnaireVersion.objects
        .filter(
            status=QuestionnaireVersion.Status.PUBLISHED,
            questionnaire__is_active=True,
        )
        .select_related("questionnaire")
        .prefetch_related("eligibility_rules")
    )

    # 同一份問卷可能有多個歷史發布版；家長只需面對「當下生效」的那一版
    latest_by_questionnaire: dict[int, QuestionnaireVersion] = {}
    for version in published_versions:
        current = latest_by_questionnaire.get(version.questionnaire_id)
        if current is None or version.version_number > current.version_number:
            latest_by_questionnaire[version.questionnaire_id] = version

    responses = (
        QuestionnaireResponse.objects
        .filter(child=child, version__questionnaire_id__in=latest_by_questionnaire.keys())
        .values("version_id", "version__questionnaire_id", "status", "id")
    )
    # {questionnaire_id: {"completed": bool, "in_progress_id": int|None}}
    by_questionnaire: dict[int, dict] = {}
    for row in responses:
        entry = by_questionnaire.setdefault(
            row["version__questionnaire_id"], {"completed": False, "in_progress_id": None}
        )
        if row["status"] == QuestionnaireResponse.Status.COMPLETED:
            entry["completed"] = True
        elif row["status"] == QuestionnaireResponse.Status.IN_PROGRESS:
            entry["in_progress_id"] = row["id"]

    # Branch-target questionnaires are gated until a completed source response
    # actually satisfies the cross-questionnaire rule.
    from .models import BranchRule
    gated_targets = set(
        BranchRule.objects.filter(
            target_questionnaire_id__in=latest_by_questionnaire,
            action=BranchRule.Action.SHOW,
            trigger_question__section__version__status__in=(
                QuestionnaireVersion.Status.PUBLISHED, QuestionnaireVersion.Status.RETIRED,
            ),
        )
        .values_list("target_questionnaire_id", flat=True)
    )
    triggered_targets: set[int] = set()
    hidden_targets: set[int] = set()
    completed_responses = (
        QuestionnaireResponse.objects
        .filter(child=child, status=QuestionnaireResponse.Status.COMPLETED)
        .select_related("version__questionnaire")
        .prefetch_related("answers")
        .order_by("-completed_at", "-started_at", "-pk")
    )
    evaluated_sources: set[int] = set()
    for response in completed_responses:
        source_questionnaire_id = response.version.questionnaire_id
        if source_questionnaire_id in evaluated_sources:
            continue
        evaluated_sources.add(source_questionnaire_id)
        answers = {answer.question_id: answer.value for answer in response.answers.all()}
        visibility = compute_visibility(response.version, answers)
        triggered_targets.update(visibility["triggered_questionnaire_ids"])
        hidden_targets.update(visibility["hidden_questionnaire_ids"])

    for questionnaire_id, version in latest_by_questionnaire.items():
        eligibility_rules = _matching_eligibility_rules(child, version, as_of)
        if eligibility_rules is not None and not eligibility_rules:
            continue
        if questionnaire_id in gated_targets and questionnaire_id not in triggered_targets:
            continue
        if questionnaire_id in hidden_targets:
            continue
        entry = by_questionnaire.get(questionnaire_id, {})
        frequency_rules = eligibility_rules or []
        if not entry.get("in_progress_id") and not _frequency_allows(
            version, child, as_of, rules=frequency_rules,
        ):
            continue
        if entry.get("completed"):
            recurring = any(
                (rule.condition_json or {}).get("frequency", "any") in {"daily", "weekly", "monthly"}
                for rule in frequency_rules
            )
            if not recurring:
                continue
        if entry.get("in_progress_id"):
            pending.append({
                "version": version,
                "state": "in_progress",
                "response_id": entry["in_progress_id"],
            })
        else:
            pending.append({
                "version": version,
                "state": "unrecorded",
                "response_id": None,
            })

    return pending
