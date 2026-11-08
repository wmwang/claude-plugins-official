# code-modernization Plugin 團隊作業說明書

> 情境：舊系統為 VS .NET WinForms（`.cs` + `.Designer.cs`），目標為 React + TypeScript 前端 + Java Spring Boot 後端。
> 範例專案：一個 Repo、內含 10 個互相有關聯的模組。

---

## 一、先記住三條鐵律

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ 鐵律 1：一個 Repo = 一個系統名稱（本文用 erp），從頭到尾不拆。           │
│         模組之間有相依（共用 DB、共用 DLL、互相呼叫），拆成多個系統名稱  │
│         會切斷相依關係，preflight 的 Check 6 就是在防這件事。            │
│                                                                          │
│ 鐵律 2：模組名稱不是人取的，是 map 階段寫在 topology.json 裡的節點 id。  │
│         Brief 的 Modules: 一行、transform/verify 的第二個參數都要照抄它。│
│                                                                          │
│ 鐵律 3：檔案才算數，聊天不算數。                                         │
│         要調整施工順序或驗收條件，直接改 MODERNIZATION_BRIEF.md 並簽核； │
│         在對話裡跟 AI 說「先做 A」不具約束力。                           │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 二、名詞對照表

| 名詞 | 白話意思 |
|---|---|
| system（系統名稱） | 整個 Repo 的代號，例如 `erp`。所有指令的第一個參數。 |
| module（模組） | `topology.json` 裡的節點 id，例如 `OrderForm`。transform / verify 的第二個參數。 |
| Phase（施工梯次） | Brief 把所有模組分成 3~6 個梯次，決定「哪些模組先搬」。 |
| P0 / P1 / P2 | 規則的重要度。P0 = 錯了會賠錢、違法、壞掉核心功能，是驗收必考題。 |
| Rule card（規則卡） | 一條商業規則，格式為 Given / When / Then，附舊碼 `檔案:行號`。 |
| Brief（計畫書） | `MODERNIZATION_BRIEF.md`，施工總控表，人類簽核後才能動工。 |
| Pilot（試點） | Phase 1，挑最簡單的模組先跑完整流程，用來驗證做法。 |
| Canary（金絲雀） | 故意改壞新程式的一行，測試必須變紅，證明測試真的有效。 |
| PROVEN | verify 由腳本判定的最高等級：新程式行為已被證明與舊系統一致。 |

> [!NOTE]
> **Phase 和 P0 是兩件事。** Phase 是「模組的先後順序」；P0 是「每個模組內部最重要的規則」。每個模組不管排在第幾個 Phase，裡面都有自己的 P0 / P1 / P2。Phase 1 通常反而挑 **P0 最少、最單純** 的模組。

---

## 三、檔案地圖（東西都放在哪）

```text
workspace/
├── legacy/erp  ──────────► Symlink 指向舊系統 Repo（唯讀，任何指令都不准改）
│
├── analysis/erp/          ◄── 全系統共用，只有一份（由 Tech Lead 在主幹維護）
│   ├── INTENT.md                 目標：WinForms → React + Spring Boot
│   ├── PREFLIGHT.md              五個人工問題的回答 + 範圍邊界檢查
│   ├── ASSESSMENT.md             規模、複雜度、技術債、資安
│   ├── topology.json             全系統地圖（模組 id 的唯一來源）
│   ├── BUSINESS_RULES.md         規則總表（會隨波次累積變大）
│   ├── DATA_OBJECTS.md           資料結構 / DTO 欄位表
│   ├── RULE_REVIEWS.json / .md   人類審核規則的紀錄
│   └── MODERNIZATION_BRIEF.md    施工總控表（3~6 個 Phase + 簽核欄）
│
└── modernized/erp/        ◄── 每個模組一個資料夾，可多人平行
    ├── OrderForm/
    │   ├── backend/              Spring Boot + JUnit 5
    │   ├── frontend/             React + TS + Vitest
    │   └── TRANSFORMATION_NOTES.md   該模組的畫面 / API / 規則對照
    ├── BillingForm/
    └── ...
```

---

## 四、角色分工

