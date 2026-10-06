# 金寶貝健康問卷模組（M04）

馬偕金寶貝智能化居家互動整合平台的健康問卷模組。

**這不是六份固定問卷，而是一套「問卷管理系統」** —— 兒科部人員可在後台自訂問卷
（題目、題組、題型、選項、條件分支、適用規則、版本發布），家長在手機上以
「一次一題」的低負擔方式填答，結果回存同一份兒童健康紀錄。

Tier 0～Tier 5 只是第一階段的最低驗收基準，系統架構不寫死在這六種情境上。

需求依據：

`docs/金寶貝_健康問卷模組M04_系統功能與功能架構設計_正式版.docx`（V1.0）

開發規劃：

`docs/M04_開發規劃書.md`

---

## 技術棧

| 層 | 技術 |
|---|---|
| 後端 / API | Django 5.2 LTS + Django REST Framework 3.18 + requests |
| 資料庫 | PostgreSQL 16（問卷 schema 與填答內容使用 JSONB） |
| 資料庫驅動 | psycopg 3 |
| 外部系統串接 | 金寶貝 API（支援 MOCK / 正式 API 模式切換） |
| 後台（工程 / 管理用） | Django Admin（客製化） |
| 問卷編輯器（醫護用） | Vue 3（CDN、Options API、無建構工具） |
| 家長端填答頁 | Vue 3（同上） |
| 其餘頁面 | Django Template + 原生 JS |

介面語系為正體中文，時區 `Asia/Taipei`。

---

## 環境建置

需求：

- PostgreSQL 16
- Python 3.13
- `virtualenvwrapper` 或標準 `venv`

```bash
# 1. 資料庫（macOS / Homebrew 範例）
brew install postgresql@16
brew services start postgresql@16
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
createdb m04_questionnaire

# 2. 虛擬環境與套件
mkvirtualenv m04_venv -p python3.13

# 或使用標準 venv
# python -m venv m04_venv
# source m04_venv/bin/activate

workon m04_venv
pip install -r requirements.txt

# 3. 環境變數
cp .env.example .env

python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"

# 把輸出填入 .env 的 DJANGO_SECRET_KEY

# 4. 資料庫結構與初始資料
python manage.py migrate

# 5. 建立後台管理帳號
python manage.py createsuperuser

# 6. （選用）建立「發燒條件式追問」示範問卷
python manage.py seed_demo_questionnaire --publish

# 7. 啟動
python manage.py runserver
```

Fedora / Windows 的差異見 `.env.example` 內的註解。

### 金寶貝 API 環境變數

`.env` 中需設定：

```env
# =========================
# 金寶貝 API
# =========================

GOLDEN_BABY_API_URL=https://icare.docter.pro/back-end/app

# true  = MOCK 模擬模式
# false = 正式 API 模式
GOLDEN_BABY_API_MOCK=true

# 正式 API 模式使用
GOLDEN_BABY_API_ACCOUNT=
GOLDEN_BABY_API_PASSWORD=
```

開發、測試及專題展示階段可設定：

```env
GOLDEN_BABY_API_MOCK=true
```

此時系統使用模擬兒童資料，不需要正式 API 帳號及密碼。

取得院方提供的正式 API 帳密後，改為：

```env
GOLDEN_BABY_API_MOCK=false
GOLDEN_BABY_API_ACCOUNT=正式帳號
GOLDEN_BABY_API_PASSWORD=正式密碼
```

即可切換至正式金寶貝 API，不需修改程式核心邏輯。

> **安全注意事項**：`.env` 不進版控，資料庫密碼、Django Secret Key、
> 金寶貝 API 帳號及密碼皆不得提交至 GitHub。
> `.env.example` 僅保留環境變數名稱及非機密範例設定。

> **本機開發注意**：專案的 session / CSRF cookie 已改名為
> `m04_sessionid` / `m04_csrftoken`，避免與其他本機 Django 專案在
> `127.0.0.1` 上互撞。

---

## 主要頁面

