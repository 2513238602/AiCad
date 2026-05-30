# -*- coding: utf-8 -*-
"""
VLM 能力诊断测试 — 隔离问题根源

测试 1: 自由描述（不给 JSON 模板）— 测 VLM 是否能"看出"形状差异
测试 2: 对比提问（同时给两张图）— 测 VLM 是否能区分两瓶差异
测试 3: 简化 prompt（只提取 3 个关键参数）— 测是否 prompt 过长导致模板化
测试 4: 分步提取（先描述再提参数）— 测分步策略是否改善差异化
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

GLM_API_KEY = os.environ.get("GLM_API_KEY", "0d44fbe7c576473c8d89b85046b1edc3.MWR2xsYm7EIVbpZW")
GLM_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
GLM_MODEL = "glm-4.6v"

# 选两张差异最大的图片做对照
IMG_A = {
    "id": "cute_round",
    "url": "https://cdn.globalso.com/bmeipackaging/cute-lip-loss-tube-1.jpg",
    "desc": "可爱粉色圆润造型",
}
IMG_B = {
    "id": "bowling_shape",
    "url": "https://cdn.globalso.com/bmeipackaging/5105B-07.png",
    "desc": "保龄球造型异形瓶",
}
IMG_C = {
    "id": "standard_cyl",
    "url": "https://cdn.globalso.com/bmeipackaging/DSC_3559_%E5%89%AF%E6%9C%AC1.jpg",
    "desc": "标准圆柱形",
}


def load_image_b64(url: str, cache_dir: str = "tests/picture") -> str:
    """下载并返回 base64（复用缓存）"""
    os.makedirs(cache_dir, exist_ok=True)
    fname = url.split("/")[-1].split("?")[0]
    fname = urllib.request.unquote(fname)
    safe = "".join(c if c.isalnum() or c in ".-_" else "_" for c in fname)
    path = os.path.join(cache_dir, safe or "img.jpg")

    if os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
    else:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 Chrome/120"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        with open(path, "wb") as f:
            f.write(data)

    # 压缩大图
    if len(data) > 500 * 1024:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > 800:
            r = 800 / max(w, h)
            img = img.resize((int(w * r), int(h * r)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        data = buf.getvalue()

    return base64.b64encode(data).decode("utf-8")


def call_glm(messages: list, max_tokens: int = 800) -> str:
    """调用 GLM API，返回纯文本回复"""
    payload = json.dumps({
        "model": GLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }).encode("utf-8")

    req = urllib.request.Request(GLM_API_URL, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GLM_API_KEY}",
    })
    with urllib.request.urlopen(req, timeout=90) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"]


def make_image_content(b64: str) -> dict:
    ext = "png" if b64[:4] == "iVBO" else "jpeg"
    return {"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{b64}"}}


# ════════════════════════════════════════════════════════════════
# 测试 1: 自由描述 — VLM 能否看出形状差异？
# ════════════════════════════════════════════════════════════════

PROMPT_FREE_DESC = """请仔细观察这张唇釉瓶的图片，详细描述瓶身的外形特征。
包括但不限于：
1. 瓶身整体形状（圆柱？锥形？曲线？方形？异形？）
2. 从底部到颈部的轮廓变化（是直线还是有弧度？哪里最粗哪里最细？）
3. 肩部过渡形态（圆弧？折角？平滑曲线？）
4. 与标准圆柱形唇釉瓶相比，有什么独特之处？
5. 如果要用一条从底到顶的截面轮廓线来描述瓶身形状，这条线是什么样的？

请尽可能具体，不要使用笼统描述。"""


def test1_free_description():
    print("\n" + "=" * 60)
    print("测试 1: 自由描述 — VLM 能否看出形状差异？")
    print("=" * 60)

    for img in [IMG_A, IMG_B, IMG_C]:
        print(f"\n--- {img['id']}: {img['desc']} ---")
        b64 = load_image_b64(img["url"])
        t0 = time.time()
        reply = call_glm([{
            "role": "user",
            "content": [
                make_image_content(b64),
                {"type": "text", "text": PROMPT_FREE_DESC},
            ]
        }])
        print(f"  耗时: {time.time()-t0:.1f}s")
        print(f"  回复:\n{reply}\n")
        time.sleep(1)


# ════════════════════════════════════════════════════════════════
# 测试 2: 简化 prompt — 只提取 3 个关键差异参数
# ════════════════════════════════════════════════════════════════

PROMPT_SIMPLE = """观察这张唇釉瓶图片，回答以下问题（JSON格式）：
{
  "shape_type": "选一个: straight_cylinder / tapered / curved_body / square / irregular",
  "body_profile": "用文字描述从底部到口部的轮廓线形状变化",
  "widest_point": "最宽处在瓶身的什么位置（底部/中部/上部）",
  "aspect_ratio": "目测瓶身高度大约是最大直径的几倍（填数字）",
  "unique_features": "与标准直筒唇釉瓶相比的独特外形特征"
}
只输出JSON，不要其他内容。"""


def test2_simple_extraction():
    print("\n" + "=" * 60)
    print("测试 2: 简化提取 — 只关注形状差异")
    print("=" * 60)

    for img in [IMG_A, IMG_B, IMG_C]:
        print(f"\n--- {img['id']}: {img['desc']} ---")
        b64 = load_image_b64(img["url"])
        t0 = time.time()
        reply = call_glm([{
            "role": "user",
            "content": [
                make_image_content(b64),
                {"type": "text", "text": PROMPT_SIMPLE},
            ]
        }])
        print(f"  耗时: {time.time()-t0:.1f}s")
        print(f"  回复:\n{reply}\n")
        time.sleep(1)


# ════════════════════════════════════════════════════════════════
# 测试 3: 分步提取 — 先描述再提参数
# ════════════════════════════════════════════════════════════════

PROMPT_STEP1 = """仔细观察这张唇釉瓶图片。
第一步：请详细描述瓶身的外形轮廓（从底部到口部的形状变化）。
只描述外形，不需要估算具体尺寸。"""

PROMPT_STEP2_TEMPLATE = """你刚才对这张唇釉瓶的形状描述是：
"{description}"

