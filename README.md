# 金寶貝健康問卷模組（M04）

馬偕金寶貝智能化居家互動整合平台之健康問卷模組。

本模組**不是六份固定問卷**，而是一套可由兒科部人員自行建立、設計、發布及維護的 **健康問卷管理系統**。

兒科部人員可透過後台設定：

- 問卷名稱與分類
- Tier／分層
- 題組
- 題目
- 題型
- 回答選項
- 必填／選填
- 條件式分支
- 跨問卷／跨 Tier 觸發
- 適用規則
- 填答頻率
- 適用期間
- 問卷版本
- 發布與停用狀態

家長端則採用「**一次一題**」的低負擔填答方式，由系統依兒童資料、追蹤狀態、適用規則與既有填答紀錄，自動判斷當次應呈現的問卷。

完成後的填答結果統一回存至兒童健康紀錄，並保留：

- 問卷
- 問卷版本
- 開始時間
- 完成時間
- 完成狀態
- 題目答案
- 資料來源

> Tier 0～Tier 5 為第一階段最低驗收與功能驗證基準，並非系統功能上限。  
> 後續可新增其他問卷類型、分類或 Tier，而不需重新修改 APP 核心程式。

---

## 需求依據

正式需求文件：

```text
docs/金寶貝_健康問卷模組M04_系統功能與功能架構設計_正式版.docx
```

文件版本：

```text
V1.0
```

開發規劃：

```text
docs/M04_開發規劃書.md
```

---

# 技術棧

| 層 | 技術 |
|---|---|
| 後端 / API | Django 5.2 LTS + Django REST Framework 3.18 + requests |
| 資料庫 | PostgreSQL 16 |
| 問卷 Schema / 填答內容 | PostgreSQL JSONB |
| 資料庫驅動 | psycopg 3 |
| 外部系統串接 | 金寶貝 API（支援 MOCK / 正式 API 模式切換） |
| 工程 / 管理後台 | Django Admin（客製化） |
| 問卷編輯器 | Vue 3（CDN、Options API、無建構工具） |
| 家長端填答頁 | Vue 3（同上） |
| 其餘頁面 | Django Template + 原生 JavaScript |


---

# 環境需求

- PostgreSQL 16
- Python 3.13
- `virtualenvwrapper` 或標準 `venv`

---

# 環境建置

## 1. 安裝 PostgreSQL

macOS / Homebrew 範例：

```bash
brew install postgresql@16
brew services start postgresql@16

export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"

createdb m04_questionnaire
```

建議將 PostgreSQL PATH 設定寫入：

```bash
~/.zshrc
```

---

## 2. 建立 Python 虛擬環境

使用 `virtualenvwrapper`：

```bash
mkvirtualenv m04_venv -p python3.13
workon m04_venv
```

或使用標準 `venv`：

```bash
python -m venv m04_venv
source m04_venv/bin/activate
```

Windows PowerShell：

```powershell
.\m04_venv\Scripts\Activate.ps1
```

安裝套件：

```bash
pip install -r requirements.txt
```

---

## 3. 建立環境變數

複製：

```bash
cp .env.example .env
```

產生 Django Secret Key：

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

將輸出內容填入：

```env
DJANGO_SECRET_KEY=
```

---

## 4. 建立資料庫結構

```bash
python manage.py migrate
```

---

## 5. 建立 Django 管理員帳號

```bash
python manage.py createsuperuser
```

---

## 6. 建立示範問卷（選用）

建立「發燒條件式追問」示範問卷：

```bash
python manage.py seed_demo_questionnaire --publish
```

若示範問卷已存在，系統會略過建立。

---

## 7. 啟動 Django

```bash
python manage.py runserver
```

啟動後：

```text
http://127.0.0.1:8000/
```

---

## Fedora / Windows

Fedora / Windows 環境差異與設定方式請參考：

```text
.env.example
```

---

# 金寶貝 API 環境變數

`.env` 中設定：

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

---

## MOCK 模式

開發、測試及專題展示階段：

```env
GOLDEN_BABY_API_MOCK=true
```

此模式：

