# -*- coding: utf-8 -*-
"""
VLM 两步提取引擎 — 图片 → 唇釉瓶完整参数包

三职分工：
- 用户提供：关键尺寸（总高、外径、口径）
- VLM 提取：外形特征（形状、轮廓曲线、肩部、底部）
- 系统填充：内部结构（螺纹、壁厚、内深、装配间隙）
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import urllib.request
from typing import Any, Callable

GLM_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
GLM_MODEL = "glm-4.6v"

# ════════════════════════════════════════════════════════════════════════
# Prompt 定义
# ════════════════════════════════════════════════════════════════════════

STEP1A_PROMPT = """\
这张图片展示了一款唇釉瓶产品。请仔细观察并描述其【基本几何形态】。

⚠️ 本步只关注基本几何形态（轮廓、截面、比例），忽略所有装饰性元素（竖纹、横沟槽、凸环、底座台阶等），装饰在下一步分析。

一、瓶身（装液体的容器部分）：
1. 截面形状（想象从正上方俯视瓶身，看到的横截面轮廓）：
   - 圆形：瓶身表面是连续光滑的曲面，没有平面棱面
   - 方形：有四个平面和四条竖向棱线，棱角分明（可能有圆角）
   - 六边形/八边形：有对应数量的平面和棱线
   ⚠️ 判断标准：棱线必须存在于【瓶身本体】上，从底部延伸到顶部。
     瓶盖或装饰带上的竖条纹/滚花纹理不算棱面——那是装饰，不影响截面形状。
     如果只有瓶盖有竖向条纹而瓶身是光滑曲面，截面仍然是"圆形"。
2. 整体轮廓：从底部到瓶口，外径是否变化？
   - 直筒（等径）/ 锥形（底宽顶窄或反向）/ 弧形变化（鼓肚/收腰/水滴/S形）
3. 肩部（瓶身→瓶口过渡区域）：圆滑过渡、有棱角、还是斜面？过渡长还是短？
4. 底部：平底、内凹、还是外凸？
5. 螺纹口（颈部）：约占瓶身总高的多少比例？（如 1/5、1/4、1/3）

二、瓶盖：
1. 高度：约占产品总可见高度的多少？（如 1/3、2/5、1/2）
2. 外径：与瓶身等宽、更宽（蘑菇形）、还是更窄？
3. 锥度：等径直筒还是有锥度？
4. 顶部：平顶、圆弧顶、还是尖顶？

请如实描述几何形态，只关注形状轮廓，忽略表面纹理和装饰。"""

STEP1B_TEMPLATE = """\
继续分析同一张唇釉瓶图片。你刚才已经描述了基本几何形态：
"{geometry_description}"

现在请仔细观察并描述【装饰与表面特征】：

一、瓶盖表面纹理：
- 光面（无任何纹路）、滚花（细密菱形网格）、竖条纹（纵向沟槽）、横沟槽、还是其他？

二、装饰环带（瓶身与瓶盖之间的过渡区域）：
1. 是否有一圈比瓶身更宽或有纹理的装饰带？
2. 如有：竖纹、横纹、还是光滑凸环？大约占瓶身高度多少比例？

三、底座台阶：
- 瓶底是否有一圈略宽于瓶身的底座台阶？

请只描述装饰和表面特征，不要重复几何形态。"""

STEP2_TEMPLATE = """\
你刚才对这张唇釉瓶的描述是：
"{description}"

用户告知瓶身的关键尺寸：
- 瓶身总高: {height_mm}mm（含颈部）
- 最大外径: {body_od_mm}mm
- 口部外径: {neck_od_mm}mm

根据你的描述和这些尺寸，提取瓶身和瓶盖的形状参数。

关键判断规则：
1. profile_mode 判断：
   - 描述中提到"直筒"/"圆柱"/"等径"且无弧度变化 → "classic"
   - 描述中提到"鼓肚"/"收腰"/"水滴"/"S形"/"弧度变化" → "spline"
2. profile_points：仅 spline 模式需要，提供 5-8 个 [r, z] 控制点
   - r 是半径(mm)，范围 [{neck_r:.1f}, {body_r:.1f}]
   - z 是从底部向上的高度(mm)，范围 [0, {height_mm}]
3. shape 判断：有锥度（底宽顶窄或底窄顶宽）→ "taper"，否则 → "cyl"
4. cap_top_shape："flat"=平顶，"dome"=圆弧顶，"pointed"=尖顶（不要用 "round"）
5. cap_od_ratio：瓶盖外径/瓶身外径，齐平=1.0，蘑菇盖>1.05，缩口盖<0.95
6. bottle_collar_style：瓶身肩部无装饰→"none"，有竖纹环带→"ribs"，有横纹→"grooves"，有光滑凸环→"smooth_band"
7. bottle_base_ring：瓶底比瓶身略宽的台阶→true，平齐或无台阶→false
8. bottle_neck_height_ratio：螺纹口（颈部）高度占瓶身总高比例，短颈0.10~0.15，长颈0.20~0.30
9. bottle_shoulder_height_ratio：肩部过渡区占瓶身总高比例，短肩0.03~0.08，长肩0.10~0.15