| 角色 | 負責的步驟 | 主要產出 / 決策 |
|---|---|---|
| **Tech Lead / 架構師** | Step 0~3、每個 Phase 的 Step 4 與 Step 5、合併分支 | 全系統地圖、規則總表、Brief 初稿；維護 `analysis/erp/` |
| **SA / 業務專家（SME）** | Step 4b（審規則）、協助 Step 5 | 判定規則 Right / Wrong / Not sure；回答待決問題 |
| **核准者（主管 / PO）** | Step 5 之後的簽核 | 在 Brief 簽名，決定只放行 Phase 1 或整份計畫 |
| **開發工程師** | Step 6、Step 7（一人負責一個模組） | 新程式碼、測試、拿到 PROVEN |
| **第二位工程師** | Step 7 之後 | 交叉檢查 `VERIFICATION.md` 並共同簽核 |

> [!IMPORTANT]
> **Plugin 規定有六個點必須由人決定，AI 不會代勞：**
> preflight 的五個問題、看起來有問題的規則（review）、核准 Brief、接受驗證找到的差異、簽核驗證結果、套用資安修補。

---

## 五、10 個模組的範例專案

### 5.1 map 之後，topology.json 裡的 10 個模組

| 模組 id | 說明 | 相依 |
|---|---|---|
| `CommonLib` | 共用工具、代碼表 | 被大家使用 |
| `AuthCore` | 登入與權限 | 被大家使用 |
| `CustomerQuery` | 客戶查詢（唯讀） | 用 CommonLib |
| `ProductMaint` | 商品維護 | 用 CommonLib |
| `TaxCalc` | 稅額計算 | 用 CommonLib |
| `QuotationForm` | 報價單 | 用 CustomerQuery、ProductMaint |
| `OrderForm` | 訂單 | 用 Quotation、TaxCalc |
| `StockForm` | 庫存 | 與 OrderForm 共用 STOCK 資料表 |
| `BillingForm` | 帳務 | 用 OrderForm、TaxCalc |
| `MonthlyReport` | 月結報表 | 讀取以上全部 |

### 5.2 Brief 自動排出的 Phase（AI 初稿，人類可改）

```text
Phase 1  試點（S）  ：CustomerQuery
Phase 2  基礎（M）  ：CommonLib, AuthCore, TaxCalc, ProductMaint
Phase 3  業務（L）  ：QuotationForm, StockForm
Phase 4  核心（XL） ：OrderForm, BillingForm
Phase 5  收尾（M）  ：MonthlyReport
```

排序依據（Plugin 自動計算）：
1. `topology.json` 的相依關係：依賴少、風險低的先做（絞殺者模式）。
2. `ASSESSMENT.md` 的複雜度：標出每個 Phase 的 S / M / L / XL 規模。
3. `RULE_REVIEWS.json` 與 `PREFLIGHT.md`：有爭議的 P0 或被外部依賴的模組，會加上開工條件擋住。

> [!TIP]
> 同一個 Phase 裡的模組，就是可以**同時分給不同工程師**的清單。

---

## 六、完整流程

### 階段 A：整個專案只做一次（Tech Lead）

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ Step 0  /code-modernization:modernize erp --source <舊系統路徑>          │
│         回答目標（重寫）與目標技術 → INTENT.md                           │
│                                                                          │
│ Step 1  /code-modernization:modernize-preflight erp                      │
│         ★人工：回答 5 個問題（範圍、能否本機建置、特殊建置、前人嘗試、  │
│           禁區）→ PREFLIGHT.md                                           │
│                                                                          │
│ Step 2  /code-modernization:modernize-assess erp       → ASSESSMENT.md   │
│                                                                          │
│ Step 3  /code-modernization:modernize-map erp          → topology.json   │
│         ★人工：熟悉系統的工程師檢查地圖、模組切分是否合理               │
└──────────────────────────────────────────────────────────────────────────┘
                     │  把 analysis/erp/ commit 進主幹
                     ▼
