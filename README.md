# 金寶貝健康問卷模組（M04）

馬偕金寶貝智能化居家互動整合平台的健康問卷模組。

**這不是六份固定問卷，而是一套「問卷管理系統」** —— 兒科部人員在後台自訂問卷
（題目、題組、題型、選項、條件分支、適用規則、版本發布），家長在手機上以
「一次一題」的低負擔方式填答，結果回存同一份兒童健康紀錄。Tier 0～Tier 5
只是第一階段的最低驗收基準，系統架構不寫死在這六種情境上。

需求依據：`docs/金寶貝_健康問卷模組M04_系統功能與功能架構設計_正式版.docx`（V1.0）
開發規劃：`docs/M04_開發規劃書.md`

---

## 技術棧

| 層 | 技術 |
|---|---|
| 後端 / API | Django 5.2 LTS + Django REST Framework 3.18 |
| 資料庫 | PostgreSQL 16（問卷 schema 與填答內容用 JSONB） |
| 資料庫驅動 | psycopg 3 |
| 後台（工程用） | Django Admin（客製化） |
| 問卷編輯器（醫護用） | Vue 3（CDN、Options API、無建構工具） |
| 家長端填答頁 | Vue 3（同上） |
| 其餘頁面 | Django Template + 原生 JS |

介面語系為正體中文，時區 `Asia/Taipei`。

---

## 環境建置

需求：PostgreSQL 16、Python 3.13、`virtualenvwrapper`（或標準 `venv`）。

```bash
# 1. 資料庫（macOS / Homebrew 範例）
brew install postgresql@16
brew services start postgresql@16
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"   # 建議寫進 ~/.zshrc
createdb m04_questionnaire

# 2. 虛擬環境與套件
mkvirtualenv m04_venv -p python3.13      # 或 python -m venv m04_venv && source ...
workon m04_venv
pip install -r requirements.txt

# 3. 環境變數
cp .env.example .env                     # 再依你這台機器的實際設定填值
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
# 把輸出填進 .env 的 DJANGO_SECRET_KEY

# 4. 資料庫結構與初始資料
python manage.py migrate                 # 建表 + 建立 Tier 0～5、基本分類

# 5. 後台管理帳號
python manage.py createsuperuser

# 6. （選用）建立「發燒條件式追問」示範問卷
python manage.py seed_demo_questionnaire --publish

# 7. 啟動
python manage.py runserver
```

Fedora / Windows 的差異見 `.env.example` 內的註解。

> **本機開發注意**：`.env` 不進版控（DB 帳密每台機器不同）。專案的 session /
> CSRF cookie 已改名為 `m04_sessionid` / `m04_csrftoken`，避免與其他本機
> Django 專案在 `127.0.0.1` 上互撞。

---

## 主要頁面

| 網址 | 對象 | 說明 |
|---|---|---|
| `/` | 全體 | 首頁，選擇「家長」或「醫護人員」入口 |
| `/admin/` | 工程 | Django Admin，完整的資料維護 |
| `/build/` | 兒科部醫護 | 問卷管理列表（新增問卷、看各版本狀態） |
| `/build/version/<id>/` | 兒科部醫護 | 三欄視覺化編輯器：大綱 / 題目卡 / 家長端即時預覽 |
| `/accounts/register/` | 家長 | 註冊帳號（成功後導向登錄第一個孩子） |
| `/accounts/login/` | 家長 | 登入 |
| `/parent/` | 家長 | 名下孩子清單、新增孩子 |
| `/parent/child/add/` | 家長 | 登錄孩子資料（姓名、出生日期、病歷號、追蹤狀態） |
| `/parent/child/<id>/edit/` | 家長 | 編輯本人名下孩子的資料 |
| `/child/<id>/` | 家長 | 該童的待填清單（未完成／未記錄）與已完成歷史 |
| `/fill/<version_id>/?child=<id>` | 家長 | 一次一題填答頁；`?preview=1` 為預覽模式（不寫入） |

> 家長帳密流程（`accounts` app）僅供展示與測試。院方 APP 介接後，家長身分
> 改由 APP 帶入，`_children_for()` 只留 `guardian` 過濾。

---

## 資料模型

應用程式：`accounts`（家長帳號）、`children`（兒童）、`questionnaires`（問卷核心）