| 網址 | 對象 | 說明 |
|---|---|---|
| `/` | 全體 | 首頁，選擇「家長」或「醫護人員」入口 |
| `/admin/` | 工程 / 管理 | Django Admin，提供資料維護、兒童資料同步及填答紀錄查詢等功能 |
| `/build/` | 兒科部醫護 | 問卷管理列表（新增問卷、查看各版本狀態） |
| `/build/version/<id>/` | 兒科部醫護 | 三欄視覺化編輯器：大綱 / 題目卡 / 家長端即時預覽 |
| `/accounts/register/` | 家長 | 以姓名、身分證、電話、電子郵件與密碼註冊 |
| `/accounts/login/` | 家長 | 登入 |
| `/accounts/profile/` | 家長 | 編輯自己的姓名、身分證、電話、電子郵件與密碼 |
| `/parent/` | 家長 | 名下孩子清單、新增孩子 |
| `/parent/child/add/` | 家長 | 登錄孩子資料（姓名、選填身分證、出生日期、追蹤狀態） |
| `/parent/child/<id>/edit/` | 家長 | 編輯本人名下孩子的資料 |
| `/child/<id>/` | 家長 | 該童的待填清單（未完成／未記錄）與已完成歷史 |
| `/fill/<version_id>/?child=<id>` | 家長 | 一次一題填答頁；`?preview=1` 為預覽模式（不寫入） |

> 家長帳密流程（`accounts` app）目前供展示與測試。
> 院方 APP 介接後，家長身分改由 APP 帶入，
> `_children_for()` 保留 `guardian` 過濾機制。

---

## 資料模型

應用程式：

- `accounts`：家長帳號
- `children`：兒童資料
- `questionnaires`：問卷核心

```text
Questionnaire（問卷主檔：名稱／分類／Tier／建立時間與建立者）
└── QuestionnaireVersion（版本：草稿 → 已發布 → 已停用，發布後內容鎖定）
    │
    ├── Section（題組）
    │   └── Question（題目：單選／複選／數值／文字／量表／日期時間）
    │       └── Option（選項）
    │
    ├── BranchRule
    │   （分支條件：某題答案 → 顯示／隱藏題組、題目或觸發其他問卷）
    │
    └── EligibilityRule
        （適用規則：月齡區間、追蹤狀態、日期期間、頻率與建議填答時點）

Child（兒童，children app）
├── medical_no：外部兒童主檔識別接點
├── guardian：主要照顧者
├── tracking_status：M04 問卷適用規則使用的追蹤狀態
│
└── QuestionnaireResponse（一次填答，對 version 使用 PROTECT）
    └── Answer（單題答案，對 question 使用 PROTECT，value 為 JSON）

Category / Tier
（分類與分層皆為資料表，而非程式常數；
  後台可自行新增，不需修改程式重新部署）
```

---

## 關鍵設計

### 已發布版本不可覆寫

`VersionScopedModel` 在 model 層阻擋對非草稿版本內容的增刪改，而不只是在
Admin 設定唯讀。

修改一份已發布問卷的題目內容，會改變歷史填答資料原本代表的語意，因此系統不允許
直接修改已發布版本。

修改已發布問卷的方式為：

```python
QuestionnaireVersion.clone_as_new_draft()
```

先複製成新的草稿版本，再進行修改。

### 狀態轉換單向

問卷版本只能：

```text
draft → published → retired
```

不允許已發布版本退回草稿，避免繞過版本內容鎖定。

### 「未記錄」不是資料庫欄位

系統需區分：

```text
已完成
未完成
未記錄
```

前兩者由 `QuestionnaireResponse.status` 判斷。

「未記錄」代表：

> 依照適用規則應該填答，但目前連一筆 QuestionnaireResponse 都不存在。

因此由：

```python
logic.get_pending_questionnaires()
```

動態推導。

### 適用時期

Builder 與 Admin 支援：

- 不限
- 首次使用
- 日常
- 階段性
- 特定追蹤期間

`first_visit` 目前沒有獨立的就診／訪次資料，因此暫以：

> 該兒童尚無已完成的問卷填答

作為判定依據。

特定追蹤期間可設定起訖日期。