- 不連線正式金寶貝 API
- 不需要正式 API 帳號
- 不需要正式 API 密碼
- 使用模擬兒童資料
- 可測試兒童同步流程
- 可測試適用規則
- 可測試問卷填答

---

## 正式 API 模式

取得院方提供的正式 API 帳密後：

```env
GOLDEN_BABY_API_MOCK=false
GOLDEN_BABY_API_ACCOUNT=正式帳號
GOLDEN_BABY_API_PASSWORD=正式密碼
```

即可切換為正式 API。

MOCK / 正式 API 切換不需修改 Python 核心程式。

---

# 安全注意事項

`.env` 不得加入 Git 版控。

以下資訊禁止提交至 GitHub：

- PostgreSQL 帳號
- PostgreSQL 密碼
- Django Secret Key
- 金寶貝 API 帳號
- 金寶貝 API 密碼
- Access Token

`.env.example` 僅保留：

- 環境變數名稱
- 非機密範例
- 設定說明

---

# 本機開發注意事項

專案 Session / CSRF Cookie 已改名：

```text
m04_sessionid
m04_csrftoken
```

避免與其他本機 Django 專案在：

```text
127.0.0.1
```

發生 Cookie 衝突。

---

# 主要頁面

| 網址 | 對象 | 說明 |
|---|---|---|
| `/` | 全體 | 首頁，選擇家長或醫護人員入口 |
| `/admin/` | 工程 / 管理 | Django Admin |
| `/build/` | 兒科部醫護 | 問卷管理列表 |
| `/build/version/<id>/` | 兒科部醫護 | 問卷視覺化編輯器 |
| `/accounts/register/` | 家長 | 家長帳號註冊 |
| `/accounts/login/` | 家長 | 家長登入 |
| `/accounts/profile/` | 家長 | 編輯個人資料 |
| `/parent/` | 家長 | 名下孩子列表 |
| `/parent/child/add/` | 家長 | 新增孩子 |
| `/parent/child/<id>/edit/` | 家長 | 編輯本人名下孩子資料 |
| `/child/<id>/` | 家長 | 待填問卷與歷史紀錄 |
| `/fill/<version_id>/?child=<id>` | 家長 | 一次一題填答 |
| `/fill/<version_id>/?child=<id>&preview=1` | 醫護 | 預覽模式，不寫入正式填答 |

---

# 家長帳號

目前 `accounts` app 的家長帳號流程主要供：

- 開發
- 測試
- 專題展示

院方 APP 正式介接後，家長身分預計由院方 APP 帶入。

兒童資料取得仍透過：

```python
_children_for()
```

保留：

```text
guardian
```

權限過濾機制，避免家長讀取非本人管理的兒童資料。

---

# 系統資料模型

主要 Django Apps：

```text
accounts
children
questionnaires
```

---

## 問卷核心

```text
Questionnaire
│
├── 名稱
├── 分類
├── Tier
├── 建立時間
└── 建立者
    │
    └── QuestionnaireVersion
        │
        ├── draft
        ├── published
        └── retired
            │
            ├── Section
            │   │
            │   └── Question
            │       │
            │       └── Option
            │
            ├── BranchRule
            │
            └── EligibilityRule
```

---

## Questionnaire

問卷主檔：

```text
Questionnaire
```

主要資料：

- 名稱
- 說明
- 分類
- Tier
- 建立者
- 建立時間

---

## QuestionnaireVersion

問卷版本：

```text
QuestionnaireVersion
```

狀態：

```text
draft
    ↓
published
    ↓
retired
```

已發布版本不可直接修改。

---

## Section

題組：

```text
Section
```

用途：

- 將相關題目分類
- 支援條件式題組顯示
- 支援題目排序
- 支援健康主題分組

---

## Question

題目：

```text
Question
```

支援題型：

- 單選
- 複選
- 數值
- 簡短文字
- 量表
- 日期時間

---

## Option

選項：

```text
Option
```

適用於：

- 單選
- 複選
- 量表等題型

---

## BranchRule

分支條件：

```text
BranchRule
```