```

### 階段 B：每個 Phase 重複一次（以 Phase 3 為例）

```text
┌──────────────────────────────────────────────────────────────────────────┐
│ ① Tech Lead（主幹，一人執行）                                            │
│   Step 4  /code-modernization:modernize-extract-rules erp "<模組範圍>"   │
│           只抽這個 Phase 的模組（QuotationForm、StockForm）              │
│           → 規則合併進 BUSINESS_RULES.md、DATA_OBJECTS.md                │
├──────────────────────────────────────────────────────────────────────────┤
│ ② SA / 業務專家                                                          │
│   Step 4b /code-modernization:modernize-review erp                       │
│           已審過的規則自動跳過，只問新的、有疑問的 P0 規則               │
│           → RULE_REVIEWS.json                                            │
├──────────────────────────────────────────────────────────────────────────┤
│ ③ Tech Lead → 核准者                                                     │
│   Step 5  /code-modernization:modernize-brief erp                        │
│           更新 Brief：前面 Phase 維持已完成，填入本 Phase 的 P0 契約、   │
│           開工 / 完工條件、待決問題                                      │
│   ★人工：核准者閱讀、必要時直接改檔，然後簽核                           │
│           （/modernize-sign，或手動填 Approved by 欄位）                 │
└──────────────────────────────────────────────────────────────────────────┘
                     │  commit 主幹，開始派工
          ┌──────────┴──────────┐
          ▼                     ▼
┌──────────────────────┐ ┌──────────────────────┐
│ ④ 工程師 A（分支）   │ │ ④ 工程師 B（分支）   │
│ Step 6               │ │ Step 6               │
│  modernize-transform │ │  modernize-transform │
│   erp QuotationForm  │ │   erp StockForm      │
│ Step 7               │ │ Step 7               │
│  modernize-verify    │ │  modernize-verify    │
│   erp QuotationForm  │ │   erp StockForm      │
│ → PROVEN             │ │ → PROVEN             │
└──────────┬───────────┘ └──────────┬───────────┘
           └───────────┬────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ ⑤ Tech Lead：合併分支、確認 Brief 本 Phase 完工條件、第二位工程師簽核   │
