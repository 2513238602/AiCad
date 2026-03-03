# CADMVP Windows 开发环境配置指南

本文档记录如何在 Windows 上配置 CADMVP 开发环境，以便从 WSL(Ubuntu) 同步项目代码后可以立即运行。

## 环境信息

| 项目 | 版本 |
|------|------|
| Windows | 10.0.26200.7623 |
| PowerShell | 5.1+ |
| Python | 3.11.9 |
| cadquery | 2.6.1 |
| cadquery-ocp | 7.8.1.1.post1 |
| pip | 26.0 |

## 快速开始

如果环境已配置好，直接运行：

```powershell
# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 运行自检
python scripts/selftest_cadquery.py

# 运行项目（需先同步代码）
.\scripts\run.ps1
```

---

## 完整安装步骤

### 第 1 步：检测环境

打开 PowerShell，运行以下命令检测已有工具：

```powershell
# 检查 Windows 版本
[System.Environment]::OSVersion.VersionString

# 检查 winget
winget --version

# 检查 Git
git --version

# 检查 Python Launcher
py --list
```

### 第 2 步：安装 Python 3.11

#### 方法 A：使用 winget（推荐）

```powershell
winget install Python.Python.3.11 --source winget --accept-source-agreements --accept-package-agreements
```

安装后验证：

```powershell
py --list
# 应显示: -V:3.11  Python 3.11 (64-bit)
```

#### 方法 B：手动安装

1. 下载: https://www.python.org/downloads/release/python-3119/
2. 选择 "Windows installer (64-bit)"
3. 安装时勾选 "Add Python to PATH" 和 "Install py launcher"

### 第 3 步：创建虚拟环境

```powershell
# 切换到项目目录
cd G:\AiCad

# 使用 Python 3.11 创建 venv
py -3.11 -m venv .venv

# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 升级 pip（使用清华镜像解决网络问题）
python -m pip install --upgrade pip setuptools wheel -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 第 4 步：安装 cadquery

```powershell
# 确保虚拟环境已激活
pip install cadquery -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 第 5 步：验证安装

```powershell
# 运行自检脚本
python scripts/selftest_cadquery.py

# 预期输出：
# - cadquery 版本: 2.6.1
# - OCP 导入成功
# - STEP 文件导出成功
# - artifacts/selftest/box.step 生成
```

---

## 常见问题与 Fallback

### 问题 1：pip 安装 cadquery 失败 (网络/SSL 错误)

**症状**：
```
SSLError: [SSL: UNEXPECTED_EOF_WHILE_READING]
ProxyError: Cannot connect to proxy
```

**解决方案**：使用国内镜像

```powershell
pip install cadquery -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn
```

其他可用镜像：
- 阿里云: https://mirrors.aliyun.com/pypi/simple/
- 中科大: https://pypi.mirrors.ustc.edu.cn/simple/

### 问题 2：pip 安装 cadquery 失败 (依赖编译错误)

**Fallback 方案：使用 Conda**

```powershell
# 1. 安装 Miniconda
winget install Anaconda.Miniconda3 --source winget

# 2. 重启 PowerShell，然后创建环境
conda create -n cadmvp python=3.11 -y
conda activate cadmvp

# 3. 从 conda-forge 安装 cadquery
conda install -c conda-forge cadquery -y

# 4. 验证
python -c "import cadquery; print(cadquery.__version__)"
```

**注意**：如果使用 Conda 方案，需要修改 `.vscode/settings.json`：

```json
{
    "python.defaultInterpreterPath": "C:/Users/<用户名>/miniconda3/envs/cadmvp/python.exe"
}
```

### 问题 3：PowerShell 执行策略限制

**症状**：
```
.ps1 cannot be loaded because running scripts is disabled on this system
```

**解决方案**：

```powershell
# 方案 A：仅当前用户（无需管理员）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 方案 B：仅当前会话
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
```

### 问题 4：winget 不可用

如果 winget 不可用，手动安装所需软件：

1. **Python 3.11**: https://www.python.org/downloads/release/python-3119/
2. **Git**: https://git-scm.com/download/win
3. **Miniconda**: https://docs.conda.io/en/latest/miniconda.html

---

## 从 WSL 同步代码

环境配置完成后，从 WSL 同步项目代码：

### 方法 1：直接复制

```bash
# 在 WSL 中执行
cp -r /path/to/cadmvp/* /mnt/g/AiCad/
```

### 方法 2：使用 rsync（推荐）

```bash
# 在 WSL 中执行
rsync -av --exclude '.venv' --exclude '__pycache__' --exclude '.git' \
    /path/to/cadmvp/ /mnt/g/AiCad/
```

### 方法 3：使用 Git

```powershell
# 在 Windows PowerShell 中执行
cd G:\AiCad
git clone <your-repo-url> .
```

---

## 项目入口脚本

### run.ps1

主要的生成/构建入口：

```powershell
# 运行全部
.\scripts\run.ps1

# 仅生成
.\scripts\run.ps1 -Target generate

# 仅构建
.\scripts\run.ps1 -Target build

# 帮助
.\scripts\run.ps1 -Target help
```

### run_web.ps1

Web 服务器入口：

```powershell
# 默认端口 5000
.\scripts\run_web.ps1

# 自定义端口
.\scripts\run_web.ps1 -Port 8080
```

---

## VS Code 配置

已自动生成 `.vscode/settings.json`，配置了：

- Python 解释器路径指向 `.venv`
- 启用 Python 类型检查
- 终端默认使用 PowerShell

打开 VS Code 后，按 `Ctrl+Shift+P`，选择 "Python: Select Interpreter"，确认选择的是 `.venv` 中的 Python。

---

## 文件结构

```
G:\AiCad\
├── .venv/                      # Python 虚拟环境
├── .vscode/
│   └── settings.json           # VS Code 配置
├── artifacts/
│   └── selftest/
│       └── box.step            # 自检生成的 STEP 文件
├── docs/
│   └── WINDOWS_SETUP.md        # 本文档
├── scripts/
│   ├── selftest_cadquery.py    # cadquery 自检脚本
│   ├── run.ps1                 # Windows 主入口脚本
│   └── run_web.ps1             # Web 服务器入口脚本
└── requirements-win.txt        # Windows 依赖文件
```

---

## 验收命令

快速验证环境是否配置正确：

```powershell
# 1. 检查 Python 版本
.\.venv\Scripts\python.exe --version
# 预期: Python 3.11.9

# 2. 检查 cadquery
.\.venv\Scripts\python.exe -c "import cadquery; print(f'cadquery {cadquery.__version__}')"
# 预期: cadquery 2.6.1

# 3. 运行自检
.\.venv\Scripts\python.exe scripts/selftest_cadquery.py
# 预期: 所有测试通过，生成 artifacts/selftest/box.step

# 4. 检查 STEP 文件
Test-Path artifacts/selftest/box.step
# 预期: True
```

---

## 更新日志

- **2026-02-04**: 初始配置完成
  - Python 3.11.9 via winget
  - cadquery 2.6.1 via pip (清华镜像)
  - 自检通过，box.step 生成成功