可依某題回答結果：

- 顯示題目
- 隱藏題目
- 顯示題組
- 隱藏題組
- 觸發指定問卷
- 觸發下一 Tier 問卷

跨問卷觸發會在來源問卷完成後進行判斷。

---

## EligibilityRule

適用規則：

```text
EligibilityRule
```

目前支援：

- 最小月齡
- 最大月齡
- 追蹤狀態
- 填答頻率
- 適用期間起日
- 適用期間迄日

Builder 可直接設定，不需由醫護人員手動輸入 JSON。

---

# Child

兒童資料：

```text
Child
```

主要欄位：

```text
name
birth_date
medical_no
guardian
tracking_status
```

其中：

### medical_no

作為：

```text
金寶貝外部兒童資料
        ↕
M04 Child
```

之間的識別接點。

### guardian

主要照顧者。

### tracking_status

M04 問卷適用規則使用的追蹤狀態。

---

# QuestionnaireResponse

一次問卷填答：

```text
QuestionnaireResponse
```

對：

```text
QuestionnaireVersion
```

使用：

```text
PROTECT
```

避免歷史填答所使用的版本被刪除。

---

# Answer

單題答案：

```text
Answer
```

對：

```text
Question
```

使用：

```text
PROTECT
```

答案內容：

```text
value = JSON
```

---

# Category / Tier

`Category` 與 `Tier` 皆為資料表。

並非程式常數。

因此管理後台可新增：

- 問卷分類
- Tier
- 分層

不需要修改 Python 程式或重新部署 APP。

---

# 關鍵設計

## 已發布版本不可覆寫

系統透過：

```python
VersionScopedModel
```

在 Model 層保護已發布版本。

非草稿版本的：

- 題目
- 題組
- 選項
- 分支規則
- 適用規則

原則上不得直接新增、修改或刪除。

此限制不只存在於 Admin UI，而是在 Model 層執行。

原因是：

> 如果直接修改已發布問卷的題目或選項，歷史填答原本所代表的語意可能被改變。

因此修改已發布問卷時必須：

```python
QuestionnaireVersion.clone_as_new_draft()
```

建立新的草稿版本後再進行修改。

---

# 問卷版本狀態

版本狀態只能：

```text
draft
    ↓
published
    ↓
retired
```

不允許：

```text
published → draft
```

避免透過退回草稿繞過版本內容鎖定。

---

# 問卷停用與刪除原則

正式問卷版本原則上不應直接刪除。

若問卷已不再使用，應：

```text
retired / 停用
```

而不是刪除。

如果問卷版本仍存在：

- 題組
- 題目
- 選項
- 分支條件
- 適用規則
- QuestionnaireResponse
- Answer

Django / Model 關聯保護可能阻止刪除。

即使為：

```text
superuser
```

也不能繞過：

```text
PROTECT
```

等資料完整性限制。

刪除功能主要適用於：

- 開發測試資料
- 無歷史填答
- 無必要保留價值的資料

正式資料應優先使用：

```text
停用
```

保留歷史可追溯性。

---

# 「未記錄」不是資料庫欄位

系統需要區分：

```text
已完成
未完成
未記錄
```

---

## 已完成

由：

```text
QuestionnaireResponse.status
```

判斷。

---

## 未完成

已建立：

```text
QuestionnaireResponse
```

但尚未完成送出。

---

## 未記錄

「未記錄」不直接存入資料庫。

其定義為：

> 依適用規則判斷目前應該填答，但目前不存在對應的 QuestionnaireResponse。

由：

```python
logic.get_pending_questionnaires()
```

動態計算。

---

# 適用規則

Builder 與 Admin 目前支援：

- 月齡
- 追蹤狀態
- 填答頻率
- 適用起日
- 適用迄日


---

## 不限

不限制適用時期。

---


# 填答頻率

Builder 可設定問卷填答頻率。

例如：

```text
不限
每日
```

以及系統目前提供的其他頻率選項。

填答頻率會與：

- EligibilityRule
- 既有完成紀錄

共同決定問卷是否再次出現在待填清單。

---