```
Questionnaire（問卷主檔：名稱／分類／Tier）
└── QuestionnaireVersion（版本：草稿→已發布→已停用，發布後內容鎖定）
    ├── Section（題組）
    │   └── Question（題目：單選／複選／數值／文字／量表／日期時間）
    │       └── Option（選項）
    ├── BranchRule（分支條件：某題答案 → 顯示／隱藏 某題組／題目／問卷）
    └── EligibilityRule（適用規則：月齡區間、追蹤狀態、日期期間、頻率與建議填答時點）

Child（兒童，children app）
└── QuestionnaireResponse（一次填答，對 version 用 PROTECT）
    └── Answer（單題答案，對 question 用 PROTECT，value 為 JSON）

Category / Tier（分類與分層，皆為資料表而非程式常數——
                 後台可自行新增，不需改程式重新部署）
```

### 幾個關鍵設計

- **已發布版本不可覆寫**：`VersionScopedModel` 在 model 層擋下對非草稿版本
  內容的增刪改（不只在 Admin 設唯讀）。改一份已發布問卷的題目文字等同默默
  竄改歷史填答的語意，屬無聲資料毀損。修改的唯一途徑是
  `QuestionnaireVersion.clone_as_new_draft()`。
- **狀態轉換單向**：只能 `draft → published → retired`，沒有退回草稿的路，
  否則能繞過內容鎖。
- **「未記錄」不是欄位**：正式文件要求區分 已完成／未完成／未記錄。前兩者
  看 `QuestionnaireResponse.status`；「未記錄」是「依適用規則應該填、卻連
  一筆紀錄都沒有」，由 `logic.get_pending_questionnaires()` 推導。
- **適用時期**：Builder 與 Admin 支援不限、首次使用、日常、階段性及特定追蹤期間。
  `first_visit` 目前沒有獨立的就診／訪次資料，因此暫以「該兒童尚無已完成的問卷
  填答」判定；特定追蹤期間可設定起訖日期。日常及階段性目前是規則分類，實際
  出現頻率仍由填答頻率設定控制。
- **分支邏輯前後端各算一份**：家長端填答頁在前端即時算可見性（避免每答一題
  打一次 server），送出時後端 `logic.compute_visibility()` 再驗一次必填。
  兩邊邏輯需保持對齊（`questionnaires/logic.py` ↔ `static/js/questionnaire_fill.js`）。

---

## API

家長端（權限：登入即可；家長身分驗證機制待院方 APP 介接規格確定後收斂）：

| Method | Endpoint | 用途 |
|---|---|---|
| GET | `/api/questionnaires/<version_id>/schema/` | 載入完整問卷 schema（`?preview=1` 可讀草稿） |
| POST | `/api/responses/` | 開始填答（已有未完成紀錄則接續） |
| GET | `/api/responses/<id>/` | 續填時取回已填內容 |
| PATCH | `/api/responses/<id>/autosave/` | 暫存單題／多題 |
| POST | `/api/responses/<id>/complete/` | 送出（只檢查當前可見且必填的題目） |

問卷編輯器（權限：`IsAdminUser`，需 staff 帳號），前綴 `/api/builder/`：
問卷與版本的建立／發布／複製／停用，題組／題目／選項／分支規則／適用規則的
CRUD，以及批次排序 `versions/<id>/reorder/`。Builder 提供適用月齡、追蹤狀態、
不限／首次使用／日常／階段性／特定追蹤期間、起訖日期、填答頻率與建議填答時點設定；
分支規則可觸發下一份問卷或 Tier。
完成來源問卷後，符合觸發條件的問卷會加入兒童待填清單。非草稿版本的寫入回 409。
Admin 的填答紀錄可依兒童、日期、Tier、問卷、版本與狀態篩選；已發布版本會提示
先複製為草稿再修改規則。

---

## 開發

```bash
python manage.py test          # 全套測試
python manage.py check
```

測試檔：
- `questionnaires/tests.py` — 版本不可覆寫、狀態轉換、分支目標約束、Admin 煙霧測試
- `questionnaires/tests_logic.py` — 分支判斷、適用規則、待填問卷推導
- `questionnaires/tests_api.py` — 家長端五個端點的端對端
- `questionnaires/tests_views.py` — 家長端入口頁
- `questionnaires/tests_builder.py` — 問卷編輯器 API
- `accounts/tests.py` — 家長註冊、登入登出、孩子登錄

### 跨機器開發

三台機器（macOS / Fedora / Windows）各自維護 venv，靠 `requirements.txt`
對齊套件；`migrations/` 進版控，切換機器後 `git pull && pip install -r
requirements.txt && python manage.py migrate`。

---

## 尚未完成 / 待院方確認

- 家長端身分驗證如何串接院方 APP（目前沿用 Django session）
- 兒科部實際的問卷內容、選項、量表、適用時期與分支條件
- PWA service worker（離線「加入主畫面」），列為 Phase 2
- 編輯器的拖曳排序（目前為上下箭頭）
- 多條件 AND/OR 組合的分支（目前刻意維持單一觸發題＋單一值）
