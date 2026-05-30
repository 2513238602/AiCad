[English](README_EN.md) | **中文**

# AiCad V2 - 化妆品包材 CAD 自动生成与预览系统

> V2 分支：参数化工业 CAD + 图像/VLM 自动管线 + Gallery/虚拟展馆预览。  
> V1 保留在 `v1.0` tag / `master` 分支；V2 保留在 `v2` 分支。

---

## V2 定位

AiCad V2 是面向化妆品包材，尤其是唇釉瓶组件的 CAD 自动生成原型。它在 V1 的参数化 CAD 生成能力上，继续加入了自动管线、图像/VLM 外观识别实验、异形/轮廓建模探索、Gallery 与虚拟展馆预览。

V2 的目标不是最终形态，而是为 V3 打底：

```text
V2：参数 / 图片分析 → 参数化 CAD → STEP/STL/SVG → 预览与展馆
V3：创意图 → AIGC 3D 外观壳 → AiCad 重建生产 CAD → STEP/工程图/装配检查
```

---

## 相比 V1 的主要变化

V1 的核心是参数化唇釉瓶 CAD 生成。V2 在此基础上扩展了这些能力：

- 新增向导模式，与高级模式并存。
- 新增 VLM/CV 自动管线，用于从参考图提取外观、比例、装饰和参数候选。
- 新增 Gallery 相关流程，用于预构建和展示参考图库生成结果。
- 新增虚拟展馆入口和 Three.js 画廊走廊预览。
- 新增 profile/spline、异形瓶盖、mesh 修复、拓扑检查等建模实验。
- 增强工程图生成模块，拆出 `primitives` / `projection` 等绘图基础能力。
- 增强装配、QC、自动修复、渲染材质元数据等核心模块。
- 保留 V1 的四组件 CAD 生成、STEP/STL/SVG 输出和装配校验基础能力。

---

## 当前可体验功能

### 1. 参数化四组件 CAD

支持唇釉瓶四组件：

- 瓶身 `Bottle`
- 瓶盖 `Cap`
- 内塞 `Wiper`
- 刷杆 `Wand`

每个组件可通过 preset 或手动参数生成，并导出：

- STEP：用于 CAD 软件和后续生产沟通
- STL：用于网页预览和快速检查
- SVG：工程图输出

### 2. 高级模式与向导模式

- 高级模式：完整参数面板，适合直接调参。
- 向导模式：按产品、组件、核心参数、方案选择、精调和生成拆分流程。

### 3. 自动管线

V2 包含图像/VLM/CV 自动管线雏形：

- 参考图分类
- 外观特征识别
- 轮廓、比例、锥度等候选参数提取
- Gallery-ready 参数结果输出
- 与现有 CadQuery 生成器连接

相关入口：

- `scripts/auto_pipeline.py`
- `scripts/prebuild_gallery.py`
- `scripts/rebuild_gallery.py`
- `src/core/vlm_extract.py`
- `src/core/render_materials.py`

### 4. Gallery 与虚拟展馆

V2 包含 Gallery 页面与虚拟展馆入口：

- Gallery 页面：展示预构建或参考生成结果。
- 虚拟展馆：Three.js 走廊式画廊预览，支持自由视角移动。
- 轻量运行资产已保留在 `web/public/assets/`。

相关入口：

- `web/src/components/gallery/GalleryPage.vue`
- `web/src/components/showroom/ShowroomPage.vue`
- `web/public/assets/showroom-gallery/`
- `web/public/assets/showroom-unreal/`

### 5. 3D 查看器与装配检查

V2 保留并扩展了 3D 预览能力：

- STL 加载和查看
- 截面检查
- 装配体位置检查
- 组件状态管理
- 拖拽/交互能力实验

---

## 技术栈

| 层级 | 技术 |
|------|------|
| CAD 内核 | Python 3.11 + CadQuery 2.6.1 + OpenCASCADE |
| 后端服务 | Python HTTP server，默认端口 `8010` |
| 前端 | Vue 3 + TypeScript + Pinia + Element Plus |
| 3D 渲染 | Three.js 0.160 |
| 输出 | STEP / STL / SVG / JSON |
| 图像自动管线 | OpenCV + VLM 接口适配 + 参数映射 |
| 展馆资产 | GLB + Three.js runtime |

---

## 快速开始

### 1. Python 环境

推荐使用 Conda：

```bash
conda create -n AiCad python=3.11 -y
conda activate AiCad
pip install cadquery==2.6.1 aiohttp numpy ezdxf matplotlib opencv-python pillow requests
```

### 2. 前端依赖

```bash
cd web
npm install
npm run build
cd ..
```

### 3. 启动 Web

```bash
python scripts/web_server.py --host 127.0.0.1 --port 8010
```

打开：

```text
http://127.0.0.1:8010/
```

Windows 下也可以使用：

```powershell
.\scripts\start.ps1
```

### 4. CLI 生成测试

```bash
python scripts/generate.py --product lip_gloss --component bottle --preset bottle_standard_5ml --outroot artifacts/v2_smoke
```

生成结果会落在 `artifacts/`，该目录默认不提交到 Git。

---

## Blender 说明

V2 的部分展馆构建、资产处理和截图流程会用到 Blender CLI。仓库不会提交本地 Blender 二进制，因为它体积过大。

可选方案：

- 将 Blender 加入系统 `PATH`
- 或本地放置到 `tools/blender/`

`tools/blender/` 和 `tools/downloads/` 已被 `.gitignore` 忽略。

---

## 项目结构

```text
AiCad/
├── src/
│   ├── core/
│   │   ├── modeler.py              # CadQuery 几何建模
│   │   ├── assembly.py             # 装配定位与检查
│   │   ├── auto_repair.py          # 自动修复实验
│   │   ├── mesh_cap.py             # 异形/mesh 瓶盖实验
│   │   ├── vlm_extract.py          # VLM 图像参数提取
│   │   └── render_materials.py     # 渲染材质元数据
│   └── products/lip_gloss/
│       ├── components/             # bottle/cap/wiper/wand
│       ├── derived_params.py
│       ├── constraints.py
│       └── drawings/               # SVG 工程图
├── scripts/
│   ├── web_server.py
│   ├── generate.py
│   ├── auto_pipeline.py
│   ├── prebuild_gallery.py
│   ├── create_gallery_shell.py
│   └── showroom_display_modules.py
├── web/
│   ├── src/components/
│   │   ├── wizard/
│   │   ├── gallery/
│   │   ├── showroom/
│   │   └── viewer/
│   └── public/assets/
├── report/
│   ├── V2/
│   └── V3/
└── docs/
```

---

## V2 发布说明

详见：

- [docs/V2_RELEASE_NOTES.md](docs/V2_RELEASE_NOTES.md)
- [report/V2/README.md](report/V2/README.md)

V3 方案详见：

- [report/V3/AiCad_V3_AIGC_to_Production_CAD.md](report/V3/AiCad_V3_AIGC_to_Production_CAD.md)

---

## 已验证项

V2 发布前已验证：

- `npm run build` 通过
- Python 核心入口语法检查通过
- CLI 生成可产出 STEP/STL/SVG
- Web API `/api/schema` 与 `/api/generate` 返回 JSON，生成结果 `ok: true`

---

## 版本关系

```text
V1: tag v1.0 / branch master
V2: branch v2
dev: 历史开发分支
V3: 下一阶段规划，尚未作为独立开发分支发布
```

---

## 许可

私有项目，保留所有权利。