# 多條適用規則

Builder 可新增多條：

```text
適用 / 排程規則
```

系統依規則判斷兒童是否符合問卷適用條件。

---

# 分支邏輯

家長端與後端都會計算分支可見性。

---

## 前端

家長填答頁：

```text
static/js/questionnaire_fill.js
```

負責：

- 即時顯示 / 隱藏題目
- 即時顯示 / 隱藏題組
- 更新填答進度

避免每回答一題都需要重新請求 Server。

---

## 後端

送出時：

```python
logic.compute_visibility()
```

會重新計算：

- 可見題目
- 必填題目
- 分支結果

避免只靠前端驗證。

因此：

```text
questionnaires/logic.py
        ↕
static/js/questionnaire_fill.js
```

兩邊邏輯必須保持一致。

---

# 跨問卷 / 跨 Tier 觸發

BranchRule 可設定：

```text
來源題目
    ↓
符合指定答案
    ↓
來源問卷完成
    ↓
觸發指定問卷
或
觸發下一 Tier
```

例如：

```text
Tier 1 日常健康檢核
        ↓
孩子今天有沒有不舒服？
        ↓
       有
        ↓
Tier 2 定向健康篩檢
```

符合觸發條件後，目標問卷會加入兒童待填清單。

正式填答對象以：

```text
已發布版本
```

為主。

---

# 外部兒童資料同步

M04 可透過金寶貝 API 取得兒童基本資料，並同步至：

```text
Child
```

同步識別接點：

```text
medical_no
```

---

# 同步邏輯

```text
找不到相同 medical_no
        ↓
建立新的 Child
```

```text
已存在相同 medical_no
        ↓
比對指定欄位
        ↓
資料有變更
        ↓
更新 Child
```

```text
資料完全相同
        ↓
略過
```

避免建立重複兒童。

---

# 外部 API 同步欄位

目前主要同步：

- 姓名
- 出生日期
- 病歷 / 外部識別碼

M04 自己管理的欄位：

- `tracking_status`
- `guardian`

不由外部 API 自動覆蓋。

---

# medical_status 與 tracking_status

金寶貝 API：

```text
medical_status
```

與 M04：

```text
tracking_status
```

定義不同。

因此目前：

```text
medical_status
        ✕
tracking_status
```

不直接映射。

目的為避免外部同步直接改變：

```text
問卷 EligibilityRule 判斷結果
```

---

# 金寶貝 API 串接架構

```text
金寶貝 API
    ↓
登入取得 access token
    ↓
取得會員 / 兒童資料
    ↓
GoldenBabyAPI
    ↓
同步服務
    ↓
Dry Run 同步預覽
    ↓
管理者確認
    ↓
Child
    ↓
EligibilityRule
    ↓
家長端待填問卷
    ↓
問卷填答
    ↓
QuestionnaireResponse / Answer
```

---

# API 與同步服務分離

程式位置：

```text
children/services/
├── golden_baby_api.py
└── golden_baby_sync.py
```

---

## golden_baby_api.py

負責：

- API 登入
- Access Token
- API Request
- 會員資料取得
- 兒童資料取得

---

## golden_baby_sync.py

負責：

- API 資料比對
- Child 新增
- Child 更新
- Dry Run
- 重複資料判斷
- 欄位同步規則

---

# API 資料對應

| 金寶貝 API | M04 Child | 處理方式 |
|---|---|---|
| `name` | `name` | 同步 |
| `birthday` | `birth_date` | 同步 |
| `identifier` | `medical_no` | 外部資料識別接點 |
| `medical_status` | `tracking_status` | 不直接同步 |
| `sex` | 無 | 目前不存入 M04 |
| `height` | 無 | 目前不存入 M04 |
| `weight` | 無 | 目前不存入 M04 |
| 無 | `guardian` | M04 自行管理 |

---

# MOCK / 正式 API 模式

系統支援：

```text
MOCK
正式 API
```

兩種資料來源。

---

## MOCK 模式

設定：

```env
GOLDEN_BABY_API_MOCK=true
```

用途：

