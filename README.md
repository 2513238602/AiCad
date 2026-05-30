[English](README_EN.md) | **中文**

# AiCad - 化妆品包装参数化 CAD 生成器

> 参数化唇釉瓶装配体 CAD 系统 —— 从参数到可制造 STEP 文件，秒级生成。

---

## 项目简介

AiCad 是一个面向化妆品包装工程师的 Web 参数化 CAD 生成平台。系统可自动生成唇釉瓶完整装配体（瓶盖、瓶身、内塞、刷杆），输出制造级精度的 **STEP**、**STL** 和 **工程图 (SVG)**。

**核心价值**：工程师无需在 SolidWorks/Fusion360 中手动建模，只需在可视化界面调整参数，即可获得带螺纹、密封结构、装配配合的生产级 CAD 文件 —— 全部自动校验。

## 当前版本：V2

V2 是当前可运行分支，目标是完整保留现有体验：

- 高级模式 / 向导模式参数化生成
- 唇釉瓶四组件 CAD：瓶盖、瓶身、内塞、刷杆
- STEP / STL / SVG 工程图输出
- 3D 预览、装配检查、截面查看
- VLM/CV 自动管线雏形
- Gallery 与虚拟展馆入口

V2 的发布说明见 [docs/V2_RELEASE_NOTES.md](docs/V2_RELEASE_NOTES.md)。

## V3 方向

V3 的目标是把 AIGC 的复杂外观生成能力接入 AiCad，并由 AiCad 重建为可用于开模沟通的工业 CAD：

```text
Codex / GPT Image 创意图
→ AIGC 生成 3D 外观 shell
→ AiCad 分析并生成 AppearanceIR
→ CadQuery/OpenCASCADE 重建生产 CAD
→ STEP / STL / 工程图 / 装配与可制造性检查
```

V3 完整方案见 [report/V3/AiCad_V3_AIGC_to_Production_CAD.md](report/V3/AiCad_V3_AIGC_to_Production_CAD.md)。

### 主界面

![主界面](docs/images/main-ui.png)

*参数面板支持核心/派生参数体系。派生参数（标记"联动"）随核心参数自动计算；跨组件约束（标记"受约束"）确保装配兼容性。*

---

## 功能特性

### 参数化四组件装配

智能参数管理，生成完整唇釉瓶装配体：

- **瓶盖 (Cap)**：外壳、防滑纹（竖筋/滚花）、圆顶/平顶、内腔 + 螺纹
- **瓶身 (Bottle)**：瓶体/肩部/颈部分段、外螺纹、内腔、瓶底处理
- **内塞 (Wiper)**：密封膜片、中心孔、加强筋、法兰
- **刷杆 (Wand)**：涂抹器盖体 + 杆 + 刷头（鹿脚/硅胶刮/纤维）、气密环

### 3D 装配查看器

交互式 Three.js 查看器，支持完整装配可视化：

![3D 装配视图](docs/images/3d-assembly.png)

*四组件装配体线框模式 —— 可见螺纹、防滑纹和内部结构。*

### 截面检查

内置截面工具，检查内部配合与间隙：

![3D 截面视图](docs/images/3d-section.png)

*截面展示内部结构：螺纹啮合、气密环定位、刷杆-瓶盖间隙。*

### 工程图

自动生成 SVG 工程图，标注制造尺寸：

![工程图](docs/images/engineering-drawing.png)

*正视图、A-A 剖视图和俯视图，标注所有关键尺寸。*

---

## 技术亮点

| 特性 | 说明 |
|------|------|
| **核心/派生参数** | 核心参数由用户控制；派生参数自动计算（如：内径 = 外径 - 1.6mm） |
| **跨组件约束** | 生成一个组件会约束其他组件（如：瓶盖生成后锁定刷杆外径） |
| **优先级仲裁** | 约束冲突按优先级解决：瓶盖(20) > 瓶身(15) > 刷杆(10) > 内塞(5) |
| **10项质量检查** | 装配干涉检测、尺寸校验、制造可行性验证 |
| **制造感知** | 最小拔模角 (0.3-0.5°)、最小壁厚 (0.8mm)、可配置螺距的螺纹 |
| **优雅降级** | 非关键装饰特征可降级处理；关键几何体严格失败 |
| **双语界面** | 中英文界面，运行时一键切换 |

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **CAD 引擎** | Python 3.11 + CadQuery 2.6.1 (OpenCASCADE 内核) |
| **Web 服务器** | aiohttp (异步 HTTP, 端口 8010) |
| **前端** | Vue 3 + TypeScript + Pinia + Element Plus |
| **3D 查看器** | Three.js 0.160.0 + TransformControls |
| **构建工具** | Vite 6.3 |
| **输出格式** | STEP, STL, SVG |

---

## 快速开始

### 环境要求

- Python 3.11+（推荐 Conda）
- Node.js 18+

### 安装与启动

```bash
# 1. 创建 Conda 环境
conda create -n AiCad python=3.11 -y
conda activate AiCad

# 2. 安装 Python 依赖
pip install cadquery==2.6.1 aiohttp numpy ezdxf matplotlib

# 3. 安装前端依赖
cd web && npm install && cd ..

# 4. 构建前端
cd web && npm run build && cd ..

# 5. 启动服务
python scripts/web_server.py
```

浏览器打开 http://localhost:8010

### 使用方法

1. 选择**产品类型**（唇釉瓶）和**组件**（瓶盖/瓶身/内塞/刷杆）
2. 选择**风格预设**或手动调参
3. 点击 **"生成 STEP + 3D预览 + 工程图"**
4. 下载 STEP/STL 文件，或查看 3D 预览和工程图
5. 生成全部 4 个组件可查看完整装配体和干涉检测结果

---

## 项目结构

```
AiCad/
├── src/
│   ├── core/                        # 核心引擎
│   │   ├── modeler.py               # CadQuery 几何建模器 (1100+ 行)
│   │   ├── param_system.py          # 参数分类框架
│   │   ├── fit_constraints.py       # 装配约束系统
│   │   ├── component_state.py       # 跨组件状态管理器
│   │   ├── interpreter.py           # 参数校验与归一化
│   │   └── assembly.py              # 装配定位与质检
│   └── products/
│       └── lip_gloss/
│           ├── components/          # 瓶盖、瓶身、内塞、刷杆定义
│           ├── constraints.py       # 配合约束规则
│           ├── derived_params.py    # 派生规则 + 跨组件规则
│           └── drawings/            # SVG 工程图生成器
├── web/
│   └── src/
│       ├── components/              # Vue 组件 (查看器、参数、布局)
│       ├── stores/                  # Pinia 状态管理
│       ├── api/                     # 后端 API 客户端
│       ├── i18n/                    # 中英文翻译
│       └── composables/             # 可复用逻辑
├── scripts/
│   ├── web_server.py                # HTTP 服务入口
│   └── generate.py                  # CLI 生成工具
├── tests/                           # 测试套件
└── docs/                            # 文档与截图
```

---

## API 接口

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/schema` | 产品/组件/预设定义 |
| GET | `/api/derived_rules` | 派生规则元数据 |
| POST | `/api/generate` | 生成组件（返回 STEP/STL/SVG 链接 + 质检结果） |
| GET | `/api/assembly` | 装配位置 + 干涉报告 |
| GET | `/api/constraints/{comp}` | 跨组件约束 |
| POST | `/api/generated/{comp}` | 存储已生成组件状态 |

---

## 许可

私有项目，保留所有权利。