现在基于你的观察，请估算具体参数。注意：
- 如果瓶身有曲线变化（不是标准直筒），请一定使用 spline 模式并提供 profile_points
- profile_points 格式为 [[r1,z1], [r2,z2], ...]，r=半径(mm)，z=从底到顶的高度(mm)
- 至少提供 5 个控制点来描述轮廓曲线

严格按 JSON 输出：
{{
  "height_mm": <瓶身总高>,
  "body_od_mm": <最大外径>,
  "neck_od_mm": <口部外径>,
  "shape": <"cyl" 或 "taper">,
  "profile_mode": <"classic" 或 "spline">,
  "profile_points": <控制点数组，如果是直筒则为[]>,
  "shoulder_style": <"round" 或 "angular" 或 "sloped">,
  "confidence": <0.0-1.0>
}}"""


def test3_two_step():
    print("\n" + "=" * 60)
    print("测试 3: 分步提取 — 先描述再提参数")
    print("=" * 60)

    for img in [IMG_A, IMG_B, IMG_C]:
        print(f"\n--- {img['id']}: {img['desc']} ---")
        b64 = load_image_b64(img["url"])

        # Step 1: 描述
        print("  [Step 1] 描述外形...")
        t0 = time.time()
        desc = call_glm([{
            "role": "user",
            "content": [
                make_image_content(b64),
                {"type": "text", "text": PROMPT_STEP1},
            ]
        }])
        print(f"  耗时: {time.time()-t0:.1f}s")
        print(f"  描述: {desc[:200]}...")

        time.sleep(1)

        # Step 2: 基于描述提参数（带图片上下文）
        print("  [Step 2] 基于描述提取参数...")
        t0 = time.time()
        params = call_glm([
            {
                "role": "user",
                "content": [
                    make_image_content(b64),
                    {"type": "text", "text": PROMPT_STEP1},
                ]
            },
            {
                "role": "assistant",
                "content": desc,
            },
            {
                "role": "user",
                "content": PROMPT_STEP2_TEMPLATE.format(description=desc[:300]),
            }
        ], max_tokens=1000)
        print(f"  耗时: {time.time()-t0:.1f}s")
        print(f"  参数:\n{params}\n")
        time.sleep(1)


# ════════════════════════════════════════════════════════════════
# 测试 4: 轮廓点专项 — 用明确指令测试曲线提取能力
# ════════════════════════════════════════════════════════════════

PROMPT_PROFILE = """这张图是一个唇釉瓶。请观察瓶身外轮廓（从底部到口部），用一系列控制点来描述这条轮廓线。

假设瓶身总高约 80mm，请沿高度方向每隔约 10mm 取一个点，测量该高度处的瓶身半径。

严格按 JSON 输出，不要其他内容：
{
  "points": [
    {"z_mm": 0, "radius_mm": <底部半径>},
    {"z_mm": 10, "radius_mm": <10mm高度处半径>},
    {"z_mm": 20, "radius_mm": <20mm高度处半径>},
    ...继续直到瓶口
  ],
  "is_straight_cylinder": <true/false，瓶身是否为标准直筒>,
  "max_radius_z": <最大半径出现在什么高度>,
  "shape_summary": "一句话描述轮廓变化趋势"
}"""


def test4_profile_points():
    print("\n" + "=" * 60)
    print("测试 4: 轮廓点专项 — 逐高度采样半径")
    print("=" * 60)

    for img in [IMG_A, IMG_B, IMG_C]:
        print(f"\n--- {img['id']}: {img['desc']} ---")
        b64 = load_image_b64(img["url"])
        t0 = time.time()
        reply = call_glm([{
            "role": "user",
            "content": [
                make_image_content(b64),
                {"type": "text", "text": PROMPT_PROFILE},
            ]
        }], max_tokens=1200)
        print(f"  耗时: {time.time()-t0:.1f}s")
        print(f"  回复:\n{reply}\n")
        time.sleep(1)


# ════════════════════════════════════════════════════════════════

def main():
    print("VLM 能力诊断测试")
    print(f"模型: {GLM_MODEL}")
    print(f"测试图片: {IMG_A['desc']} vs {IMG_B['desc']} vs {IMG_C['desc']}")

    test1_free_description()
    test2_simple_extraction()
    test3_two_step()
    test4_profile_points()

    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