- 本機開發
- 自動測試
- 人工功能測試
- 專題展示
- 正式 API 尚未取得帳號時使用

MOCK 模式：

```text
不會連線正式金寶貝 API
```

---

## 正式 API 模式

設定：

```env
GOLDEN_BABY_API_MOCK=false
GOLDEN_BABY_API_ACCOUNT=正式帳號
GOLDEN_BABY_API_PASSWORD=正式密碼
```

正式模式流程：

```text
帳號密碼
    ↓
登入金寶貝 API
    ↓
access_token
    ↓
Authorization: Bearer <token>
    ↓
取得兒童資料
```

目前：

> API Client、模式切換與同步機制已完成。

但正式 API 環境仍需：

- 院方提供有效帳號
- 院方提供有效密碼
- 驗證正式 API 回傳格式
- 驗證正式資料內容

因此目前整合流程主要以：

```text
MOCK 模式
```

完成開發與功能驗證。

---

# Admin 兒童同步

Django Admin 的兒童管理頁提供：

```text
從金寶貝 API 同步
```

流程：

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

---

# Dry Run

進入同步頁面不會直接修改資料庫。

必須由管理者按下：

```text
確認同步
```

後才會：

- 新增 Child
- 更新 Child

---

# Admin 顯示資料來源

同步頁會顯示：

```text
MOCK 模擬模式
```

或：

```text
正式 API 模式
```

方便開發、測試與專題展示時確認目前使用的資料來源。

---

# M04 內部 API

## 家長端 API

權限：

```text
登入使用者
```

家長身分驗證機制待院方 APP 正式介接後再收斂。

| Method | Endpoint | 用途 |
|---|---|---|
| GET | `/api/questionnaires/<version_id>/schema/` | 取得完整問卷 Schema |
| POST | `/api/responses/` | 開始填答 |
| GET | `/api/responses/<id>/` | 取得既有填答 |
| PATCH | `/api/responses/<id>/autosave/` | 暫存答案 |
| POST | `/api/responses/<id>/complete/` | 完成送出 |

---

## Schema Preview

草稿預覽：

```text
/api/questionnaires/<version_id>/schema/?preview=1
```

可讀取草稿版本。

預覽模式：

```text
不寫入正式填答資料
```

---

# 問卷編輯器 API

權限：

```text
IsAdminUser
```

需要：

```text
staff 帳號
```

API 前綴：

```text
/api/builder/
```

提供：

- 問卷 CRUD
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

---

## 批次排序

```text
versions/<id>/reorder/
```

---

# Builder 功能

目前 Builder 支援：

## 問卷基本資料

- 名稱
- 說明
- 分類
- Tier

## 題組

- 新增
- 編輯
- 排序

## 題目

- 新增
- 編輯
- 必填
- 選填
- 題型
- 排序

## 選項

- 新增
- 編輯
- 刪除
- 排序

## 分支條件

- 題目顯示
- 題目隱藏
- 題組顯示
- 題組隱藏
- 觸發指定問卷
- 觸發下一 Tier

## 適用規則

- 最小月齡
- 最大月齡
- 追蹤狀態
- 不限
- 日期起訖
- 填答頻率

---

# 非草稿版本寫入

對非草稿版本進行 Builder 寫入時：

```text
HTTP 409
```

系統要求：

```text
複製為新版本
```

再進行修改。

---

# Admin 填答紀錄查詢

Django Admin 可查詢：

- 兒童
- 問卷
- 日期
- Tier
- 問卷版本
- 完成狀態

填答紀錄列表可顯示：

- 兒童
- 問卷
- 問卷版本
- 狀態
- 開始時間
- 完成時間
- 資料來源

---

# 已驗證功能

## 問卷管理

已人工驗證：

- 問卷建立
- 問卷分類
- Tier 設定
- 題組建立
- 題目建立
- 選項建立
- 必填設定
- 題型設定
- 題目排序
- 預覽

---

## Tier 0～Tier 5

已驗證同一套 Builder 可建立：

```text
Tier 0
Tier 1
Tier 2
Tier 3
Tier 4
Tier 5
```

