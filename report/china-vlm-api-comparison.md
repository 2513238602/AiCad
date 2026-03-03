# 中国企业 VLM API 服务对比报告

> 日期：2026-03-03
> 目标：为 AiCad 项目选择最适合的付费 VLM API，用于从产品图片提取几何参数
> 场景：用户上传唇釉瓶照片 → VLM 提取比例/分类 → 生成 STEP 模型

---

## 1. 总览定价表（按单价从低到高排序）

> 单位：RMB / 百万 tokens（M tokens）

| 服务商 | 推荐模型 | 输入价格 | 输出价格 | 免费额度 | OpenAI 兼容 |
|--------|---------|---------|---------|---------|------------|
| **智谱 AI** | GLM-4V-Flash | **免费** | **免费** | 无限(限速) | 是 |
| **硅基流动** | GLM-4.1V-9B-Thinking | **免费** | **免费** | 无限(限速) | 是 |
| **硅基流动** | PaddleOCR-VL | **免费** | **免费** | 无限(限速) | 是 |
| 智谱 AI | GLM-4.6V-FlashX | 0.15 | 1.50 | 20M tokens | 是 |
| **硅基流动** | Qwen2.5-VL-7B | **0.35** | **0.35** | 有 | 是 |
| 硅基流动 | Qwen3-VL-8B | 0.50 | 2.00 | 有 | 是 |
| **火山引擎** | doubao-1.5-vision-pro | **0.80** | **2.00** | 500K tokens | 是 |
| 百度 | ERNIE-4.5-Turbo-VL | ~0.80 | ~3.20 | 免费基础模型 | 部分 |
| 硅基流动 | DeepSeek-VL2 | 0.99 | 0.99 | 无 | 是 |
| **智谱 AI** | GLM-4.6V | 1.00 | 3.00 | 20M tokens | 是 |
| MiniMax | MiniMax-VL-01 | 1.00 | 8.00 | 试用额度 | 是 |
| 硅基流动 | Qwen3-VL-32B | 1.00 | 4.00 | 无 | 是 |
| **阿里云** | qwen-vl-plus | 1.50 | ~4.50 | 1M tokens/模型 | 是 |
| 阶跃星辰 | step-1o-turbo-vision | 2.50 | 8.00 | 试用额度 | 是 |
| **阿里云** | qwen-vl-max | 3.00 | ~9.00 | 1M tokens/模型 | 是 |
| 腾讯云 | hunyuan-turbos-vision | 3.00 | 9.00 | 1M tokens | 是 |
| 零一万物 | Yi-Vision | ~6.00 | ~6.00 | 试用额度 | 是 |
| 月之暗面 | moonshot-v1-8k-vision | 12.00 | 12.00 | 少量 | 是 |
| 讯飞 | Spark 4.0 Ultra | ~21.00 | ~21.00 | 100M(Max) | 否 |

---

## 2. 各服务商详细分析

### 2.1 硅基流动 SiliconFlow（聚合平台）

**定位：** 模型聚合平台，单一 API 访问多个开源 VLM

| 模型 | 输入(RMB/M) | 输出(RMB/M) | 备注 |
|------|-----------|-----------|------|
| Qwen2.5-VL-7B-Instruct | 0.35 | 0.35 | 性价比之王 |
| Qwen3-VL-8B-Instruct | 0.50 | 2.00 | 最新一代 |
| DeepSeek-VL2 | 0.99 | 0.99 | MoE 架构 |
| Qwen2.5-VL-72B-Instruct | 4.13 | 4.13 | 旗舰质量 |
| GLM-4.1V-9B-Thinking | 免费 | 免费 | 免费视觉模型 |

**优势：** OpenAI 兼容 API、多模型 A/B 测试、无供应商锁定、价格透明
**适合：** 初创团队快速试错

### 2.2 智谱 AI（GLM 系列）

**定位：** 国内最慷慨的免费 VLM 额度