严格输出 JSON，不要其他内容：
{{
  "cross_section": "round" 或 "octagon" 或 "hexagon" 或 "square",
  "corner_radius_mm": <float, 方形/多边形圆角半径 0-8mm, 圆形填 0>,
  "shape": "cyl" 或 "taper",
  "taper_deg": <float, 0=直筒, 正值=底宽顶窄, 负值=底窄顶宽>,
  "profile_mode": "classic" 或 "spline",
  "profile_points": [],
  "shoulder_style": "round" 或 "angular" 或 "sloped",
  "shoulder_fillet_mm": <float, 0-15>,
  "bottom_style": "flat" 或 "concave" 或 "convex",
  "cap_height_ratio": <float, 瓶盖高度占总可见高度比例, 0.2~0.7>,
  "cap_od_ratio": <float, 瓶盖外径/瓶身外径>,
  "cap_taper_deg": <float, 瓶盖锥度角, 0=直筒>,
  "cap_top_shape": "flat" 或 "dome" 或 "pointed",
  "cap_grip_style": "smooth" 或 "knurl" 或 "stripe" 或 "ribs" 或 "horizontal_grooves",
  "bottle_collar_style": "none" 或 "ribs" 或 "grooves" 或 "smooth_band",
  "bottle_collar_height_ratio": <float, 装饰环带高度占瓶身高度比例, 0=无, 0.05~0.15>,
  "bottle_base_ring": <bool, 瓶底是否有底座台阶>,
  "bottle_neck_height_ratio": <float, 螺纹口高度占瓶身总高比例, 0.10~0.30>,
  "bottle_shoulder_height_ratio": <float, 肩部过渡区占瓶身总高比例, 0.03~0.15>,
  "confidence": <0.0-1.0>,
  "shape_description": "<一句话概括>"
}}"""


# ════════════════════════════════════════════════════════════════════════
# GLM API 调用
# ════════════════════════════════════════════════════════════════════════

def _get_api_key() -> str:
    key = os.environ.get("GLM_API_KEY", "")
    if not key:
        raise RuntimeError("未设置 GLM_API_KEY 环境变量")
    return key


def _call_glm(messages: list, max_tokens: int = 4000, model: str | None = None) -> str:
    """调用 GLM，返回纯文本（启用思考模式以提升视觉分析质量）"""
    body: dict = {
        "model": model or GLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 1.0,
        "thinking": {"type": "enabled"},
    }
    payload = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(GLM_API_URL, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_get_api_key()}",
    })
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    msg = result["choices"][0]["message"]
    # 思考模式：reasoning_content 含推理过程，content 含最终回答
    # 若 content 为空（部分 API 版本），回退到 reasoning_content
    content = msg.get("content") or ""
    if not content.strip():
        content = msg.get("reasoning_content") or ""
    return content


def _compress_image_b64(b64: str, max_px: int = 800, quality: int = 80) -> str:
    """压缩 base64 图片到合理大小，防止 GLM API 超时"""
    try:
        from PIL import Image
        raw = base64.b64decode(b64)
        img = Image.open(io.BytesIO(raw))
        w, h = img.size
        if max(w, h) > max_px:
            ratio = max_px / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=quality)
        return base64.b64encode(buf.getvalue()).decode("ascii")
    except ImportError:
        return b64  # 没有 Pillow 就用原图
    except Exception:
        return b64


def _make_image_content(b64: str) -> dict:
    # 自动压缩大图
    if len(b64) > 500_000:  # ~375KB 原始数据
        b64 = _compress_image_b64(b64)
    ext = "png" if b64[:4] == "iVBO" else "jpeg"
    return {"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{b64}"}}


def _parse_json(text: str) -> dict | None:
    text = text.strip()
    if "```" in text:
        for part in text.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


# ════════════════════════════════════════════════════════════════════════
# 两步提取
# ════════════════════════════════════════════════════════════════════════

def vlm_describe(image_b64: str) -> str:
    """Step 1: 两步描述瓶身外形 — 先几何形态，再装饰特征。

    拆分为 1A（几何）和 1B（装饰）两次调用，防止 VLM 将瓶盖装饰纹理
    误判为瓶身截面形状（如竖条纹盖 → 误判六边形截面）。
    """
    img_content = _make_image_content(image_b64)

    # Step 1A: 几何形态（截面、轮廓、比例）
    geometry_desc = _call_glm([{
        "role": "user",
        "content": [img_content, {"type": "text", "text": STEP1A_PROMPT}],
    }])

    # Step 1B: 装饰与表面特征（盖纹理、装饰带、底座）
    step1b_prompt = STEP1B_TEMPLATE.format(
        geometry_description=geometry_desc[:300]
    )
    decoration_desc = _call_glm([{
        "role": "user",
        "content": [img_content, {"type": "text", "text": step1b_prompt}],
    }])

    # Step 1C: 材质与外观（透明/不透明/金属等）
    # 合并为完整描述，供 Step 2 结构化提取使用
    combined = (
        f"【几何形态】\n{geometry_desc}\n\n"
        f"【装饰特征】\n{decoration_desc}"
    )
    return combined


def _sanitize_vlm_shape(raw: dict) -> dict:
    """清洗 VLM 返回的 shape 字典，将 None/null 值替换为安全默认值。

    VLM（GLM）经常对不适用的字段返回 null（如圆形截面的 corner_radius_mm），
    而 dict.get(key, default) 在 key 存在但值为 None 时不会使用 default。
    """
    DEFAULTS = {
        "cross_section": "round",
        "corner_radius_mm": 3.0,
        "shape": "cyl",
        "taper_deg": 0.0,
        "profile_mode": "classic",
        "profile_points": [],
        "shoulder_style": "round",
        "shoulder_fillet_mm": 3.0,
        "bottom_style": "flat",
        "cap_height_ratio": 0.0,
        "cap_od_ratio": 1.0,
        "cap_taper_deg": 0.0,
        "cap_top_shape": "flat",
        "cap_grip_style": "smooth",
        "bottle_collar_style": "none",
        "bottle_collar_height_ratio": 0,
        "bottle_base_ring": False,
        "bottle_neck_height_ratio": 0.15,
        "bottle_shoulder_height_ratio": 0.08,
        "confidence": 0.5,
        "shape_description": "",
    }
    # 材质枚举校验
    # 枚举修正（在 None 替换之前）
    if raw.get("cap_top_shape") == "round":
        raw["cap_top_shape"] = "dome"
    if raw.get("cap_top_shape") not in (None, "flat", "dome", "pointed"):
        raw["cap_top_shape"] = "flat"
    if raw.get("profile_mode") not in (None, "classic", "spline"):
        raw["profile_mode"] = "classic"
    if raw.get("cap_grip_style") == "smooth":
        raw["cap_grip_style"] = "none"  # VLM 的 smooth 映射为模型的 none

    out = {}
    for k, v in raw.items():
        if v is None and k in DEFAULTS:
            out[k] = DEFAULTS[k]
        else:
            out[k] = v
    return out


def _rescue_from_description(description: str) -> dict:
    """当 Step2 JSON 解析失败时，从 Step1 文字描述中用关键词匹配抢救关键分类字段"""
    result = {
        "shape": "cyl", "profile_mode": "classic", "profile_points": [],
        "shoulder_style": "round", "bottom_style": "flat",
        "confidence": 0.4,  # 略高于纯失败的 0.3（至少抢救了部分字段）
    }
    txt = description

    # 截面形状
    if "方形" in txt or "正方形" in txt:
        result["cross_section"] = "square"
    elif "六边形" in txt:
        result["cross_section"] = "hexagon"
    elif "八边形" in txt:
        result["cross_section"] = "octagon"
    elif "三角" in txt:
        result["cross_section"] = "triangle"
    else:
        result["cross_section"] = "round"

    # 盖顶形态
    if "圆弧顶" in txt or "圆顶" in txt or "弧形顶" in txt:
        result["cap_top_shape"] = "dome"
    elif "尖顶" in txt:
        result["cap_top_shape"] = "pointed"
    else:
        result["cap_top_shape"] = "flat"

    # 盖面纹理
    if "滚花" in txt:
        result["cap_grip_style"] = "knurl"
    elif "竖纹" in txt or "竖条纹" in txt or "纵向条纹" in txt:
        result["cap_grip_style"] = "ribs"
    elif "横纹" in txt or "横沟槽" in txt:
        result["cap_grip_style"] = "horizontal_grooves"
    elif "条纹" in txt:
        result["cap_grip_style"] = "stripe"
    elif "光面" in txt or "光滑" in txt:
        result["cap_grip_style"] = "none"

    # 装饰带
    if "装饰环带" in txt or "装饰带" in txt:
        if "竖纹" in txt:
            result["bottle_collar_style"] = "ribs"
        elif "横纹" in txt:
            result["bottle_collar_style"] = "grooves"
        else:
            result["bottle_collar_style"] = "smooth_band"
    if "底座环" in txt or "底座台阶" in txt:
        if "无" not in txt.split("底座")[0][-5:]:
            result["bottle_base_ring"] = True

    # 盖与瓶身宽度关系
    if "与瓶身等宽" in txt or "宽度一致" in txt or "外径一致" in txt:
        result["cap_od_ratio"] = 1.0

    # 盖高比例
    if "1/3" in txt or "三分之一" in txt:
        result["cap_height_ratio"] = 0.33
    elif "1/2" in txt or "二分之一" in txt:
        result["cap_height_ratio"] = 0.5

    return result


def vlm_extract_shape(description: str, user_dims: dict) -> dict:
    """Step 2: 基于描述和用户尺寸提取结构化形状参数（纯文本，不传图片）"""
    prompt2 = STEP2_TEMPLATE.format(
        description=description[:500],
        height_mm=user_dims["height_mm"],
        body_od_mm=user_dims["body_od_mm"],
        neck_od_mm=user_dims["neck_od_mm"],
        body_r=user_dims["body_od_mm"] / 2,
        neck_r=user_dims["neck_od_mm"] / 2,
    )
    # 纯文本调用（glm-4.6v 统一模型），无需重传图片——描述已包含全部视觉信息
    reply = _call_glm([
        {"role": "user", "content": f"我观察了一张唇釉瓶图片，以下是详细描述：\n\n{description}"},
        {"role": "user", "content": prompt2},
    ], max_tokens=4000, model="glm-4.6v")

    parsed = _parse_json(reply)
    if parsed is None:
        # JSON 解析失败 → 从 Step1 描述文本中抢救关键分类字段
        rescued = _rescue_from_description(description)
        return rescued
    return _sanitize_vlm_shape(parsed)


# ════════════════════════════════════════════════════════════════════════
# 轮廓点处理
# ════════════════════════════════════════════════════════════════════════

def _rescale_profile(raw_pts: list, user_dims: dict) -> list:
    """将 VLM 输出的轮廓点校准到用户实际尺寸"""
    if not raw_pts or len(raw_pts) < 3:
        return []

    h = user_dims["height_mm"]
    od = user_dims["body_od_mm"]
    nod = user_dims["neck_od_mm"]
    max_r = od / 2
    min_r = nod / 2
    neck_h = _estimate_neck_height(user_dims)
    body_z_max = h - neck_h  # 轮廓只到肩顶

    # 提取 VLM 的 r 和 z 范围
    rs = [pt[0] for pt in raw_pts]
    zs = [pt[1] for pt in raw_pts]
    vlm_r_min, vlm_r_max = min(rs), max(rs)
    vlm_z_min, vlm_z_max = min(zs), max(zs)

    scaled = []
    for r, z in raw_pts:
        # Z 缩放到 [0, body_z_max]
        if vlm_z_max > vlm_z_min:
            nz = (z - vlm_z_min) / (vlm_z_max - vlm_z_min) * body_z_max
        else:
            nz = z
        # R 缩放到 [min_r, max_r]
        if vlm_r_max > vlm_r_min:
            nr = min_r + (r - vlm_r_min) / (vlm_r_max - vlm_r_min) * (max_r - min_r)
        else:
            nr = max_r
        # 安全夹紧
        nr = max(min_r * 0.9, min(max_r * 1.05, nr))
        nz = max(0, min(body_z_max, nz))
        scaled.append([round(nr, 2), round(nz, 2)])

    # 确保 Z 单调递增
    scaled.sort(key=lambda p: p[1])
    # 去重（z 相同的只保留一个）
    deduped = [scaled[0]]
    for p in scaled[1:]:
        if p[1] > deduped[-1][1] + 0.1:
            deduped.append(p)

    # 确保首点 z=0，末点 z=body_z_max
    if deduped[0][1] > 0.5:
        deduped.insert(0, [deduped[0][0], 0.0])
    else:
        deduped[0][1] = 0.0
    if deduped[-1][1] < body_z_max - 1:
        deduped.append([min_r, body_z_max])

    return deduped


def _is_meaningful_curve(pts: list, max_r: float) -> bool:
    """检查轮廓点是否有真正的曲线变化（vs 接近直筒）"""
    if len(pts) < 3:
        return False
    rs = [p[0] for p in pts]
    r_range = max(rs) - min(rs)
    # 如果所有点的半径变化 < 最大半径的 5%，认为是直筒
    return r_range > max_r * 0.05


def _estimate_neck_height(h: float, vlm_shape: dict) -> float:
    """估算颈部高度：CV 绝对值 > VLM ratio > 默认比例"""
    # 1. CV 精确测量（来自 merge_cv_vlm 的 bottle_profile）
    cv_neck_h = float(vlm_shape.get("bottle_neck_height_mm", 0))
    if cv_neck_h > 0:
        return max(4.0, min(30.0, cv_neck_h))
    # 2. VLM 比例估计
    vlm_ratio = float(vlm_shape.get("bottle_neck_height_ratio", 0))
    if vlm_ratio > 0.05:
        return max(4.0, min(30.0, h * vlm_ratio))
    # 3. 默认
    return max(4.0, min(25.0, h * 0.14))


def _estimate_shoulder_height(h: float, od: float, nod: float, vlm_shape: dict) -> float:
    """估算肩部高度：CV 绝对值 > VLM ratio > 几何推算"""
    # 1. CV 精确测量（0 是合法值——锥形瓶无肩部）
    if "bottle_shoulder_height_mm" in vlm_shape:
        cv_sh_h = float(vlm_shape["bottle_shoulder_height_mm"])
        return max(0.0, min(30.0, cv_sh_h))
    # 2. merge 传入的 shoulder_height_mm（VLM 或 CV）
    if "shoulder_height_mm" in vlm_shape:
        sh_override = float(vlm_shape["shoulder_height_mm"])
        return max(0.0, min(30.0, sh_override))
    # 3. VLM 比例
    vlm_ratio = float(vlm_shape.get("bottle_shoulder_height_ratio", 0))
    if vlm_ratio > 0.02:
        return max(2.0, min(30.0, h * vlm_ratio))
    # 4. 默认：从直径差推算
    return max(2.0, min(30.0, (od - nod) * 0.5 + 3.0))


# ════════════════════════════════════════════════════════════════════════
# 参数合成 — 4 组件完整参数包
# ════════════════════════════════════════════════════════════════════════

def build_bottle_params(user_dims: dict, vlm_shape: dict) -> dict:
    """合成瓶身完整参数"""
    h = user_dims["height_mm"]
    od = user_dims["body_od_mm"]
    nod = max(10.0, user_dims["neck_od_mm"])  # schema min=10.0
    neck_h = _estimate_neck_height(h, vlm_shape)
    shoulder_h = _estimate_shoulder_height(h, od, nod, vlm_shape)

    # 截面形状
    cross_section = vlm_shape.get("cross_section", "round")
    if cross_section not in ("round", "square", "triangle", "hexagon", "octagon"):
        cross_section = "round"

    # 多边形截面需要最小肩高来完成多边形→圆形过渡 loft
    if cross_section != "round" and shoulder_h < 1.0:
        shoulder_h = 1.0
    corner_r = float(vlm_shape.get("corner_radius_mm", 3.0))
    corner_r = max(0.5, min(10.0, corner_r))

    p = {
        # 用户尺寸
        "height_mm": h,
        "body_od_mm": od,
        "neck_od_mm": nod,
        "neck_height_mm": neck_h,
        # 截面形状
        "cross_section": cross_section,
        "corner_radius_mm": corner_r,
        # VLM 形状
        "shape": vlm_shape.get("shape", "cyl"),
        "taper_deg": vlm_shape.get("taper_deg", 0.0),
        "shoulder_height_mm": shoulder_h,
        "shoulder_style": vlm_shape.get("shoulder_style", "round"),
        "shoulder_fillet_mm": vlm_shape.get("shoulder_fillet_mm", 3.0),
        "bottom_style": vlm_shape.get("bottom_style", "flat"),
        "profile_mode": "classic",
        "profile_points_json": "[]",
        "profile_symmetry": "symmetric",
        "profile_b_points_json": "[]",
        # 系统默认
        "lip_thickness_mm": 1.0,
        "bottom_thickness_mm": 2.0,
        "bottom_concave_mm": 1.0,
        "bottom_fillet_mm": vlm_shape.get("bottom_fillet_mm", 1.5),
        "finish": f"{round(nod)}-415",
        "cap_clearance_mm": 0.2,
        # 标准螺纹
        "thread.enabled": True,
        "thread.pitch_mm": 2.7,
        "thread.turns": 2,
        "thread.depth_mm": 0.75,
        "thread.lead_angle_deg": 3.0,
        "thread.segmented": False,
        "thread.gap_angle_deg": 20.0,
    }

    # 处理轮廓点（仅当 VLM 明确指定 spline 模式时）
    vlm_mode = vlm_shape.get("profile_mode", "classic")
    raw_pts = vlm_shape.get("profile_points", [])
    if vlm_mode == "spline":
        if raw_pts and isinstance(raw_pts, list) and len(raw_pts) >= 3:
            scaled = _rescale_profile(raw_pts, user_dims)
            if len(scaled) >= 3 and _is_meaningful_curve(scaled, od / 2):
                p["profile_mode"] = "spline"
                p["profile_points_json"] = json.dumps(scaled)
            else:
                # 控制点不够弯曲，仍启用 spline（建模器会生成默认轮廓）
                p["profile_mode"] = "spline"
        else:
            # 无控制点但指定了 spline 模式，建模器会自动生成默认轮廓
            p["profile_mode"] = "spline"

    # 螺纹长度安全：短瓶颈部空间不足时自动减少圈数
    max_thread_len = neck_h - 1.0  # thread_safe 硬约束要求
    if p["thread.pitch_mm"] * p["thread.turns"] > max_thread_len:
        p["thread.turns"] = 1
        if p["thread.pitch_mm"] > max_thread_len:
            p["thread.pitch_mm"] = max(1.5, max_thread_len)

    # 枚举安全校验
    if p["shape"] not in ("cyl", "taper"):
        p["shape"] = "cyl"
    if p["shoulder_style"] not in ("round", "angular", "sloped"):
        p["shoulder_style"] = "round"
    if p["bottom_style"] not in ("flat", "concave", "convex"):
        p["bottom_style"] = "flat"
    p["taper_deg"] = max(-5, min(8, p["taper_deg"]))
    p["shoulder_fillet_mm"] = max(0, min(15, p["shoulder_fillet_mm"]))

    # 派生参数 — normalize_strict 不会自动调用 DerivedRule，
    # 必须在这里显式设置，否则会使用 ParamDef 静态默认值导致约束失败
    wall = max(0.8, min(2.0, od * 0.05))
    # shoulder_h 已由 _estimate_shoulder_height 计算（CV > VLM > 几何推算）
    inner_depth = max(10.0, min(130.0, h - p["bottom_thickness_mm"] - 3.0))  # ParamDef: 10~130
    inner_r = od / 2 - wall
    capacity = round(math.pi * inner_r ** 2 * inner_depth / 1000.0, 1)
    full_depth = h - p["bottom_thickness_mm"]
    full_cap = round(math.pi * inner_r ** 2 * full_depth / 1000.0, 1)

    p["wall_thickness_mm"] = wall
    p["shoulder_height_mm"] = shoulder_h
    p["inner_depth_mm"] = inner_depth
    p["capacity_ml"] = capacity
    p["full_capacity_ml"] = full_cap

    # 装饰特征（CV 精确值优先，VLM ratio 回退）
    collar_style = vlm_shape.get("bottle_collar_style", "none")
    collar_abs_h = float(vlm_shape.get("bottle_collar_height_mm", 0))
    collar_ratio = float(vlm_shape.get("bottle_collar_height_ratio", 0))

    collar_h = 0
    if collar_abs_h > 0:
        # CV 绝对值（来自 merge_cv_vlm 中的 CV 装饰带检测）
        collar_h = max(1.5, min(12.0, collar_abs_h))
    elif collar_style != "none" and collar_ratio > 0:
        # VLM ratio 回退
        body_h_est = h * 0.7
        collar_h = max(1.5, min(12.0, body_h_est * collar_ratio))

    if collar_h > 0 and collar_style != "none":
        p["collar_enabled"] = True
        p["collar_height_mm"] = round(collar_h, 1)
        # collar 宽度外凸（CV 精确值 > 默认）
        collar_w_excess = float(vlm_shape.get("bottle_collar_width_excess_mm", 0.5))
        p["collar_width_excess_mm"] = max(0.0, min(3.0, collar_w_excess))
        if collar_style == "ribs":
            p["collar_rib_count"] = 30
            p["collar_rib_depth_mm"] = 0.3

    if vlm_shape.get("bottle_base_ring", False):
        p["base_ring_enabled"] = True
        p["base_ring_height_mm"] = float(
            vlm_shape.get("bottle_base_ring_height_mm", 2.0))
        p["base_ring_width_excess_mm"] = float(
            vlm_shape.get("bottle_base_ring_width_excess_mm", 0.5))

    # 透传 user_dims 中的额外键（collar/base_ring 等装饰参数）
    _known = {"height_mm", "body_od_mm", "neck_od_mm"}
    for k, v in user_dims.items():
        if k not in _known and k not in p:
            p[k] = v

    return p


def derive_cap_params(bottle_p: dict, vlm_shape: dict) -> dict:
    """从瓶身参数 + VLM 视觉比例推导瓶盖参数"""
    body_od = bottle_p["body_od_mm"]
    nod = bottle_p["neck_od_mm"]
    bottle_h = bottle_p["height_mm"]
    neck_h = bottle_p.get("neck_height_mm", 10)

    # 盖径：VLM 可指定比例（蘑菇盖>1, 缩口盖<1, 齐平=1）
    cap_od_ratio = vlm_shape.get("cap_od_ratio", 1.0)
    if not (0.7 <= cap_od_ratio <= 1.4):
        cap_od_ratio = 1.0
    # 盖径基准：
    #   "body" - 基于瓶底最大外径（默认，适合直筒/微锥）
    #   "body_top" - 基于瓶身肩顶外径（锥瓶连续轮廓，盖覆盖肩部+颈部）
    cap_od_base = vlm_shape.get("cap_od_base", "body")
    body_top_od = 0  # 在 body_top 模式下有值，供 inner_id 使用
    if cap_od_base == "body_top":
        import math as _m
        shoulder_h = bottle_p.get("shoulder_height_mm", 8)
        body_h = bottle_h - neck_h - shoulder_h
        bottle_taper_deg = bottle_p.get("taper_deg", 0)
        delta_r = _m.tan(_m.radians(bottle_taper_deg)) * max(body_h, 0)
        body_top_od = body_od - 2 * delta_r
        body_top_od = max(nod + 2, body_top_od)  # 至少比颈径宽2mm
        # cap_od = body_top_od + 余量（底部间隙由薄壁+螺纹区豁免提供）
        min_cap_od = body_top_od + 0.8  # 总余量0.8mm（0.4mm/侧），薄壁0.3mm
        od = round(max((body_top_od + 0.3) * cap_od_ratio, min_cap_od), 1)
    else:
        od = round(body_od * cap_od_ratio, 1)
    # 物理约束：盖内径必须 >= 瓶颈外径（否则盖不上去）
    min_od = nod + 1.6  # 内径 = od - 1.6, 需 >= nod
    od = max(min_od, od)

    # 从 VLM 获取瓶盖高度（绝对值优先于比例）
    cap_abs_h = vlm_shape.get("cap_height_mm", 0)
    cap_ratio = vlm_shape.get("cap_height_ratio", 0)
    if cap_abs_h > 0:
        h = max(10, min(80, round(float(cap_abs_h), 1)))
    elif 0.15 <= cap_ratio <= 0.7:
        # VLM 给出的比例：总产品高度 = 瓶身可见部分 + 瓶盖可见部分
        # body_top 模式：盖覆盖肩部+颈部，可见瓶身 = body_h
        if cap_od_base == "body_top":
            shoulder_h_val = bottle_p.get("shoulder_height_mm", 8)
            visible_body = bottle_h - neck_h - shoulder_h_val
        else:
            visible_body = bottle_h - neck_h
        # cap_ratio = cap_h / (visible_body + cap_h)  → 解出 cap_h
        h = round(visible_body * cap_ratio / (1 - cap_ratio), 1)
        h = max(10, min(80, h))   # ParamDef: 10~80
    else:
        # VLM 未给出有效比例，回退到经验公式
        h = max(20, min(70, od * 1.6))

    # ★ 层1B: cap/bottle 高度比例约束 — cap 不超过 bottle 高度的 1.5 倍
    max_cap_h = bottle_h * 1.5
    if h > max_cap_h:
        h = round(max_cap_h, 1)

    # VLM 提取的瓶盖形态
    taper = max(0, min(8, vlm_shape.get("cap_taper_deg", 0)))
    # 锥瓶盖锥度继承：body_top 模式下盖继承瓶身同角度，保持轮廓线连续
    bottle_taper = bottle_p.get("taper_deg", 0)
    if cap_od_base == "body_top" and bottle_taper > 0 and taper == 0:
        taper = round(min(8, bottle_taper), 1)
    top_shape = vlm_shape.get("cap_top_shape", "flat")
    if top_shape == "round":
        top_shape = "dome"  # VLM 的 round 等同于模型的 dome
    if top_shape not in ("flat", "dome", "pointed"):
        top_shape = "flat"
    grip_style = vlm_shape.get("cap_grip_style", "knurl")
    if grip_style == "smooth":
        grip_style = "none"  # VLM 的 smooth 等同于模型的 none
    if grip_style not in ("none", "ribs", "knurl", "horizontal_grooves", "stripe"):
        grip_style = "knurl"

    # 根据纹理类型设置合理的纹理数量
    grip_count_map = {"knurl": 60, "horizontal_grooves": 0, "none": 0}
    grip_count = grip_count_map.get(grip_style, 24)

    # 截面形状：从瓶身继承（方形瓶身 → 方形瓶盖）
    cross_section = bottle_p.get("cross_section", "round")
    corner_radius_mm = bottle_p.get("corner_radius_mm", 3.0)

    # 方形截面：dome/pointed/grip 已支持，不再强制降级
    # （建模器通过 _square_to_circle_loft 和线性沟槽实现）

    # ★ 层1A: cap 顶部 OD 可行性检查 — 防止高锥度+长盖导致顶部退化
    if taper > 0 and h > 0:
        cap_top_od_est = od - 2 * math.tan(math.radians(taper)) * h
        min_top_od = 10.0 if cross_section == "square" else (8.0 if cross_section != "round" else 6.0)
        if cap_top_od_est < min_top_od:
            # 反算最大安全锥度（+0.5mm 余量避免浮点精度问题）
            safe_target = min_top_od + 0.5
            max_safe_taper = math.degrees(math.atan((od - safe_target) / (2 * h)))
            taper = round(max(0.5, max_safe_taper), 1)

    # 派生参数 — 实心盖/空心盖辨别
    # 判别条件：cap 底部外径 / 颈径 >= 阈值 → 实心盖（锥形瓶盖等）
    #   实心盖：内腔只需容纳颈部+螺纹，其余为实心材料
    #   空心盖：传统薄壁壳体，内腔贯穿整个盖高
    od_neck_ratio = od / nod if nod > 0 else 1.0
    solid_threshold = 1.5
    # 多边形盖内腔有效通过直径 = inner_id × cos(π/n)（内切圆），
    # 实心盖模式的小内径在多边形下会导致圆形颈部塞不进去，
    # 因此提高阈值，让同宽多边形盖走空心模式
    _n_sides = {"triangle": 3, "square": 4, "hexagon": 6, "octagon": 8}.get(cross_section, 0)
    if _n_sides >= 3:
        solid_threshold = 1.5 / math.cos(math.pi / _n_sides)
    is_solid_cap = od_neck_ratio >= solid_threshold

    if is_solid_cap:
        # 实心盖：内径刚好容纳颈部（颈径 + 2mm 间隙）
        inner_id = max(8.0, min(45.0, nod + 2.0))
        # 腔深只需容纳颈高 + 螺纹接合长度
        thread_engage = bottle_p.get("thread.pitch_mm", 2.7) * bottle_p.get("thread.turns", 2)
        cavity_depth = max(5.0, min(70.0, neck_h + thread_engage + 2.0))
    else:
        # 空心盖：传统薄壁，内径 = 外径 - 两侧壁厚
        inner_id = max(8.0, min(45.0, od - 1.6))
        cavity_depth = max(5.0, min(70.0, h - 1.5))

    result = {
        "outer_od_mm": od,
        "height_mm": h,
        "taper_deg": taper,
        "top_shape": top_shape,
        "edge_fillet_mm": 0.5,
        "finish": bottle_p.get("finish", "18-415"),
        "profile_mode": bottle_p.get("profile_mode", "classic"),
        "profile_points_json": "[]",
        "cross_section": cross_section,
        "corner_radius_mm": corner_radius_mm,
        "grip.style": grip_style,
        "grip.count": grip_count,
        "grip.depth_mm": 0.3 if grip_style != "none" else 0.0,
        # 派生参数
        "inner_id_mm": inner_id,
        "cavity_depth_mm": cavity_depth,
    }

    # ---- 可选内置杆子（cap 代替独立 wand）----
    cap_stem_enabled = vlm_shape.get("cap_stem_enabled", False)
    if cap_stem_enabled:
        stem_d = float(vlm_shape.get("cap_stem_diameter_mm", 4.25))
        brush_type = str(vlm_shape.get("cap_brush_type", "doe_foot"))
        result.update({
            "stem.enabled": True,
            "stem.diameter_mm": stem_d,
            "stem.profile": "round",
            "stem.taper_ratio": 1.0,
            "stem.wall_mm": 0.8,
            "thread.enabled": True,
            "thread.pitch_mm": bottle_p.get("thread.pitch_mm", 2.7),
            "thread.turns": bottle_p.get("thread.turns", 2),
            "thread.depth_mm": bottle_p.get("thread.depth_mm", 0.75),
            "thread.lead_angle_deg": bottle_p.get("thread.lead_angle_deg", 3.0),
            "thread.segmented": bottle_p.get("thread.segmented", False),
            "thread.gap_angle_deg": bottle_p.get("thread.gap_angle_deg", 20.0),
            # ★ 峰径：匹配瓶颈外径，且必须小于内腔直径（否则螺纹穿墙）
            "thread.crest_dia_mm": max(10.0, min(28.0,
                nod,
                inner_id - 2 * float(bottle_p.get("thread.depth_mm", 0.75)) - 0.5,
            )),
            "brush.type": brush_type,
            "brush.length_mm": 12.0,
            "brush.width_mm": stem_d + 3.0,
            "brush.thickness_mm": 3.0,
            "seal_ring.height_mm": 2.0,
            "seal_ring.style": "flat",
        })

    return result


def derive_wand_params(cap_p: dict, bottle_p: dict) -> dict:
    """从瓶盖+瓶身参数推导刷杆参数"""
    cap_od = cap_p["outer_od_mm"]
    cap_inner_id = cap_od - 1.6   # 壁厚 0.8 * 2
    cap_taper = cap_p.get("taper_deg", 0)

    bottle_h = bottle_p["height_mm"]
    cap_h = cap_p["height_mm"]
    neck_h = bottle_p.get("neck_height_mm", 10)

    if cap_taper >= 3:
        # ===== 锥盖模式：wand 盖部跟随锥度 =====
        # wand_od 取底部最宽处，锥度负责收窄顶部
        wand_od = max(10.0, min(35.0, round(cap_inner_id - 0.9, 1)))
        wand_cap_h = round(min(cap_h - 4, cap_h * 0.7), 1)
        wand_cap_h = max(8.0, min(35.0, wand_cap_h))
    else:
        # ===== 标准模式 =====
        wand_od = max(10.0, min(35.0, cap_inner_id - 0.9))
        wand_cap_h = round(min(cap_h - 4, cap_h * 0.7), 1)
        wand_cap_h = max(8.0, min(35.0, wand_cap_h))

    # 杆身长度：需伸入瓶内但不触底
    inner_depth = bottle_h - bottle_p.get("lip_thickness_mm", 1.0) - bottle_p.get("bottom_thickness_mm", 2.0)
    stem_len = max(20.0, min(150.0, inner_depth - 5))  # ParamDef: 20~150
    total_h = max(40.0, min(200.0, wand_cap_h + stem_len))  # ParamDef: 40~200

    nod = bottle_p["neck_od_mm"]
    # 杆径由瓶颈内腔决定（需穿过内塞孔口）
    # 约束: stem_diameter < orifice - 0.5
    rod_dia = max(2.0, min(10.0, nod * 0.25))  # ParamDef: 2~10
    orifice = rod_dia + 1.5  # 充足余量（需 > rod_dia + 0.5）

    # 派生参数 — 全部夹紧到 ParamDef 范围
    seal_ring_od = max(8.0, min(25.0, wand_od - 5.5))     # ParamDef: 8~25（窄盖支持）
    # 气密环在瓶颈处密封，不能超过螺纹底径（颈径约束）
    thread_depth_est = float(bottle_p.get("thread.depth_mm", 0.75))
    finish_dia = nod  # 颈径即螺纹峰径基准
    max_seal_ring = finish_dia - 2 * thread_depth_est + 1.0
    seal_ring_od = min(seal_ring_od, max_seal_ring)
    cavity_depth = max(5.0, min(35.0, wand_cap_h - 2.0))  # 合理范围
    mouth_to_top = max(0.0, min(80.0, round(wand_cap_h * 0.63, 1)))  # ParamDef: 0~80
    stem_length = max(20.0, min(150.0, round(total_h - wand_cap_h, 1)))  # ParamDef: 20~150
    # 螺纹峰径：必须匹配 finish 规格（否则 _finish_match 硬约束失败）
    finish = bottle_p.get("finish", "18-415")
    try:
        spec_dia = float(finish.split("-")[0])
    except (ValueError, IndexError):
        spec_dia = 18.0
    thread_crest_dia = max(10.0, min(28.0, spec_dia))  # ParamDef: 10~28
    # 窄盖安全：优先自动缩径保留螺纹，而非静默禁用
    thread_enabled = True
    max_thread_dia = cap_inner_id - 1.0
    if thread_crest_dia > max_thread_dia:
        # 自动缩径：将峰径缩至盖内径允许的最大值
        thread_crest_dia = max(10.0, round(max_thread_dia, 1))
        # 仅当缩径后仍不可行（< ParamDef 最小值 10mm）才禁用
        if thread_crest_dia < 10.0:
            thread_enabled = False

    # 极端锥度（≥8°）仍禁用螺纹
    if cap_taper >= 8:
        thread_enabled = False
        thread_crest_dia = max(10.0, min(28.0, rod_dia + 2.0))

    result = {
        "wand_type": "cap_integrated",
        "outer_od_mm": wand_od,
        "cap_height_mm": wand_cap_h,
        "cap_taper_deg": cap_taper if cap_taper >= 3 else 0.0,
        "stem_diameter_mm": rod_dia,
        "total_height_mm": total_h,
        "orifice_mm": orifice,
        "finish": bottle_p.get("finish", "18-415"),
        "stem_profile": "round",
        "stem_taper_ratio": 1.0,
        "stem_wall_mm": 0.8,
        "thread.enabled": thread_enabled,
        "thread.pitch_mm": 2.7,
        "thread.turns": 2,
        "thread.depth_mm": 0.75,
        "thread.lead_angle_deg": 3.0,
        "thread.segmented": False,
        "thread.gap_angle_deg": 20.0,
        "seal_ring.height_mm": 2.0,
        "seal_ring.style": "flat",
        "seal_ring.od_mm": seal_ring_od,
        "brush.type": "doe_foot",
        "brush.length_mm": 15.0,
        "brush.width_mm": rod_dia + 3.0,
        "brush.thickness_mm": 3.0,
        "fit_clearance_mm": 0.15,
        # 派生参数
        "cavity_depth_mm": cavity_depth,
        "mouth_to_top_mm": mouth_to_top,
        "stem_length_mm": stem_length,
        "thread.crest_dia_mm": thread_crest_dia,
    }

    return result


def derive_wiper_params(bottle_p: dict, wand_p: dict) -> dict:
    """从瓶身+刷杆参数推导刮片参数"""
    nod = bottle_p["neck_od_mm"]
    lip_t = bottle_p.get("lip_thickness_mm", 1.0)
    neck_id = nod - 2 * lip_t  # 瓶颈内径（内塞必须装入此内径）
    rod_dia = wand_p["stem_diameter_mm"]
    orifice = wand_p.get("orifice_mm", rod_dia + 1.5)
    # 内塞外径 = 颈内径 - 间隙（必须 < neck_id 才能装入）
    outer_od = max(10.0, min(32.0, neck_id - 0.3))
    inner_id = max(8.0, min(30.0, outer_od - 2.0))
    # 凸环外径：略小于颈内径，留 0.2mm 间隙装入
    flange_od = max(11.0, min(34.0, neck_id - 0.2))

    result = {
        "outer_od_mm": outer_od,
        "orifice_mm": orifice,
        "height_mm": max(4, min(12, neck_id * 0.4)),
        "finish": bottle_p.get("finish", "18-415"),
        "orifice_edge_mm": 0.5,
        # 派生参数 — 显式设置
        "inner_id_mm": inner_id,
        "flange_od_mm": flange_od,
        "flange_id_mm": max(8.0, min(30.0, outer_od - 1.0)),
        "flange_height_mm": 2.0,
        "flange_position": "top",
        "diaphragm_style": "flat",
        "diaphragm_thickness_mm": 0.8,
        "diaphragm_depth_mm": 0.5,
        "rib.enabled": False,
        "fit_clearance_mm": 0.15,
        "material": "LDPE",
    }

    return result


# ════════════════════════════════════════════════════════════════════════
# 参数协调 — 复用 DerivedRule / CrossComponentDerived 做全局一致性校验
# ════════════════════════════════════════════════════════════════════════

def reconcile_all_params(
    all_params: dict,
) -> tuple[dict, list[str]]:
    """
    全局参数协调 — 用已有规则验证+修正 VLM 派生链产出的参数。

    在 build_bottle → derive_cap → derive_wand → derive_wiper 链式合成之后、
    交给 generate() 之前调用。复用 derived_params.py 中已定义的规则，
    不重复任何计算公式。

    三个步骤：
    1. 全局不变量（cross_section 一致性）
    2. DerivedRule 范围校验（复用各组件 compute_range）
    3. CrossComponentDerived 约束校验（复用跨组件双向规则）

    返回: (修正后的 all_params, 修正报告列表)
    """
    from products.lip_gloss.derived_params import (
        CAP_DERIVED_RULES, BOTTLE_DERIVED_RULES,
        WAND_DERIVED_RULES, WIPER_DERIVED_RULES,
        CROSS_COMPONENT_RULES,
    )

    report: list[str] = []

    # --- Step 1: 全局不变量 --- cross_section 从 bottle 向下传播
    cs = all_params["bottle"].get("cross_section", "round")
    cr = all_params["bottle"].get("corner_radius_mm", 3.0)
    for comp_id in ("cap", "wand"):
        old_cs = all_params[comp_id].get("cross_section", "round")
        if old_cs != cs:
            all_params[comp_id]["cross_section"] = cs
            report.append(f"{comp_id}.cross_section: {old_cs} → {cs}")
        all_params[comp_id]["corner_radius_mm"] = cr

    # --- Step 2: DerivedRule 范围校验 ---
    rule_maps = {
        "cap": CAP_DERIVED_RULES,
        "bottle": BOTTLE_DERIVED_RULES,
        "wand": WAND_DERIVED_RULES,
        "wiper": WIPER_DERIVED_RULES,
    }
    for comp_id, rules in rule_maps.items():
        p = all_params[comp_id]
        for param_key, rule in rules.items():
            if rule.compute_range is None:
                continue
            master_val = p.get(rule.master_param, 0)
            if master_val == 0:
                continue
            current_val = p.get(param_key, 0)
            if current_val == 0:
                continue
            try:
                lo, hi = rule.compute_range(master_val, p)
            except Exception:
                continue
            if lo > hi:
                continue  # 无效范围，跳过
            if current_val < lo or current_val > hi:
                fixed = max(lo, min(hi, current_val))
                p[param_key] = round(fixed, 2)
                report.append(
                    f"{comp_id}.{param_key}: {current_val:.2f} → {fixed:.2f} "
                    f"(规则范围 [{lo:.1f}, {hi:.1f}])"
                )

    # --- Step 3: CrossComponentDerived 约束校验 ---
    # 只应用正向约束（按生成顺序：bottle→cap→wand→wiper）
    # 反向约束（如 cap→bottle）跳过，避免修改用户指定的上游参数
    _GEN_ORDER = {"bottle": 0, "cap": 1, "wand": 2, "wiper": 3}
    for rule in CROSS_COMPONENT_RULES:
        src_ord = _GEN_ORDER.get(rule.source_component, -1)
        tgt_ord = _GEN_ORDER.get(rule.target_component, -1)
        if src_ord >= tgt_ord:
            continue  # 跳过反向/同级约束
        src_p = all_params.get(rule.source_component, {})
        tgt_p = all_params.get(rule.target_component, {})
        src_val = src_p.get(rule.source_param)
        if src_val is None:
            continue
        tgt_val = tgt_p.get(rule.target_param)
        if tgt_val is None:
            continue
        try:
            lo, hi = rule.compute_range(src_val, src_p)
        except Exception:
            continue
        if lo > hi:
            continue  # 约束区间无效（几何上不可能），跳过
        if tgt_val < lo or tgt_val > hi:
            try:
                fixed = rule.compute_default(src_val, src_p)
            except Exception:
                fixed = (lo + hi) / 2.0
            fixed = max(lo, min(hi, fixed))
            if isinstance(fixed, (int, float)):
                tgt_p[rule.target_param] = round(fixed, 2)
                report.append(
                    f"跨组件 {rule.source_component}.{rule.source_param}={src_val:.1f} "
                    f"→ {rule.target_component}.{rule.target_param}: "
                    f"{tgt_val:.2f} → {fixed:.2f} "
                    f"(范围 [{lo:.1f}, {hi:.1f}])"
                )
            else:
                # 字符串类参数（如 finish）直接赋值，不 round
                tgt_p[rule.target_param] = fixed
                report.append(
                    f"跨组件 {rule.source_component}.{rule.source_param}={src_val} "
                    f"→ {rule.target_component}.{rule.target_param}: "
                    f"{tgt_val} → {fixed}"
                )

    # --- Step 3.5: 螺纹可行性守卫 ---
    # 如果 F2 规则强制的 crest_dia 导致建模器会膨胀 outer_od，
    # 则回退 crest_dia 到 outer_od 能容纳的最大值，并同步 bottle.neck_od
    wand_p = all_params.get("wand", {})
    thr_on = wand_p.get("thread.enabled", True)
    if thr_on:
        wand_od = wand_p.get("outer_od_mm", 20)
        crest = wand_p.get("thread.crest_dia_mm", 18)
        depth = wand_p.get("thread.depth_mm", 0.5)
        # 建模器公式: min_outer_od = crest + 2*(depth + 0.5 + 1.0)
        min_wall_total = depth + 0.5 + 1.0
        min_outer_od = crest + 2 * min_wall_total
        if min_outer_od > wand_od:
            max_crest = wand_od - 2 * min_wall_total
            if max_crest >= 10.0:
                old_crest = crest
                new_crest = round(max_crest, 2)
                wand_p["thread.crest_dia_mm"] = new_crest
                # 同步 finish 规格（扁平格式，_fix_finish_spec 可能读不到）
                new_finish_dia = str(int(round(new_crest)))
                old_finish = str(wand_p.get("finish", "18-415"))
                try:
                    parts = old_finish.split("-")
                    parts[0] = new_finish_dia
                    wand_p["finish"] = "-".join(parts)
                except Exception:
                    pass
                # 同步 bottle.neck_od + bottle.finish 以保持螺纹互锁
                bottle_p = all_params.get("bottle", {})
                old_neck = bottle_p.get("neck_od_mm", crest)
                if old_neck > new_crest + 0.5:
                    bottle_p["neck_od_mm"] = round(new_crest, 1)
                    # 同步 bottle 的 finish
                    old_b_finish = str(bottle_p.get("finish", "18-415"))
                    try:
                        b_parts = old_b_finish.split("-")
                        b_parts[0] = new_finish_dia
                        bottle_p["finish"] = "-".join(b_parts)
                    except Exception:
                        pass
                    report.append(
                        f"螺纹守卫: bottle.neck_od {old_neck:.1f}→{new_crest:.1f} "
                        f"(同步缩径)")
                report.append(
                    f"螺纹守卫: wand.thread.crest_dia {old_crest:.1f}→{new_crest:.2f} "
                    f"(outer_od={wand_od:.1f}mm 容量限制)")
            else:
                wand_p["thread.enabled"] = False
                report.append(
                    f"螺纹守卫: 禁用wand螺纹 "
                    f"(max_crest={max_crest:.1f}mm < 10mm)")

    # --- Step 3.6: Cap-Wand 容纳守卫 ---
    # Step 3 的规则执行顺序问题：A1(cap→wand) 可能在 B4(bottle→cap) 之前执行，
    # 导致 wand.outer_od 基于未修正的 cap.inner_id。此处做最终容纳校验。
    cap_inner_final = all_params.get("cap", {}).get("inner_id_mm")
    wand_od_final = wand_p.get("outer_od_mm")
    if cap_inner_final is not None and wand_od_final is not None:
        if wand_od_final > cap_inner_final - 0.5:
            new_wand_od = round(cap_inner_final - 0.9, 1)
            new_wand_od = max(10.0, new_wand_od)  # 下限保护
            report.append(
                f"容纳守卫: wand.outer_od {wand_od_final:.1f}→{new_wand_od:.1f} "
                f"(cap.inner_id={cap_inner_final:.1f}mm)")
            wand_p["outer_od_mm"] = new_wand_od
            # 同步 outer_od 的派生参数
            old_seal = wand_p.get("seal_ring.od_mm", wand_od_final - 5.5)
            new_seal = round(new_wand_od - 5.5, 1)
            new_seal = max(8.0, new_seal)
            wand_p["seal_ring.od_mm"] = new_seal
            # 如果 outer_od 缩小了，可能需要重新检查螺纹可行性
            thr_on2 = wand_p.get("thread.enabled", True)
            if thr_on2:
                crest2 = wand_p.get("thread.crest_dia_mm", 18)
                depth2 = wand_p.get("thread.depth_mm", 0.5)
                min_wall2 = depth2 + 0.5 + 1.0
                if crest2 + 2 * min_wall2 > new_wand_od:
                    max_crest2 = new_wand_od - 2 * min_wall2
                    if max_crest2 >= 10.0:
                        wand_p["thread.crest_dia_mm"] = round(max_crest2, 2)
                        report.append(
                            f"容纳守卫: wand.crest_dia {crest2:.1f}→{max_crest2:.2f} "
                            f"(缩径后螺纹调整)")
                    else:
                        wand_p["thread.enabled"] = False
                        report.append(
                            f"容纳守卫: 禁用wand螺纹 (max_crest={max_crest2:.1f}mm)")

    # --- Step 4: 几何可行性守卫 — 锥度 × 高度 → 顶部退化检查 ---
    cap_p = all_params.get("cap", {})
    cap_od = cap_p.get("outer_od_mm", 20)
    cap_h = cap_p.get("height_mm", 30)
    cap_taper = cap_p.get("taper_deg", 0)
    cs = cap_p.get("cross_section", "round")

    if cap_taper > 0 and cap_h > 0:
        cap_top_od = cap_od - 2 * math.tan(math.radians(cap_taper)) * cap_h
        min_top = 10.0 if cs == "square" else (8.0 if cs != "round" else 6.0)
        if cap_top_od < min_top:
            safe_taper = math.degrees(math.atan((cap_od - min_top) / (2 * cap_h)))
            safe_taper = round(max(0.5, safe_taper), 1)
            cap_p["taper_deg"] = safe_taper
            report.append(
                f"cap.taper_deg: {cap_taper:.1f}→{safe_taper:.1f} "
                f"(顶部{cap_top_od:.1f}mm<{min_top}mm)"
            )

    # --- Step 5: 安全下限守卫 — 确保核心参数不低于 ParamDef 最小值 ---
    # 当 CV 推算值过小或跨组件约束压缩导致参数低于建模器最小值时，
    # 强制夹紧到安全下限，避免 normalize_strict 硬约束失败。
    _CORE_MINS = {
        "bottle": {"body_od_mm": 12.0, "height_mm": 15.0, "neck_od_mm": 10.0,
                   "neck_height_mm": 4.0},
        "cap":    {"outer_od_mm": 12.0, "height_mm": 10.0},
        "wand":   {"outer_od_mm": 10.0, "cap_height_mm": 8.0,
                   "total_height_mm": 40.0},
        "wiper":  {"outer_od_mm": 8.0, "height_mm": 4.0},
    }
    for comp_id, mins in _CORE_MINS.items():
        p = all_params.get(comp_id, {})
        for k, min_val in mins.items():
            cur = p.get(k)
            if cur is not None and isinstance(cur, (int, float)) and cur < min_val:
                p[k] = min_val
                report.append(
                    f"安全下限: {comp_id}.{k}: {cur:.1f} → {min_val:.1f}"
                )

    # 补充校验：cap 派生参数一致性
    cap_p2 = all_params.get("cap", {})
    cap_od2 = cap_p2.get("outer_od_mm", 20)
    cap_h2 = cap_p2.get("height_mm", 25)
    cap_iid = cap_p2.get("inner_id_mm", 18)
    cap_cav = cap_p2.get("cavity_depth_mm", 20)
    # inner_id < outer_od（壁厚合理性）
    if cap_od2 <= cap_iid:
        cap_p2["inner_id_mm"] = round(cap_od2 - 1.6, 1)
        report.append(
            f"安全下限: cap.inner_id: {cap_iid:.1f} → {cap_p2['inner_id_mm']:.1f} "
            f"(需 < outer_od={cap_od2:.1f})"
        )
    # cavity_depth < height（腔深不超总高）
    if cap_cav >= cap_h2:
        cap_p2["cavity_depth_mm"] = round(cap_h2 - 1.5, 1)
        report.append(
            f"安全下限: cap.cavity_depth: {cap_cav:.1f} → {cap_p2['cavity_depth_mm']:.1f} "
            f"(需 < height={cap_h2:.1f})"
        )

    # 补充校验：wiper 派生参数一致性
    # 跨组件约束可能缩小 outer_od/flange_od 而不更新 inner_id/flange_id
    wiper_p = all_params.get("wiper", {})
    wp_od = wiper_p.get("outer_od_mm", 15)
    wp_iid = wiper_p.get("inner_id_mm", 13)
    wp_flange = wiper_p.get("flange_od_mm", 17)
    wp_flange_id = wiper_p.get("flange_id_mm", 14)
    # flange_od >= outer_od
    if wp_flange < wp_od:
        wiper_p["flange_od_mm"] = round(wp_od + 1.5, 1)
        wp_flange = wiper_p["flange_od_mm"]
        report.append(
            f"安全下限: wiper.flange_od → {wp_flange:.1f} (需 >= outer_od={wp_od:.1f})"
        )
    # inner_id 重算（确保壁厚 >= 0.5mm）
    if (wp_od - wp_iid) / 2 < 0.5:
        wiper_p["inner_id_mm"] = round(wp_od - 2.0, 1)
        wp_iid = wiper_p["inner_id_mm"]
        report.append(
            f"安全下限: wiper.inner_id → {wp_iid:.1f} (壁厚需 >= 0.5mm)"
        )
    # flange_id < flange_od
    if wp_flange_id >= wp_flange:
        wiper_p["flange_id_mm"] = round(wp_flange - 1.0, 1)
        report.append(
            f"安全下限: wiper.flange_id → {wiper_p['flange_id_mm']:.1f} "
            f"(需 < flange_od={wp_flange:.1f})"
        )

    return all_params, report


# ════════════════════════════════════════════════════════════════════════
# 公共入口
# ════════════════════════════════════════════════════════════════════════

def extract_and_build_all(
    image_b64: str,
    user_dims: dict,
    on_progress: Callable[[str, str, str], None] | None = None,
) -> dict:
    """
    完整流程：VLM 两步提取 → 4 组件参数合成

    on_progress(step_id, status, message) 回调用于 SSE 推送进度。

    返回:
    {
        "description": str,
        "vlm_shape": dict,
        "bottle": dict,
        "cap": dict,
        "wand": dict,
        "wiper": dict,
    }
    """
    def emit(step_id: str, status: str, msg: str):
        if on_progress:
            on_progress(step_id, status, msg)

    # Step 1: VLM 描述
    emit("vlm_describe", "running", "AI 正在识别瓶身+瓶盖外形...")
    description = vlm_describe(image_b64)
    emit("vlm_describe", "done", description[:100])

    # Step 2: VLM 提取形状（纯文本，不重传图片）
    emit("vlm_extract", "running", "正在提取形状参数...")
    vlm_shape = vlm_extract_shape(description, user_dims)
    shape_desc = vlm_shape.get("shape_description", "")
    emit("vlm_extract", "done", shape_desc or "提取完成")

    # Step 3: 合成参数
    emit("params", "running", "正在合成 4 组件参数...")
    bottle_p = build_bottle_params(user_dims, vlm_shape)
    cap_p = derive_cap_params(bottle_p, vlm_shape)
    wand_p = derive_wand_params(cap_p, bottle_p)
    wiper_p = derive_wiper_params(bottle_p, wand_p)

    # Step 4: 全局协调（复用 DerivedRule + CrossComponentDerived 规则）
    emit("reconcile", "running", "正在校验跨组件约束...")
    all_p = {"bottle": bottle_p, "cap": cap_p, "wand": wand_p, "wiper": wiper_p}
    all_p, reconcile_report = reconcile_all_params(all_p)
    if reconcile_report:
        emit("reconcile", "done", f"已修正 {len(reconcile_report)} 项参数")
    else:
        emit("reconcile", "done", "所有参数一致，无需修正")

    return {
        "description": description,
        "vlm_shape": vlm_shape,
        "bottle": all_p["bottle"],
        "cap": all_p["cap"],
        "wand": all_p["wand"],
        "wiper": all_p["wiper"],
        "reconcile_report": reconcile_report,
    }