日常及階段性目前屬於規則分類，實際出現頻率仍由填答頻率設定控制。

### 分支邏輯前後端各計算一次

家長端填答頁由前端即時計算題目可見性，避免每回答一題就向 Server 發送一次判斷請求。

送出時，後端會再次使用：

```python
logic.compute_visibility()
```

重新驗證目前可見且必填的題目。

因此前後端分支邏輯需保持一致：

```text
questionnaires/logic.py
        ↕
static/js/questionnaire_fill.js
```

### 外部兒童資料同步

M04 可透過金寶貝 API 取得兒童基本資料，並同步至 `Child`。

系統使用 `medical_no` 作為外部兒童主檔與 M04 兒童資料之間的識別接點。

同步時：

- 找不到相同 `medical_no` → 建立新的 Child
- 已存在相同 `medical_no` → 比對並更新指定基本欄位
- 資料沒有變更 → 不重複寫入

同步程式目前主要處理：

```text
姓名
出生日期
病歷／外部識別碼
```

M04 自己管理的資料，例如：

```text
tracking_status
guardian
```

不由外部 API 自動覆蓋。

此外，金寶貝 API 的 `medical_status` 與 M04 的 `tracking_status`
定義不同，因此兩者不直接映射，以避免外部資料同步影響問卷適用規則。

---

## 金寶貝 API 串接

健康問卷模組可透過金寶貝 API 取得兒童基本資料，並同步至 M04 的 `Child`。

### 串接架構

```text
金寶貝 API
    ↓
登入取得 access token
    ↓
取得會員／兒童資料
    ↓
GoldenBabyAPI
    ↓
同步服務
    ↓
Dry Run 同步預覽
    ↓
管理者確認同步
    ↓
Child
    ↓
適用規則判斷
    ↓
家長端待填問卷
    ↓
問卷填答
    ↓
健康紀錄
```

API 通訊與資料同步邏輯分離：

```text
children/services/
├── golden_baby_api.py
└── golden_baby_sync.py
```

其中：

- `golden_baby_api.py`：負責金寶貝 API 登入及資料取得
- `golden_baby_sync.py`：負責 API 資料與 M04 `Child` 的比對、新增及更新

---

### API 資料對應

| 金寶貝 API | M04 Child | 處理方式 |
|---|---|---|
| `name` | `name` | 同步 |
| `birthday` | `birth_date` | 同步，供月齡及適用規則計算 |
| `identifier` | `medical_no` | 作為外部資料識別接點 |
| `medical_status` | `tracking_status` | 不直接同步，兩者定義不同 |
| `sex` | 無 | 目前不存入 M04 |
| `height` | 無 | 目前不存入 M04 |
| `weight` | 無 | 目前不存入 M04 |
| 無 | `guardian` | 由 M04 管理，不由 API 覆蓋 |

---

### MOCK / 正式 API 模式

系統支援兩種資料來源。

#### MOCK 模擬模式

```env
GOLDEN_BABY_API_MOCK=true
```

用途：

- 本機開發
- 功能測試
- 專題展示
- 正式 API 尚未取得帳密時使用

MOCK 模式不會連線正式金寶貝 API。

#### 正式 API 模式

```env
GOLDEN_BABY_API_MOCK=false
GOLDEN_BABY_API_ACCOUNT=正式帳號
GOLDEN_BABY_API_PASSWORD=正式密碼
```

正式模式會使用設定的 API 帳密登入金寶貝 API，取得 access token 後再存取兒童資料。

MOCK / 正式 API 的切換只需修改環境變數，不需要修改 Python 程式。

---

### Admin 兒童同步

Django Admin 的兒童管理頁提供：

```text
從金寶貝 API 同步
```

同步流程為：

```text
兒童資料列表
    ↓
從金寶貝 API 同步
    ↓
顯示目前資料來源
    ↓
執行 Dry Run
    ↓
顯示：
準備新增 X 筆
準備更新 X 筆
略過 X 筆
    ↓
管理者確認
    ↓
實際寫入 Child
```

系統不會在進入同步頁面時直接修改資料庫。

只有管理者按下：

```text
確認同步
```

