# TrailSnap 夜间测试值守 · 任务清单

> 任何 AI agent（Codex / Claude / GPT 等）或人拿到这份清单，都能自主完成一轮「测试 → 失败修复 / 盲区补测 → 提交」。
>
> 本文档是「单一事实源」。执行时不再需要回头询问任何前置决策；遇到模糊点请按本文档默认策略处理并继续。

---

## 0. 角色、时间、范围

- **执行者**：具备 shell + git 写权限、对 Python / TypeScript 有基本阅读能力的 AI 或人。
- **仓库根**：`E:\Project\TrailSnap`（绝对路径优先）。
- **时区**：Asia/Shanghai（机器已设）。
- **影响范围**：只能新增 / 修改以下路径，超出即停止：
  - `tests/`
  - `package/server/app/`
  - `package/server/tests/`
  - `package/ai/app/`
  - `package/website/tests/`
- **禁止动作**：
  - 推送到远端（`git push`）。
  - 修改 `tests/scripts/run-tests.ps1` 本身（除非有明确 bug，改完加 `// [skip-nightly]` 注释）。
  - 在 commit message 里出现：`构建后端`、`构建前端`、`构建ai`、`构建AI`、`构建cli`（这些字面量会触发 Docker 构建 / npm 发布 CI）。
  - 删除数据库 / 清理用户上传的 `data/uploads/`，除非是测试自己产生的临时文件。

---

## 1. 预检（每次必做，失败立刻中止并写 ALERT）

```powershell
cd E:\Project\TrailSnap

# 1.1 工作区脏检查
$dirty = git status --porcelain
if ($dirty) {
    # 排除预期内的 .env.test、__pycache__ 等
    $allowed = $dirty | Where-Object { $_ -match '^\?\? (tests\\.env\.test|.*\\__pycache__\\|.*\.pyc|tests\\artifacts\\)' }
    $real = $dirty | Where-Object { $_ -notmatch '^\?\? (tests\\.env\.test|.*\\__pycache__\\|.*\.pyc|tests\\artifacts\\)' }
    if ($real) { Write-ALERT "工作区有非预期改动" $real; exit 2 }
}

# 1.2 分支检查
$branch = git rev-parse --abbrev-ref HEAD
if ($branch -in @('main','master')) {
    git checkout -b "nightly/test-watch-$(Get-Date -Format 'yyyyMMdd')"
    # 若已存在同名分支，沿用现有，不重建
}

# 1.3 环境变量文件
if (-not (Test-Path 'tests\.env.test')) {
    if (Test-Path 'tests\.env.test.example') {
        Copy-Item 'tests\.env.test.example' 'tests\.env.test'
    } else {
        Write-ALERT "缺少 tests\.env.test 且无模板"; exit 2
    }
}
```

1.4. 创建当次目录：
   ```powershell
   $stamp = Get-Date -Format 'yyyy-MM-dd'
   $runDir = "tests\artifacts\nightly\$stamp"
   New-Item -ItemType Directory -Path $runDir -Force | Out-Null
   ```

---

## 2. 运行测试

```powershell
.\tests\scripts\run-tests.ps1 -Layer e2e -Level full `
    2>&1 | Tee-Object -FilePath "$runDir\run.log"