| 模型 | 输入(RMB/M) | 输出(RMB/M) | 上下文 | 备注 |
|------|-----------|-----------|--------|------|
| GLM-4V-Flash | **免费** | **免费** | 128K | 永久免费，限速 |
| GLM-4.6V-FlashX | 0.15 | 1.50 | 128K | 快速高性价比 |
| GLM-4.6V | 1.00 | 3.00 | 128K | 旗舰 |

**优势：** 免费额度最好、OpenAI 兼容、CogVLM 系列空间理解强
**适合：** 原型开发阶段零成本验证

### 2.3 火山引擎（豆包 / ByteDance）

**定位：** 字节跳动旗下，视觉理解能力强

| 模型 | 输入(RMB/M) | 输出(RMB/M) | 上下文 | 备注 |
|------|-----------|-----------|--------|------|
| doubao-1.5-vision-pro-32k | 0.80 | 2.00 | 128K | 推荐，任意分辨率 |
| doubao-1.5-thinking-vision-pro | 4.00 | 16.00 | 128K | 深度推理 |
| doubao-seed-1.6-vision | ≥0.80 | ≥8.00 | 128K | 最新一代 |

**优势：** 任意分辨率/极端宽高比支持、精细视觉理解、价格有竞争力
**适合：** 产品照片尺寸多样的场景

### 2.4 阿里云（通义千问 / Qwen-VL）

**定位：** 视觉理解基准测试领先者

| 模型 | 输入(RMB/M) | 输出(RMB/M) | 上下文 | 备注 |
|------|-----------|-----------|--------|------|
| qwen3-vl-plus | 0.80 | 2.00 | 1M | 支持上下文缓存 |
| qwen-vl-plus | 1.50 | ~4.50 | 32K+ | 平衡之选 |
| qwen-vl-max | 3.00 | ~9.00 | 32K+ | 旗舰 |

**优势：** DocVQA 93.1% (超 GPT-4V)、原生 JSON mode、OpenAI 完全兼容
**适合：** 对结构化输出精度要求最高的场景

### 2.5 腾讯云（混元）

| 模型 | 输入(RMB/M) | 输出(RMB/M) | 备注 |
|------|-----------|-----------|------|
| hunyuan-turbos-vision | 3.00 | 9.00 | 推荐 |

**评价：** 定价统一但偏高，功能中规中矩，无明显优势

### 2.6 百度（文心一言 / ERNIE）

| 模型 | 输入(RMB/M) | 输出(RMB/M) | 备注 |
|------|-----------|-----------|------|
| ERNIE-4.5-Turbo-VL | ~0.80 | ~3.20 | 性价比尚可 |
| ERNIE-Speed/Lite | 免费 | 免费 | 基础能力 |

**评价：** API 兼容性不如竞品（部分 OpenAI 兼容），视觉模型竞争力一般

### 2.7 不推荐的服务商

| 服务商 | 原因 |
|--------|------|
| **月之暗面 (Kimi)** | 视觉模型价格 12-60 RMB/M，远超竞品，性价比极低 |
| **讯飞** | ~21 RMB/M 且 API 不兼容 OpenAI 格式（WebSocket） |
| **零一万物** | 公司战略调整中，模型更新不稳定，不建议长期依赖 |
| **DeepSeek** | 官方不提供视觉 API（仅文本），视觉模型需通过硅基流动等第三方 |

---

## 3. 单次调用成本估算

典型的 AiCad 图片参数提取请求：
- 输入：~500 tokens (prompt) + ~1500 tokens (图片编码) = 2000 input tokens
- 输出：~500 tokens (JSON 结果)

| 服务商 / 模型 | 单次成本 (RMB) | 1万次/月成本 |
|--------------|---------------|------------|
| 智谱 GLM-4V-Flash | **0** | **0** |
| 硅基流动 Qwen2.5-VL-7B | 0.0009 | 9 |
| 硅基流动 Qwen3-VL-8B | 0.002 | 20 |
| 火山引擎 doubao-1.5-vision-pro | 0.0026 | 26 |
| 阿里云 qwen-vl-plus | 0.005 | 53 |
| 阿里云 qwen-vl-max | 0.011 | 110 |

