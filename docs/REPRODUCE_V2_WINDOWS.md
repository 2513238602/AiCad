# AiCad V2 Windows 复现指南

本文档用于让另一台 Windows 电脑上的 Codex 或开发者，从 GitHub 仓库完整复现当前 V2。

当前仓库状态：

- GitHub 只保留 `V1` 和 `V2` 两个分支。
- 默认分支是 `V2`。
- 当前 V2 以仓库内的 `README.md`、`environment.yml`、`web/package-lock.json` 和本文件作为复现入口。

## 复现范围

可以直接复现：

- 参数化 CAD 生成：瓶身、瓶盖、内塞、刷杆。
- STEP / STL / SVG 输出。
- Web 前端构建与后端 API。
- 高级模式、向导模式、Gallery 页面入口。
- 当前已提交的虚拟展馆 GLB 资产展示。

需要额外外部条件：

- VLM 图片识别：需要 `GLM_API_KEY` 和外网/API 可用。
- 重新生成 Blender 展馆资产：需要本机安装 Blender CLI。
- Epic/Unreal 原始资产再导出：需要本机已有对应授权资产和 Unreal 环境；当前网页展示所需 GLB 已提交，不依赖新机器重新导出。

## 1. 系统前置条件

推荐配置：

- Windows 10/11 64-bit。
- Git。
- Miniconda 或 Miniforge。
- Node.js 20 LTS。若使用 `environment.yml`，Conda 环境也会安装 `nodejs=20`。
- 可选：Blender 4.x，并将 `blender.exe` 加入 `PATH`。

PowerShell 若禁止脚本执行，可以使用一次性绕过：

```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
```

## 2. 拉取仓库

```powershell
git clone https://github.com/2513238602/AiCad.git
cd AiCad
git switch V2
```

正常情况下 `V2` 已是默认分支，`git switch V2` 只是显式确认。

确认远端分支：

```powershell
git branch -a
git ls-remote --heads origin
git ls-remote --symref origin HEAD
```

预期只看到：

```text
refs/heads/V1
refs/heads/V2
HEAD -> refs/heads/V2
```

## 3. 一键初始化

推荐直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_windows.ps1
```

它会执行：

- 根据 `environment.yml` 创建 Conda 环境 `AiCad`。
- 根据 `web/package-lock.json` 执行 `npm.cmd ci`。
- 执行 `npm.cmd run build`。
- 如果没有 `.env`，从 `.env.example` 创建一个空模板。
- 执行 `scripts/smoke_v2.ps1`。

如果环境已经存在但想按仓库刷新：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_windows.ps1 -UpdateEnv
```

如果只想装环境，不跑 smoke：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap_windows.ps1 -SkipSmoke
```

## 4. 手动初始化

如果不使用 bootstrap，可按下面步骤手动执行。

### 4.1 Conda 环境

```powershell
conda env create -f environment.yml
conda activate AiCad
```

如果环境已经存在：

```powershell
conda env update -n AiCad -f environment.yml --prune
conda activate AiCad
```

pip fallback：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-win.txt
```

CadQuery 在 Windows 上通过 Conda 更稳；pip fallback 只作为备选。

### 4.2 前端依赖

PowerShell 下优先使用 `npm.cmd`，避免 `npm.ps1` 被执行策略拦截：

```powershell
cd web
npm.cmd ci
npm.cmd run build
cd ..
```

### 4.3 环境变量

核心 CAD 和展馆预览不需要 API key。

如果要使用 VLM 图片识别：

```powershell
Copy-Item .env.example .env
notepad .env
```

填入：

```text
GLM_API_KEY=你的智谱GLM Key
```

## 5. 启动 V2

推荐：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1
```

默认地址：

```text
http://127.0.0.1:8010/
```

如果端口占用：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start.ps1 -Port 8020
```

## 6. 验收 smoke test

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_v2.ps1
```

它会检查：

- Python 是否是 3.11。
- CadQuery / OCP / numpy / cv2 / PIL 等核心依赖是否可导入。
- CadQuery STEP 导出是否正常。
- 四组件是否都能生成 STEP/STL/SVG。
- 展馆 GLB 资产是否存在。
- 前端是否能生产构建。
- 后端 `/api/schema` 与 `/api/generate` 是否返回有效 JSON。

可选项：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_v2.ps1 -SkipFrontendBuild
powershell -ExecutionPolicy Bypass -File scripts/smoke_v2.ps1 -SkipWebApi
```

## 7. 常见问题

### 默认 python 不是 3.11

症状：

```text
Expected Python 3.11.x
No module named 'cadquery'
```

解决：

```powershell
conda activate AiCad
python --version
```

或者直接让脚本解析 Conda 环境：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke_v2.ps1 -EnvName AiCad
```

### npm.ps1 被禁止

症状：

```text
npm.ps1 cannot be loaded because running scripts is disabled
```

解决：

```powershell
npm.cmd ci
npm.cmd run build
```

仓库脚本已优先查找 `npm.cmd`。

### Blender 找不到

这不会影响当前 V2 网页端展馆展示，因为 GLB 资产已经提交。

只有重新生成展馆资产时需要：

```powershell
blender --version
```

若失败，请安装 Blender 并加入 `PATH`，或放在本地 `tools/blender/` 后自行加入 PATH。

### VLM 功能不可用

核心 CAD 不受影响。VLM 需要：

```text
GLM_API_KEY=...
```

并且网络可访问智谱 GLM API。

## 8. 复现完成标准

满足以下条件即可认为 V2 在新 Windows 电脑上复现成功：

- `scripts/smoke_v2.ps1` 无 FAIL。
- `web/dist/index.html` 存在。
- `artifacts/smoke_v2/` 下出现四组件生成结果。
- 打开 `http://127.0.0.1:8010/` 后，高级模式、向导模式、Gallery 和虚拟展馆入口可见。

