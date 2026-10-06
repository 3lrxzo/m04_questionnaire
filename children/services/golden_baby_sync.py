from datetime import date

from django.db import transaction

from children.models import Child
from children.services.golden_baby_api import GoldenBabyAPI


class GoldenBabySyncError(Exception):
    """金寶貝會員資料同步失敗。"""
    pass


def parse_birth_date(value):
    """將 API birthday 轉成 Django DateField 可使用的 date。"""

    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise GoldenBabySyncError(
            f"無法解析出生日期：{value}"
        ) from exc


@transaction.atomic
def sync_children(dry_run=False):
    """
    從金寶貝 API 取得會員資料並同步至 Child。

    對應：
    name       -> Child.name
    birthday   -> Child.birth_date
    identifier -> Child.medical_no

    不同步：
    medical_status -> tracking_status
    guardian
    """

    api = GoldenBabyAPI()
    users = api.get_users()

    created_count = 0
    updated_count = 0
    skipped_count = 0

    for user in users:
        medical_no = str(user.get("identifier") or "").strip()
        name = str(user.get("name") or "").strip()
        birthday = user.get("birthday")

        # 沒有對接識別碼就不建立，避免產生無法識別的 Child
        if not medical_no:
            skipped_count += 1
            continue

        # Child.birth_date 為必填，因此 API 沒生日也先略過
        if not birthday:
            skipped_count += 1
            continue

        birth_date = parse_birth_date(birthday)

        child = Child.objects.filter(
            medical_no=medical_no
        ).first()

        if child is None:
            if not dry_run:
                Child.objects.create(
                    name=name,
                    birth_date=birth_date,
                    medical_no=medical_no,
                    tracking_status="",
                    is_active=True,
                )

            created_count += 1

        else:
            changed = False

            if child.name != name:
                child.name = name
                changed = True

            if child.birth_date != birth_date:
                child.birth_date = birth_date
                changed = True

            if changed:
                if not dry_run:
                    child.save(
                        update_fields=[
                            "name",
                            "birth_date",
                        ]
                    )

                updated_count += 1

    return {
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,
    }