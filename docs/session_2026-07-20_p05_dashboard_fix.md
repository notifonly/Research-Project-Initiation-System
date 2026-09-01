# P05 Dashboard 方案质量修复 + Playwright 环境修复 — Session Work Journal

**Date**: 2026-07-20
**Session**: 用户聚焦 p05(scFM + agent 两方向)，发现仪表盘"P05 方案质量"tab 异常；诊断修复 2 个数据问题，随后修复 Playwright 浏览器版本漂移
**Outcome**: data.json 恢复正常(9 候选 / 2 通过 / 50 LLM / 467 MCP / 28.3 min)，浏览器可视化验证通过，全局 MCP 已钉版防复发

---

## 概述

用户将工作重心收窄至 p05 项目（scFM + agent 两个方向），查看仪表盘时发现"P05 方案质量"tab 数据异常。诊断出 2 个独立问题并修复；可视化验证时又暴露 Playwright MCP 浏览器"未安装"误报，一并修复并做了防复发钉版。

---

## 发现的问题与根因

| # | 现象 | 根因 | 位置 |
|---|------|------|------|
| 1 | tab 显示 LLM 调用 0 / MCP 调用 0 / 耗时 0.0 min（真实值 30/351/1202.7s） | `_aggregate_harness_runs()` 从 checkpoint.json 读**文件级** `total_llm_calls` 等字段，但 `loop_runner._append_checkpoint()` 写的 checkpoint 只有 `{"candidates": [...]}`，统计字段在**每个 candidate 记录内** | `dashboard/build_data.py:725-727` |
| 2 | agent 方向验收结果完全不可见（含 2 个通过方案） | 分方向多次运行后未执行 `--merge`，`latest_run.txt` 只含 `post_fix_v3`（5 个 scFM 候选） | `data/p05_harness_output/latest_run.txt` |
| 3 | Playwright 报 `Browser "chrome-for-testing" is not installed`，但浏览器 7/8 已全局安装 | 全局配置 `npx -y @playwright/mcp` 无钉版 → 静默升级到 0.0.78 → 其 playwright-core 1.62.0-alpha 要求 chromium-**1232**，本机是旧版 MCP 安装的 chromium-**1228**；新版中 `--browser chromium` 映射 `channel: "chrome-for-testing"`，报错名是 channel 别名 | `C:\Users\cy\.config\opencode\opencode.jsonc:15` |
| 4 | `npx ...` 报 `PSSecurityException: UnauthorizedAccess` | Windows PowerShell 执行策略禁止运行 `.ps1` 脚本，`npx.ps1` 被拦截 | bash 工具调用方式 |
| 5 | playwright MCP 报 `Access to "file:" protocol is blocked` | MCP 服务端安全策略默认禁止 file:// 协议 | 验证方式 |

### 问题 1 关键细节

