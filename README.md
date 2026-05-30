# AiCad V1 - 唇釉瓶参数化 CAD 生成器

> V1 分支：面向唇釉瓶四组件的参数化工业 CAD 原型。  
> 本分支固定为 AiCad V1；V2 请查看 `V2` 分支。

---

## V1 定位

AiCad V1 是项目的第一个可运行版本，目标是验证“用参数化方式自动生成可制造 CAD”的基础可行性。

V1 聚焦于唇釉瓶包装组件：

- 瓶身 `Bottle`
- 瓶盖 `Cap`
- 内塞 `Wiper`
- 刷杆 `Wand`

核心输出：

- STEP：用于 CAD 软件打开和生产沟通
- STL：用于 3D 预览
- SVG：用于工程图查看

V1 的重点是 CAD 结构能力，而不是复杂外观生成。

---

## V1 核心能力

### 1. 参数化建模

通过产品、组件、preset 和参数生成 CAD 模型。核心参数包括：

- 外径、高度、锥度
- 瓶口和螺纹规格
- 内腔、壁厚、底厚
- 刷杆、内塞和瓶盖相关装配尺寸

### 2. 四组件装配基础

V1 建立了唇釉瓶四组件的基础结构：

- `cap`
- `bottle`
- `wiper`
- `wand`

并包含跨组件约束和装配检查雏形。

### 3. 工程输出

每个组件可生成：

- `.step`
- `.stl`
- `.svg` 工程图
- 生成参数和 QC 结果

### 4. Web 界面

V1 包含一个基础 Web UI：

- 产品/组件选择
- 参数面板
- 生成按钮
- 输出结果区
- 3D 查看器
- 中英文界面

---

## 技术栈

| 层级 | 技术 |
|------|------|
| CAD 内核 | Python 3.11 + CadQuery 2.6.1 + OpenCASCADE |
| 后端 | `scripts/web_server.py` |
| 前端 | Vue 3 + TypeScript + Pinia + Element Plus |
| 3D 预览 | Three.js |
| 输出 | STEP / STL / SVG / JSON |

---

## 快速开始

### Python 环境

```bash
conda create -n AiCad python=3.11 -y
conda activate AiCad
pip install cadquery==2.6.1 aiohttp numpy ezdxf matplotlib
```

### 前端依赖

```bash
cd web
npm install
npm run build
cd ..
```

### 启动服务

```bash
python scripts/web_server.py --host 127.0.0.1 --port 8010
```

打开：

```text
http://127.0.0.1:8010/
```

Windows 下也可以使用：

```powershell
.\scripts\run_web.ps1
```

### CLI 生成示例

```bash
python scripts/generate.py --product lip_gloss --component cap --preset cap_full_detail_demo --outroot artifacts/cli
```

---

## 项目结构

```text
AiCad/
├── scripts/
│   ├── generate.py
│   ├── web_server.py
│   ├── run.ps1
│   ├── run_web.ps1
│   └── selftest_cadquery.py
├── src/
│   ├── core/
│   │   ├── modeler.py
│   │   ├── param_system.py
│   │   ├── interpreter.py
│   │   ├── fit_constraints.py
│   │   ├── component_state.py
│   │   └── assembly.py
│   └── products/lip_gloss/
│       ├── components/
│       ├── constraints.py
│       ├── derived_params.py
│       └── drawings/
├── web/
│   └── src/
├── tests/
├── docs/
└── report/
```

---

## V1 边界

V1 不包含：

- VLM/CV 自动图像管线
- Gallery
- 虚拟展馆
- 异形外观/mesh 重建实验
- V3 的 AIGC 外观壳到生产 CAD 工作流

这些能力属于 V2 或 V3 方向。

---

## 版本关系

```text
V1: 当前分支
V2: V2 分支
```

---

## 许可

私有项目，保留所有权利。