**结论：即使月调用 1 万次，最贵也仅 110 元/月。成本不是瓶颈。**

---

## 4. 几何理解能力排名

针对 AiCad 的核心需求（从产品照片提取比例、形状分类、特征识别）：

| 排名 | 模型 | 几何/空间强项 | 短板 |
|------|------|-------------|------|
| 1 | **阿里 Qwen-VL-Max / Qwen3-VL** | 文档/图表理解 SOTA、结构化 JSON 最稳 | 价格较高 |
| 2 | **火山 doubao-1.5-vision-pro** | 任意分辨率、精细视觉推理 | 生态不如阿里 |
| 3 | **智谱 GLM-4.6V** | 视觉定位强、免费额度大 | JSON 稳定性略逊 Qwen |
| 4 | 硅基流动 Qwen2.5-VL-7B | 性价比极高、Qwen 架构 | 7B 能力上限 |
| 5 | MiniMax-VL-01 | 4M 超长上下文 | 视觉精度中等 |

---

## 5. 推荐策略（分阶段）

### 阶段一：原型开发（零成本）

```
智谱 GLM-4V-Flash（免费）
   + 硅基流动 GLM-4.1V-9B-Thinking（免费）
```

- 目标：验证 pipeline 可行性
- 成本：0 元
- API 格式：OpenAI 兼容，后续切换零成本

### 阶段二：生产部署（性价比优先）

```
硅基流动 Qwen2.5-VL-7B（0.35 RMB/M）
   或 Qwen3-VL-8B（0.50/2.00 RMB/M）
```

- 目标：日常生产使用
- 月成本（1万次）：9-20 元
- 复杂图片 fallback：doubao-1.5-vision-pro

### 阶段三：质量优先

```
阿里云 qwen-vl-max（3.00/9.00 RMB/M）
   或 火山引擎 doubao-1.5-thinking-vision-pro
```

- 目标：对精度要求极高的场景
- 月成本（1万次）：~110 元

---

## 6. 技术集成建议

### API 统一接口设计

所有推荐服务商均支持 OpenAI 兼容格式，可设计统一后端：

```python
# 统一接口，切换 base_url 即可更换供应商
import openai

PROVIDERS = {
    "siliconflow": {
        "base_url": "https://api.siliconflow.cn/v1",
        "model": "Qwen/Qwen2.5-VL-7B-Instruct",
    },
    "zhipu": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4v-flash",
    },
    "volcano": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-1.5-vision-pro-32k",
    },
    "alibaba": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-vl-max",
    },
}

def extract_params(image_b64: str, anchor: dict, provider: str = "siliconflow"):
    cfg = PROVIDERS[provider]
    client = openai.OpenAI(base_url=cfg["base_url"], api_key=API_KEYS[provider])
    response = client.chat.completions.create(
        model=cfg["model"],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": f"锚定尺寸：{anchor['param']} = {anchor['value']}mm"},
            ]},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)
```

### 本地 VLM 也可作为 provider

Ollama 提供 OpenAI 兼容端点（`http://localhost:11434/v1`），可无缝接入同一接口：

```python
PROVIDERS["local"] = {
    "base_url": "http://localhost:11434/v1",
    "model": "qwen3-vl:4b",
}
```

---

## 7. 最终推荐

| 场景 | 推荐方案 | 月成本 |
|------|---------|--------|
| 开发调试 | 智谱 GLM-4V-Flash (免费) | 0 |
| 日常生产 | 硅基流动 Qwen2.5-VL-7B | ~9元/万次 |
| 高精度需求 | 阿里云 qwen-vl-max | ~110元/万次 |
| 离线环境 | 本地 Qwen3-VL-4B (Ollama) | 0（仅电费） |

**核心结论：成本极低（最贵不超 110元/月），质量完全够用，技术集成简单（统一 OpenAI 格式）。Phase 1 的技术瓶颈不在模型能力或成本，而在 Prompt 工程和参数映射逻辑的设计。**