後，才會真正執行資料新增或更新。

Admin 同步頁同時顯示目前資料來源：

```text
MOCK 模擬模式
```

或：

```text
正式 API 模式
```

方便開發、測試及展示時確認目前使用的資料來源。

---

## M04 內部 API

### 家長端 API

權限：登入即可；家長身分驗證機制待院方 APP 介接規格確定後收斂。

| Method | Endpoint | 用途 |
|---|---|---|
| GET | `/api/questionnaires/<version_id>/schema/` | 載入完整問卷 schema（`?preview=1` 可讀草稿） |
| POST | `/api/responses/` | 開始填答（已有未完成紀錄則接續） |
| GET | `/api/responses/<id>/` | 續填時取回已填內容 |
| PATCH | `/api/responses/<id>/autosave/` | 暫存單題／多題 |
| POST | `/api/responses/<id>/complete/` | 送出（只檢查當前可見且必填的題目） |

### 問卷編輯器 API

權限：`IsAdminUser`，需 staff 帳號。

前綴：

```text
/api/builder/
```

提供：

- 問卷建立
- 版本建立
- 發布
- 複製
- 停用
- 題組 CRUD
- 題目 CRUD
- 選項 CRUD
- 分支規則 CRUD
- 適用規則 CRUD
- 批次排序

批次排序：

```text
versions/<id>/reorder/
```

Builder 提供：

- 適用月齡
- 追蹤狀態
- 不限
- 首次使用
- 日常
- 階段性
- 特定追蹤期間
- 起訖日期
- 填答頻率
- 建議填答時點

分支規則可觸發下一份問卷或 Tier。

完成來源問卷後，符合觸發條件的問卷會加入兒童待填清單。

非草稿版本的寫入回：

```text
HTTP 409
```

Admin 的填答紀錄可依兒童、日期、Tier、問卷、版本與狀態篩選。

已發布版本若需修改，系統會提示先複製為草稿版本。

---

## 已驗證流程

目前已完成基本整合流程驗證：

```text
金寶貝 MOCK API
    ↓
取得兒童資料
    ↓
同步預覽
    ↓
建立 / 更新 Child
    ↓
設定主要照顧者
    ↓
依出生日期計算月齡
    ↓
依追蹤狀態及 EligibilityRule 判斷
    ↓
家長端顯示符合條件的問卷
    ↓
一次一題填答
    ↓
完成送出
    ↓
QuestionnaireResponse / Answer 回存
```

同步流程亦已驗證：

- 新兒童可建立
- 已存在兒童不會重複建立
- 基本資料差異可被偵測
- Dry Run 不修改資料庫
- 確認同步後才實際更新
- `tracking_status` 不會被外部 API 覆蓋
- API 同步兒童可正常套用 M04 適用規則
- API 同步兒童可正常完成問卷填答及回存

> 上述金寶貝 API 整合目前主要以 MOCK 模式完成開發及流程驗證。
> 正式 API 環境仍需取得院方提供的有效帳號及密碼後進行最終連線驗證。

---

## 開發

```bash
python manage.py test
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

macOS / Fedora / Windows 各自維護 Python 虛擬環境，透過 `requirements.txt`
對齊套件版本。

`migrations/` 納入版控。

切換機器後執行：

```bash
git pull
pip install -r requirements.txt
python manage.py migrate
```

---

## 尚未完成 / 待院方確認

- **金寶貝正式 API 環境驗證**：API Client、MOCK 模式、同步預覽及 Child
  同步流程已完成；待院方提供正式 API 帳號及密碼後進行正式連線與資料格式驗證。
- **家長端身分驗證與院方 APP 串接**：目前沿用 Django session，實際登入及身分
  帶入方式待院方 APP 介接規格確認。
- **兒科部正式問卷內容**：實際題目、選項、量表、適用時期及分支條件仍需由院方確認。
- **PWA Service Worker**：離線與「加入主畫面」功能列為 Phase 2。
- **編輯器拖曳排序**：目前使用上下箭頭調整順序。
- **多條件 AND / OR 分支**：目前維持單一觸發題＋單一值的條件模型。