不需要修改程式。

---

## 條件式分支

已驗證：

```text
回答 A
    ↓
顯示追問題組
```

以及：

```text
回答 B
    ↓
隱藏追問題組
```

---

## 跨 Tier / 跨問卷

已驗證：

```text
Tier 1
    ↓
特定答案
    ↓
完成來源問卷
    ↓
觸發 Tier 2
```

目標問卷可正常加入兒童待填清單並完成填答。

---

## 適用規則

已驗證：

### 月齡符合

```text
12～24 個月規則
20 個月兒童
→ 顯示
```

### 月齡不符合

```text
12～24 個月規則
32 個月兒童
→ 不顯示
```

### 追蹤狀態符合

```text
tracking_status = 一般
EligibilityRule = 一般
→ 顯示
```

### 追蹤狀態不符合

```text
tracking_status != 一般
→ 不顯示
```

---

## 填答頻率

已驗證：

```text
每日
```

完成當日填答後，同日不會立即重新列為待填。

---

## 家長端孩子資料

已驗證：

- 新增孩子
- 編輯孩子
- 修改出生日期
- 修改追蹤狀態
- 修改後重新計算適用問卷

---

# 問卷填答流程

已驗證：

```text
未記錄
    ↓
開始填答
    ↓
未完成
    ↓
暫存
    ↓
離開
    ↓
再次進入
    ↓
續填
    ↓
完成
    ↓
歷史紀錄
```

---

# 版本管理流程

已驗證：

```text
草稿 v1
    ↓
預覽
    ↓
發布 v1
    ↓
內容鎖定
    ↓
複製為 v2
    ↓
修改
    ↓
發布 v2
```

---

# 歷史版本保留

已驗證：

```text
兒童 A
完成 v1
```

發布 v2 後：

```text
兒童 A 的歷史紀錄
仍然顯示 v1
```

新兒童：

```text
使用最新已發布版本
```

舊資料不會被新版問卷改寫。

---

# 金寶貝 API 整合驗證

目前主要以：

```text
MOCK 模式
```

完成以下流程驗證：

```text
金寶貝 MOCK API
    ↓
取得兒童資料
    ↓
同步預覽
    ↓
建立 / 更新 Child
    ↓
設定 guardian
    ↓
計算月齡
    ↓
EligibilityRule
    ↓
家長端待填問卷
    ↓
問卷填答
    ↓
QuestionnaireResponse
    ↓
Answer
```

---

# 同步流程已驗證

- 新兒童可建立
- 已存在兒童不重複建立
- 基本資料差異可被偵測
- Dry Run 不修改資料庫
- 管理者確認後才寫入
- `tracking_status` 不被外部 API 覆蓋
- API 同步兒童可正常套用 EligibilityRule
- API 同步兒童可正常完成問卷
- 填答結果可正常回存

---

# 自動測試

執行：

```bash
python manage.py test
```

系統檢查：

```bash
python manage.py check
```

---

# 測試檔

## questionnaires/tests.py

測試：

- 已發布版本不可覆寫
- 狀態轉換
- 分支目標約束
- Admin Smoke Test

---

## questionnaires/tests_logic.py

測試：

- 分支判斷
- EligibilityRule
- 月齡
- 追蹤狀態
- 待填問卷推導
- 頻率相關邏輯

---

## questionnaires/tests_api.py

家長端 API 端對端測試：

- Schema
- 建立 Response
- 取得 Response
- Autosave
- Complete

---

## questionnaires/tests_views.py

測試：

- 家長端入口
- 兒童頁面
- 問卷呈現流程

---

## questionnaires/tests_builder.py

測試：

- Builder API
- 問卷
- 版本
- 題組
- 題目
- 選項
- 分支規則
- 適用規則

---

## accounts/tests.py

測試：

- 家長註冊
- 登入
- 登出
- 孩子登錄
- 帳號相關流程

---

# 跨機器開發

目前開發環境：

- macOS
- Fedora
- Windows

每台電腦獨立維護 Python Virtual Environment。

套件版本透過：

```text
requirements.txt
```

保持一致。