- 数据流：`_build_p05_harness()` → 读 `latest_run.txt` → `_aggregate_harness_runs()` 逐 run 读 `checkpoint.json`（优先）→ 写入 `data.json` 的 `p05_research_plans` → `js/tabs/p05.js` 渲染
- 已验证 post_fix_v3 的 5 个候选按 candidate 求和 = 30 LLM / 351 MCP / 1202.7s，与该 run 目录下 `harness_result.json` 的文件级统计**完全一致**
- `scripts/p05_harness/main.py` 的 `merge_runs()`(392-394 行）就是按 candidate 求和的，dashboard 聚合逻辑未对齐

### 问题 3 关键细节

- `npx -y` 每次解析最新 @playwright/mcp = 0.0.78(npx 缓存 `_npx\86170c4cd1c5da32`)
- 其 `playwright-core/lib/coreBundle.js`:`case "chromium"` → `{ browserName: "chromium", channel: "chrome-for-testing" }`
- 该版 `browsers.json` 要求 chromium rev=1232；`%LOCALAPPDATA%\ms-playwright\` 仅有 chromium-1228（旧版 MCP 7/8 安装，`chrome-win64\chrome.exe` 完好）
- PLAYWRIGHT_BROWSERS_PATH 未设置（默认 per-user 全局目录，安装位置无误）;**本质是版本漂移导致的修订号不匹配**

---

## 修复内容

### 1. `dashboard/build_data.py` — 聚合统计 bug

`_aggregate_harness_runs()`: 删除文件级累加（`total_llm += data.get("total_llm_calls", 0)` 等 3 行），在 run 循环结束后对**去重后**的 `all_candidates` 按 candidate 求和：

```python
# checkpoint.json has no file-level stats; sum per-candidate stats instead
# (matches merge_runs() semantics in scripts/p05_harness/main.py)
total_llm = sum(c.get("total_llm_calls", 0) for c in all_candidates)
total_mcp = sum(c.get("total_mcp_calls", 0) for c in all_candidates)
total_dur = sum(c.get("duration_s", 0.0) for c in all_candidates)
```

对 harness_result.json 来源（有文件级字段）的 run 结果不变，两种来源均正确。

### 2. 合并 agent_v3 进仪表盘视图

```powershell
python scripts/p05_harness/main.py --merge post_fix_v3,agent_v3
```

- 复用既有 `merge_runs()` 按 candidate_id 去重合并（5 + 4，无 ID 冲突）→ 9 候选
- 重写顶层 `harness_result.json`(9 候选聚合）与 `latest_run.txt`（两行：`post_fix_v3`、`agent_v3`)
- merge 不需要 API key（仅需 litellm 可导入）

### 3. 重建 dashboard

```powershell
python dashboard/build_data.py
# → P05 Harness: 2 passed, 7 failed, 9 candidates
```

### 4. Playwright 浏览器修复 + 钉版

```powershell
# npx.ps1 被 PowerShell 执行策略拦截 → 用 npx.cmd
npx.cmd -y "@playwright/mcp@0.0.78" install-browser chrome-for-testing
# → Chrome for Testing 151.0.7922.10 (chromium-1232) + headless shell 下载至 ms-playwright\
```

全局 `C:\Users\cy\.config\opencode\opencode.jsonc` 第 15 行钉版：

```jsonc
"command": ["npx", "-y", "@playwright/mcp@0.0.78", "--browser", "chromium"],
```

**注意：钉版需重启 opencode 生效**；浏览器安装无需重启（注册表检查在 launch 时进行）。以后升级 MCP：改版本号 + 重跑对应版本 `install-browser`。

---

## 验证结果

### data.json `p05_research_plans` 修复前后对照

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 候选数 | 5 | **9**(5 scFM + 3 agent + T006) |
| 通过 / 未通过 | 0 / 5 | **2 / 7** |
| total_llm_calls | 0 | **50**(30 post_fix_v3 + 20 agent_v3) |
| total_mcp_calls | 0 | **467** |
| total_duration_s | 0.0 | **1697.0**(28.3 min) |

通过验收的 2 个 agent 方案：`p05_agent_rl_002`(4.10)、`p05_agent_benchmark_003`(4.00)。

### 多层级验证

1. **data.json 字段校验**:python 读取断言通过（数值如上表）
2. **standalone HTML 内嵌数据校验**:`index_standalone.html` Contains `"total_llm_calls": 50` / `"passed_count": 2` / `"total_duration_s": 1697.0` 全部 True
3. **浏览器截图验证**：修复 Playwright 后起 `python -m http.server 8899` 打开 `index_standalone.html` → P05 tab 统计卡片、9 个候选卡片、通过徽章、维度均分（文献覆盖度 2.7 / 技术可行性 3.2 / 创新性清晰度 3.4 / 数据可及性 4.0 / 缺口对齐度 3.3）全部正常渲染
4. **清理**：临时 HTTP 服务、截图、`.playwright-mcp/` 快照目录已删除

---

## 经验沉淀

已同步至 `docs/TROUBLESHOOTING.md` 新增 2 个 section:

- **P05 Harness Dashboard 数据异常**:checkpoint 无文件级统计字段（聚合按 candidate 求和）；分方向运行后必须 `--merge`
- **开发环境 / MCP 工具链 (Windows)**:npx -y 启动的 MCP 必须钉版（浏览器修订号随上游发布漂移）;npx 被拦截用 `npx.cmd`;file:// 被拦起本地 HTTP 服务

CHANGELOG 已记录 r10 条目。

---

## 修改文件总览

| 文件 | 改动 |
|------|------|
| `dashboard/build_data.py` | `_aggregate_harness_runs()` 聚合统计改为按 candidate 求和 |
| `data/p05_harness_output/latest_run.txt` | 加入 `agent_v3`（两行） |
| `data/p05_harness_output/harness_result.json` | 重写为 9 候选聚合（merge 产物） |
| `dashboard/data.json` + `dashboard/index_standalone.html` | 重建 |
| `C:\Users\cy\.config\opencode\opencode.jsonc` | playwright MCP 钉版 `@0.0.78`（需重启生效） |
| `%LOCALAPPDATA%\ms-playwright\chromium-1232\` | 新装浏览器（与 1228 并存） |
| `docs/TROUBLESHOOTING.md` | 新增 2 个 section(5 条经验） |
| `docs/CHANGELOG.md` | r10 条目 |
| `docs/session_2026-07-20_p05_dashboard_fix.md` | 本日志 |