$exit = $LASTEXITCODE
"$exit" | Set-Content "$runDir\exit.txt"
```

- `$exit -eq 0` → §4（盲区扫描）。
- `$exit -ne 0` → §3（失败分类）。

---

## 3. 失败分类与修复

3.1. 提取失败用例：
   - pytest：`Get-ChildItem -Recurse -Filter 'junit*.xml' $runDir | ForEach-Object { [xml](Get-Content $_) }` 或 `Select-String -Pattern '^FAILED' $runDir\run.log`
   - Playwright：`Select-String -Pattern '✘| failed|\bError:' $runDir\run.log`

3.2. **逐个判断类型**（A / B / C 三选一，不允许跳过判断直接改代码）：

   | 现场特征（关键字）                                      | 类型        | 动作                                                |
   |--------------------------------------------------------|-------------|-----------------------------------------------------|
   | `ModuleNotFoundError`、`fixture not found`、import 路径错 | A 测试代码  | 改测试的 import / fixture 名                        |
   | `AssertionError` 且断言语义与 docstring / 类型注解冲突   | A 测试代码  | 修正断言匹配正确行为，加注释说明                    |
   | `AssertionError` 且明显是行为回归（之前能用的功能坏了）  | B 业务代码  | 修复被测代码                                        |
   | `AssertionError` 但被测代码与断言都不明显有理            | 模糊        | 读 `git log -p` 最近一次改动，由改动判定 A 还是 B     |
   | `Connection refused` / `ETIMEDOUT` 到 127.0.0.1:8000     | C 环境      | 不改业务代码，restart 后端后重试一次                 |
   | `playwright._impl._errors.TimeoutError` 等 selector     | A 或 C      | 先看 selector 是否仍存在；不在 → A，存在 → C        |
   | `psycopg2.OperationalError` / `database "x" does not exist` | C 环境  | `python start.py` 重建 DB 后重试                    |
   | 整段套件 `skip`（无失败用例但 exit != 0）                | A 测试代码  | 检查 `TS_TEST_USERNAME` / `TS_TEST_PASSWORD` 配置  |

3.3. **修复原则**：
   - 优先 A：改测试，不动业务代码。
   - A 改之前必须读被测函数源代码 + 最近 `git log -p -- <file>`，确认是测试错。
   - B 改必须更新或新增对应单元测试覆盖该回归点。
   - C 独立处理：环境修好后不算「业务改动」，不进入 §6 提交流程。

3.4. 重跑策略（最小重跑单元，节省时间）：
   ```powershell
   # 单个 pytest 用例
   python -m pytest path\to\test_x.py::test_y -v

   # 单个 playwright 用例（按 grep 过滤）
   pnpm --dir package/website exec playwright test --grep "<失败用例名>"
   ```

3.5. **重试上限**：单用例两次失败仍未修 → 立即停止，回滚本用例相关代码改动，写 ALERT，跳过本轮 commit。

3.6. 全部失败修完，跑一次完整 e2e 确认无回归：
   ```powershell
   .\tests\scripts\run-tests.ps1 -Layer e2e -Level full
   ```
   - 通过 → §4。
   - 仍有失败 → §3.5 处理剩余失败；如果只是「测试运行慢导致超时」这种 C 类，retry 后仍超时则整体放弃本轮 commit。

---

## 4. 盲区扫描（每次必做，独立于 §3 结果）

4.1. **后端 Python 盲区**：
   ```powershell
   $serverRoot = (Resolve-Path 'package\server').Path
   $candidates = Get-ChildItem -Recurse -Filter *.py 'package\server\app' `
       | Where-Object { $_.FullName -notmatch 'migrations|__pycache__|db\\models' }
   $gaps = foreach ($f in $candidates) {
       $rel = $f.FullName.Substring($serverRoot.Length + 1) -replace '\\','/'
       $testA = "package\server\tests\$($f.BaseName).py"
       $testB = "package\server\tests\$($f.BaseName)\test_*.py"
       if (-not (Test-Path $testA) -and -not (Get-ChildItem -Path $testB -ErrorAction SilentlyContinue)) {
           [PSCustomObject]@{ Module = $rel; Layer = 'server' }
       }
   }
   $gaps | Sort-Object Module | ConvertTo-Markdown | Set-Content "$runDir\coverage-gaps-backend.md"
   ```
   若没有 `ConvertTo-Markdown` 模块，改用 `Format-Table Module,Layer | Out-String`。

4.2. **AI 服务盲区**：把上面 `package\server\app` 换成 `package\ai\app`，`tests` 换成 `package\ai\tests`。

4.3. **前端 E2E 盲区**：
   - 列出 `package\website\src\views\**\*.vue`
   - 在 `package\website\tests\e2e\*.spec.ts` 中 grep 每个 view 的路径 / 组件名 / 路由 path
   - 未被任何 spec 引用过的 view 视为候选
   - 写入 `$runDir\coverage-gaps-frontend.md`

4.4. **优先级排序**：
   1. 前端未覆盖的 view 或 现有测试中覆盖不全的 view（最高，缺一个就补一个）
   2. `app/api/*.py` 中的 router
   3. `app/service/*.py` 业务逻辑
   4. `app/utils/*.py`、`app/schemas/*.py`
   5. AI service 的 routers

4.5. 选 **5 - 10 个**最高优先级模块。

---

## 5. 编写新测试

5.1. 写之前必读：
   - 被测模块 docstring、类型注解、`git log -3 -- <file>`。
   - 同目录已有测试文件，模仿 fixture 命名 / async 模式 / 断言库。
   - E2E 参考 `package\website\tests\e2e\global-setup.ts` 与现有 spec 的 `storageState` 复用方式。

5.2. 每个模块写 **1 - 3 个**用例，覆盖：
   - Happy path（正常输入返回正常结果）
   - Edge（空输入、边界值、特殊字符）
   - Error（非法输入、未授权、依赖不可用）

5.3. 必须遵守：
   - 后端：使用 `tests/conftest.py` 已有的 fixture；不要新建 DB 连接。
   - E2E：用现有 `storageState` 复用登录态；不写新的全局 setup。
   - 不修改任何现有测试，只新增文件或新增 `def test_xxx` 函数。
   - 不修改 `tests/.env.test`，需要新环境变量时改 `.env.test.example` 并在 summary 说明。

5.4. 单独跑新测试，必须全绿：
   ```powershell
   python -m pytest path\to\test_new_module.py -v
   # 或
   pnpm --dir package\website exec playwright test tests\e2e\new.spec.ts
   ```

5.5. 再跑一次完整 e2e（同 3.6），确认无回归。
   ```powershell
   .\tests\scripts\run-tests.ps1 -Layer e2e -Level full
   ```

5.6. 失败处理：
   - 新测试连续 **3 次**失败 → 停止本轮，写 ALERT；
   - 已写但失败的新测试文件 `git checkout -- <file>` 回滚到 HEAD；
   - 不进入 §6。

