# CADMVP WSL to Windows 迁移指南

本文档记录如何将 CADMVP 项目从 WSL(Ubuntu) 迁移到 Windows 原生环境运行。

## 迁移概览

| 项目 | WSL 路径 | Windows 路径 |
|------|---------|-------------|
| 项目根目录 | `/home/user/projects/cadmvp` | `G:\AiCad` |
| 源代码 | `src/cadmvp/` | `src/cadmvp/` (相同) |
| 脚本 | `scripts/run.sh` | `scripts/run.ps1` |
| Web 服务 | `scripts/run_web.sh` | `scripts/run_web.ps1` |
| 输出目录 | `artifacts/` | `artifacts/` (相同) |
| Python 环境 | conda / venv | `.venv` (pip) |

## 目录结构

```
G:\AiCad\
├── .venv/                      # Python 3.11 虚拟环境
├── .vscode/
│   └── settings.json           # VS Code 配置
├── artifacts/
│   ├── cli/                    # CLI 生成输出
│   ├── webui/                  # Web UI 生成输出
│   └── selftest/               # 环境自检输出
├── docs/
│   ├── WINDOWS_SETUP.md        # 环境配置文档
│   └── WINDOWS_MIGRATION.md    # 本文档
├── scripts/
│   ├── generate.py             # 生成入口 (从 WSL 复制)
│   ├── web_server.py           # Web 服务器 (从 WSL 复制)
│   ├── selftest_cadquery.py    # cadquery 自检
│   ├── run.ps1                 # Windows 主入口脚本
│   └── run_web.ps1             # Windows Web 入口脚本
├── src/
│   └── cadmvp/
│       ├── __init__.py
│       ├── core/
│       │   ├── interpreter.py  # 参数解释器
│       │   ├── modeler.py      # CAD 建模器
│       │   └── util.py
│       ├── bottle/
│       │   └── components/
│       │       ├── cap_component.py  # 瓶盖组件
│       │       └── registry.py       # 组件注册表
│       └── viz/
│           ├── svg.py
│           ├── bottle_sheet.py
│           └── cap_sheet.py    # 工程图导出
├── web/
│   └── index.html              # Web UI 前端
├── requirements-win.txt        # Windows 依赖
└── requirements-wsl.txt        # WSL 依赖 (参考)
```

## 常见迁移坑点

### 1. 路径分隔符

**问题**: WSL 使用 `/`，Windows 使用 `\`

**解决**: 代码中已使用 `pathlib.Path`，自动处理路径分隔符。

```python
# 正确做法 (已实现)
from pathlib import Path
output_dir = Path("artifacts") / "cli" / "output"

# 避免
output_dir = "artifacts/cli/output"  # 可能有问题
```

### 2. 编码问题

**问题**: WSL 默认 UTF-8，Windows 命令行可能使用 GBK

**解决**:
- 所有文件读写已指定 `encoding="utf-8"`
- PowerShell 输出中文可能乱码，但不影响功能

```python
# 正确做法 (已实现)
path.write_text(content, encoding="utf-8")
path.read_text(encoding="utf-8")
```

### 3. 换行符 (CRLF vs LF)

**问题**: Git 在 Windows 上可能自动转换换行符

**解决**: 配置 Git 保持 LF

```bash
git config --global core.autocrlf input
```

### 4. Shell 脚本不可用

**问题**: `run.sh` 在 Windows 无法直接运行

**解决**: 已创建等效的 PowerShell 脚本

| WSL | Windows |
|-----|---------|
| `./scripts/run.sh cap cap_full_detail_demo` | `.\scripts\run.ps1 cap cap_full_detail_demo` |
| `./scripts/run_web.sh` | `.\scripts\run_web.ps1` |

### 5. Python 环境差异

**问题**: WSL 使用 conda，Windows 使用 pip + venv

**解决**:
- Windows 使用 `.venv` 虚拟环境
- cadquery 通过 pip 安装 (使用清华镜像)
- 核心功能完全兼容

## 从 WSL 同步代码

### 方法 1: 直接访问 WSL 文件系统

```powershell
# Windows 可以通过 \\wsl.localhost\ 访问 WSL 文件
Copy-Item -Recurse "\\wsl.localhost\Ubuntu-24.04\home\user\projects\cadmvp\src" "G:\AiCad\"
```

### 方法 2: 在 WSL 中复制到 Windows

```bash
# 在 WSL 中执行
cp -r ~/projects/cadmvp/src /mnt/g/AiCad/
cp -r ~/projects/cadmvp/scripts/*.py /mnt/g/AiCad/scripts/
cp -r ~/projects/cadmvp/web /mnt/g/AiCad/
```

### 方法 3: 使用 Git

```powershell
# 在 Windows 中
cd G:\AiCad
git init
git remote add origin <your-repo-url>
git pull origin main
```

### 方法 4: 使用 robocopy (Windows)

```powershell
robocopy "\\wsl.localhost\Ubuntu-24.04\home\user\projects\cadmvp" "G:\AiCad" /E /XD .venv __pycache__ .git
```

## 验收测试

### CLI 生成测试

```powershell
# 激活环境
.\.venv\Scripts\Activate.ps1

# 运行 cap 生成
.\scripts\run.ps1 cap cap_full_detail_demo

# 或直接调用
.\.venv\Scripts\python.exe scripts/generate.py --component cap --preset cap_full_detail_demo
```

**预期输出**:
- `artifacts/cli/<timestamp>__cap__cap_full_detail_demo/cap.step` (约 3MB)
- `artifacts/cli/<timestamp>__cap__cap_full_detail_demo/drawings/cap_sheet.svg` (约 7KB)
- JSON 输出包含 `"ok": true`

### Web UI 测试

```powershell
.\scripts\run_web.ps1
```

打开 http://127.0.0.1:8010 应能：
1. 看到参数配置界面
2. 选择预设并生成
3. 下载 STEP 和 SVG 文件

## QC 验证

CADMVP 包含严格的参数校验 (QC)：

1. **壁厚一致性**: `wall ≈ (OD - ID) / 2`
2. **顶厚一致性**: `top ≈ H - cavity`
3. **锥度范围**: `OD1 <= OD0 且 OD1 >= 0.70*OD0`
4. **竖筋安全**: `rib_depth <= wall - 0.3`
5. **螺纹安全**: 长度不超过内腔，牙深不穿透壁厚
6. **密封塞安全**: 尺寸可装入且不顶到开口

如果参数不满足硬约束，将返回 `"ok": false` 并**拒绝导出** STEP/SVG。

## 已知限制

1. **字体**: SVG 工程图使用 Arial/Microsoft YaHei/SimHei，Windows 系统通常已有
2. **并发**: Web 服务器使用 ThreadingHTTPServer，适合开发测试
3. **大模型**: 复杂特征 (如滚花) 可能耗时较长

## 更新日志

- **2026-02-04**: 完成从 WSL 到 Windows 的迁移
  - 复制核心代码: src/cadmvp/, scripts/, web/
  - 创建 PowerShell 入口脚本: run.ps1, run_web.ps1
  - 验证 cap_full_detail_demo 生成成功
  - STEP: 2,979,958 bytes
  - SVG: 6,764 bytes