│    驗證結果 → 進入下一個 Phase，回到 ①                                   │
└──────────────────────────────────────────────────────────────────────────┘
```

### Step 6 / Step 7 各自做了什麼

| 步驟 | 內容 |
|---|---|
| Step 6 transform | 檢查前後端工具鏈 → 讀 Brief 與該模組的規則 → **先提出計畫等人核可** → 寫測試釘住舊行為 → 產出 `backend/`、`frontend/` 與 `TRANSFORMATION_NOTES.md`（含畫面 / React / API 三方對照表） |
| Step 7 verify | 清除建置產物後重跑全部測試 → 對照每條 P0 是否有「跑過且通過」的測試 → Canary 測試 → 由 `proof_pack.py` 腳本判定 PROVEN / PARTLY PROVEN / NOT PROVEN |

---

## 七、哪些步驟能平行、哪些不行

| 步驟 | 可否多人平行 | 原因 |
|---|---|---|
| Step 0~3 | ❌ 只跑一次 | 產出全系統唯一的地圖 |
| Step 4 抽規則 | ❌ 主幹一人執行 | 全系統只有一份 `BUSINESS_RULES.md` |
| Step 4b 審規則 | ⚠️ 可多位 SA 分領域審，但寫入同一份紀錄 | 共用 `RULE_REVIEWS.json` |
| Step 5 Brief | ❌ 主幹一人執行 | 全系統只有一份 Brief |
| Step 6 transform | ✅ 同一 Phase 內一人一模組 | 輸出在 `modernized/erp/<模組>/` 各自獨立 |
| Step 7 verify | ✅ 同上 | 帶模組參數各自驗證 |

**Git 建議：**
- `analysis/erp/` 由 Tech Lead 在主幹維護，工程師分支盡量不要改動裡面的共用檔案。
- 工程師分支命名例如 `feature/phase3-QuotationForm`，只放 `modernized/erp/QuotationForm/`。
- Brief 的打勾與簽核統一由 Tech Lead / 核准者在主幹處理，避免合併衝突。
- Plugin 不會自動 commit，每一步完成都要自己 commit。

---

## 八、已知限制與注意事項（導入前請大家知道）

> [!WARNING]
> **1. 規則編號可能在下一波重新洗牌。**
> `render_rules.py` 每次會把所有規則重新排序、從 `RULE-001` 重新編號。下一個 Phase 抽規則後，舊規則的編號可能改變，導致 `RULE_REVIEWS.json` 與已寫好的測試名稱（如 `test_RULE_004`）對不上。
> **暫時做法：** 同一個 Phase 的模組在 review 之前全部抽完；每次抽完都要比對舊編號有沒有變。
> **根本做法：** 正式導入前修改 `render_rules.py`，讓已存在的編號固定、新規則往後接號。

> [!WARNING]
> **2. 第二波抽規則是「合併」還是「覆蓋」，需要在試點時實測。**
> 官方指令只明寫「補跑失敗模組時要合併進 `rules_result.json`」。換一批模組抽取時，請確認舊規則沒有被覆蓋掉。

> [!NOTE]
> **3. `UI-State` / `UI-Flow` 是我們自己加的擴充，不是官方原生設計。**
> 它能讓 AI 抽出畫面連動與操作手順，作為轉寫與測試的檢查清單；但規則卡是零散的，**不等於完整的畫面規格書**（普通欄位、整體畫面樣貌不會出現）。

> [!NOTE]
> **4. 目前不會產出正式 API Spec。**
> 規則卡只有一行 `uiMapping` 的建議路徑；正式 API 是在 Step 6 寫程式時才決定。若需要事先審 API，未來可擴充 Step 5 產出 API 規格表。

> [!NOTE]
> **5. 檔案大小。**
> `MODERNIZATION_BRIEF.md` 不會很大（只列 Phase、模組名單、P0 標題）。會一直變大的是 `BUSINESS_RULES.md`；轉寫和驗證時 AI 只取跟當前模組有關的規則，影響有限。

> [!CAUTION]
> **6. 成本。** 抽規則是最耗資源的步驟（官方案例一次 50~200 個 agent）。先用 Phase 1 試點估算單一模組的時間與 token，再決定後續節奏。

---

## 九、常見問答

**Q：可以先把 10 個模組的規則全部抽完嗎？**
可以，但不建議第一次就這樣做。官方建議先做一個試點模組，確認規則粒度與流程後，再逐個 Phase 推進。

**Q：AI 排的 Phase 不滿意怎麼辦？**
直接編輯 `MODERNIZATION_BRIEF.md`，把模組 id 移到想要的 Phase 的 `Modules:` 行，再簽核。transform 會依照檔案內容執行。

**Q：工程師執行 transform 時不帶模組參數會怎樣？**
它會讀 Brief，自動挑「最早的 Phase 裡、還沒有 `TRANSFORMATION_NOTES.md` 的第一個模組」。多人作業時**請務必帶模組參數**，避免兩人搶到同一個模組。

**Q：P0 沒有測試覆蓋會怎樣？**
verify 拿不到 PROVEN。每條 P0 都必須有「實際執行且通過」的測試指名它（例如測試名稱含 `RULE-007`）。

**Q：規則被 SA 標成 Wrong 或 Not sure 會怎樣？**
Brief 會把它列入待決問題，並擋住該模組所屬 Phase；transform 不會把 Wrong 規則當成標準答案，遇到仍在討論的 P0 會停下來。

---

## 十、指令速查表

| 時機 | 指令 | 誰執行 |
|---|---|---|
| 專案開始 | `/code-modernization:modernize erp --source <路徑>` | Tech Lead |
| 專案開始 | `/code-modernization:modernize-preflight erp` | Tech Lead + 熟悉建置的人 |
| 專案開始 | `/code-modernization:modernize-assess erp` | Tech Lead |
| 專案開始 | `/code-modernization:modernize-map erp` | Tech Lead |
| 每個 Phase | `/code-modernization:modernize-extract-rules erp "<模組範圍>"` | Tech Lead |
| 每個 Phase | `/code-modernization:modernize-review erp` | SA / 業務專家 |
| 每個 Phase | `/code-modernization:modernize-brief erp` | Tech Lead |
| 每個 Phase | `/modernize-sign "<姓名, 職稱>"` | 核准者 |
| 每個模組 | `/code-modernization:modernize-transform erp <模組id>` | 開發工程師 |
| 每個模組 | `/code-modernization:modernize-verify erp <模組id>` | 開發工程師 |
| 隨時 | `/code-modernization:modernize-status erp` | 任何人（看進度與下一步） |