5.7. 关闭所有服务（server+ai+website）：
   ```powershell
   .\tests\scripts\run-tests.ps1 -StopServices
   ```

---

## 6. 提交

6.1. 复查：
   ```powershell
   git status
   git diff --stat
   ```
   - 改动文件必须全部在 §0 列出的「影响范围」内；否则写 ALERT，退出码 5。

6.2. Stage：
   ```powershell
   git add tests/ package/server/app/ package/server/tests/ package/ai/app/ package/website/tests/
   ```

6.3. Commit message（Conventional Commits）：
   ```
   test(nightly): <一句话描述>

   - 修复失败用例: <test_module>::<test_func>（类型 A / B / C）
   - 新增覆盖: <module1>, <module2>

   Nightly watch run YYYY-MM-DD
   Co-authored-by: Codex <noreply@openai.com>
   ```

6.4. 不 push。记录 commit SHA：
   ```powershell
   git rev-parse HEAD | Set-Content "$runDir\commit.txt"
   ```

---

## 7. 报告与 ALERT

7.1. **每次**写 `$runDir\summary.md`：
   ```markdown
   # Nightly Watch Summary — YYYY-MM-DD HH:MM

   - 测试结果: PASS / FAIL_FIXED / ENV_SKIP
   - 失败用例: <N>（修复 A=<a> B=<b> C=<c>）
   - 新增测试: <M> 个模块 / <K> 个用例
   - Commit: <sha | 无>
   - 状态: OK / NEEDS_HUMAN
   - 最终完整 E2E：0 passed / 03 skipped / 0 failed。
   - 耗时: <minutes>

   ## 修复明细
   - tests/test_xxx.py::test_yyy [A] - <一句话>
   - package/server/app/foo.py [B] - <一句话>

   ## 新增测试明细
   - tests/test_foo.py - <模块功能简述>，3 个用例（happy/edge/error）

   ## 下次待办
   - <例如：后端 8 个 router 仍无测试覆盖>
   ```

7.2. **触发 ALERT**（写 `$runDir\ALERT.md`，退出码非 0）的条件：
   | 条件                                   | 退出码 |
   |----------------------------------------|--------|
   | 工作区脏（§1.1）                       | 2      |
   | 在保护分支且无法切出（§1.2）            | 2      |
   | 失败用例两次重试未修（§3.5）            | 3      |
   | 新测试连续 3 次失败（§5.6）            | 4      |
   | commit 失败 / 改动超范围（§6.1）        | 5      |
   | 总耗时 > 90 分钟                       | 6      |

7.3. **append 到全局日志**：
   ```powershell
   "YYYY-MM-DD HH:MM | PASS/FAIL_FIXED/ENV_SKIP | A=$a B=$b C=$c | new=$m mod/$k case | commit=$sha" `
       | Add-Content 'data\logs\test-nightly.log' -Encoding UTF8
   ```

7.4. 清理：保留最近 7 天的 `$runDir`，更早的移到 `$runDir\_archive\` 或删除（首期保守保留 7 天）。

---

## 8. 给用户的最终输出格式

成功：
```
✅ Nightly Watch YYYY-MM-DD 完成
测试结果: PASS / FAIL_FIXED
最终完整 E2E：2 passed / 0 skipped / 0 failed
新增测试: M 个模块 / K 个用例
Commit:   <sha | 无>
报告:     tests\artifacts\nightly\YYYY-MM-DD\summary.md
```

失败 / 中断：
```
⚠️ Nightly Watch YYYY-MM-DD 中断
原因:   <简述>
位置:   §<最后一次成功的步骤编号>
ALERT:  tests\artifacts\nightly\YYYY-MM-DD\ALERT.md
建议:   <一段话>
```

---

## 9. 执行附录：常用命令速查

| 用途                  | 命令                                                                 |
|-----------------------|----------------------------------------------------------------------|
| 跑全部 e2e            | `.\tests\scripts\run-tests.ps1 -Layer e2e -Level full`               |
| 跑单个 pytest 用例    | `python -m pytest tests/test_x.py::test_y -v`                        |
| 跑单个 playwright     | `pnpm --dir package/website exec playwright test --grep "用例名"`    |
| 重建后端 DB + 起服务  | `python start.py`                                                    |
| 起 AI 服务            | `cd package\ai && uvicorn main:app --port 8001`                      |
| 看某文件最近改动      | `git log -p -3 -- <path>`                                            |
| 回滚单文件            | `git checkout -- <path>`                                             |
| 关闭所有服务（server+ai+website） | ` .\tests\scripts\run-tests.ps1 -StopServices`                                             |

---

## 10. 元信息

- 创建：2026-07-22
- 适用范围：TrailSnap 当前主干（main / feat-* 分支皆可；保护分支禁止）。
- 维护者：项目所有者 + Codex nightly agent。
- 修订原则：跑通 4 周后回看，新增「经常踩坑的失败类型」到 §3.2 表中。