---

# Migration

```text
migrations/
```

必須加入 Git 版控。

切換電腦後：

```bash
git pull
pip install -r requirements.txt
python manage.py migrate
```

---

# 尚未完成 / 待院方確認

## 1. 金寶貝正式 API 環境驗證

目前已完成：

- API Client
- MOCK 模式
- 正式模式切換
- 同步預覽
- Child 同步流程

尚待：

- 院方正式 API 帳號
- 院方正式 API 密碼
- 正式連線測試
- 正式 API Response 格式確認
- 正式欄位語意確認
- 實際資料驗證

---

## 2. 家長端與院方 APP 身分串接

目前：

```text
Django Session
```

作為展示與測試登入方式。

正式：

- APP 身分如何帶入
- Token / Session 如何交換
- 家長與兒童關聯如何取得

仍待院方介接規格確認。

---

## 3. 兒科部正式問卷內容

目前系統功能已支援問卷設計。

但實際：

- 題目
- 選項
- 量表
- 適用時期
- 月齡條件
- 追蹤條件
- 分支條件
- Tier 使用情境

仍需由兒科部確認。

---

## 4. PWA Service Worker

離線及：

```text
加入主畫面
```

功能列為：

```text
Phase 2
```

---

## 5. 編輯器拖曳排序

目前：

```text
↑
↓
```

上下箭頭調整題目及題組順序。

尚未提供：

```text
Drag & Drop
```

拖曳排序。

---

## 6. 多條件 AND / OR 分支

目前 BranchRule 採：

```text
單一觸發題
+
單一條件
+
單一值
```

尚未提供複合邏輯，例如：

```text
條件 A AND 條件 B
```

或：

```text
條件 A OR 條件 B
```

此功能可列為後續擴充項目。

---

# 第一階段功能驗證摘要

目前 M04 已完成並實際驗證：

| 功能 | 狀態 |
|---|---|
| 多類型問卷建立 | ✅ |
| Tier 0～Tier 5 | ✅ |
| 題組 / 題目 / 選項 | ✅ |
| 常用題型 | ✅ |
| 條件式分支 | ✅ |
| 跨問卷觸發 | ✅ |
| 跨 Tier 觸發 | ✅ |
| 月齡適用規則 | ✅ |
| 追蹤狀態適用規則 | ✅ |
| 適用時期 | ✅ |
| 填答頻率 | ✅ |
| 適用期間 | ✅ |
| 建議填答時點 UI | ✅ |
| 草稿 / 預覽 / 發布 | ✅ |
| 已發布版本內容鎖定 | ✅ |
| 複製新版本 | ✅ |
| 舊版本歷史保留 | ✅ |
| 未記錄 | ✅ |
| 未完成 | ✅ |
| 暫存 / 續填 | ✅ |
| 已完成 | ✅ |
| 家長端孩子資料編輯 | ✅ |
| Admin 填答紀錄查詢 | ✅ |
| MOCK API 同步 | ✅ |
| 正式金寶貝 API | ⏳ 待院方帳密 |
| 院方 APP 身分串接 | ⏳ 待規格 |
| PWA | ⏳ Phase 2 |
| 拖曳排序 | ⏳ 待擴充 |
| AND / OR 複合分支 | ⏳ 待擴充 |

---

# 系統定位

M04 的核心不是：

```text
Tier 0 問卷
Tier 1 問卷
Tier 2 問卷
Tier 3 問卷
Tier 4 問卷
Tier 5 問卷
```

六份固定功能。

而是：

```text
一套健康問卷管理系統
        ↓
醫護自行建立問卷
        ↓
設定 Tier
        ↓
設定適用條件
        ↓
設定題目
        ↓
設定分支
        ↓
發布
        ↓
家長端動態呈現
        ↓
結果回存兒童健康紀錄
```

Tier 0～Tier 5 僅為第一階段最低支援與驗證基準。

系統架構保留：

- 新增問卷
- 新增分類
- 新增 Tier
- 新增照護情境
- 新增條件規則

之擴充能力，而不需將問卷內容寫死於 APP 程式中。