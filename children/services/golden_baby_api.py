import requests
from django.conf import settings


class GoldenBabyAPIError(Exception):
    """金寶貝 API 呼叫失敗。"""
    pass


class GoldenBabyAPI:
    #def __init__(self):
        #self.base_url = settings.GOLDEN_BABY_API_URL.rstrip("/")
        #self.account = settings.GOLDEN_BABY_API_ACCOUNT
        #self.password = settings.GOLDEN_BABY_API_PASSWORD
        #self.timeout = 10

    def __init__(self):
        self.base_url = settings.GOLDEN_BABY_API_URL.rstrip("/")
        self.account = settings.GOLDEN_BABY_API_ACCOUNT
        self.password = settings.GOLDEN_BABY_API_PASSWORD
        self.mock = settings.GOLDEN_BABY_API_MOCK
        self.timeout = 10


    def login(self):
        """登入金寶貝 API 並取得 access_token。"""

        if not self.account or not self.password:
            raise GoldenBabyAPIError(
                "尚未設定金寶貝 API 帳號或密碼"
            )

        try:
            response = requests.post(
                f"{self.base_url}/login/golden-baby",
                json={
                    "account": self.account,
                    "password": self.password,
                },
                timeout=self.timeout,
            )

            response.raise_for_status()
            result = response.json()

        except requests.RequestException as exc:
            raise GoldenBabyAPIError(
                f"無法連線至金寶貝 API：{exc}"
            ) from exc

        if not result.get("success"):
            raise GoldenBabyAPIError(
                f"登入失敗，API code={result.get('code')}"
            )

        token = result.get("data", {}).get("access_token")

        if not token:
            raise GoldenBabyAPIError(
                "登入成功，但 API 沒有回傳 access_token"
            )

        return token

    def get_users(self, **params):
        """查詢金寶貝會員名冊。"""
        if self.mock:
            return [
                {
                    "id": 10001,
                    "name": "API測試兒童A",
                    "identifier": "MOCK001",
                    "sex": 1,
                    "org_id": 1,
                    "org_name": "測試機構",
                    "area_id": 1,
                    "area_name": "測試單位",
                    "medical_status": 1,
                    "birthday": "2025-02-01",
                    "height": 80.5,
                    "weight": 11.2,
                },
                {
                    "id": 10002,
                    "name": "API測試兒童B",
                    "identifier": "MOCK002",
                    "sex": 0,
                    "org_id": 1,
                    "org_name": "測試機構",
                    "area_id": 1,
                    "area_name": "測試單位",
                    "medical_status": 1,
                    "birthday": "2024-06-15",
                    "height": 90.0,
                    "weight": 13.5,
                },
            ]

        token = self.login()

        try:
            response = requests.get(
                f"{self.base_url}/user",
                headers={
                    "Authorization": f"Bearer {token}",
                },
                params=params,
                timeout=self.timeout,
            )

            response.raise_for_status()
            result = response.json()

        except requests.RequestException as exc:
            raise GoldenBabyAPIError(
                f"無法取得會員資料：{exc}"
            ) from exc

        if not result.get("success"):
            raise GoldenBabyAPIError(
                f"取得會員資料失敗，API code={result.get('code')}"
            )

        return result.get("data")