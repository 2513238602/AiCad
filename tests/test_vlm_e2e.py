# -*- coding: utf-8 -*-
"""
VLM 图片→参数→生成 端到端测试

测试流程：
1. 下载多种唇釉瓶产品图片（不同造型）
2. 发送给 GLM-4V 提取参数
3. 对参数进行 AiCad 约束验证（范围、派生规则、QC）
4. 调用 AiCad 后端生成 3D 模型
5. 评估外形相似度 & 内部装配结构完整性

用法：
    python tests/test_vlm_e2e.py [--server http://localhost:9876]
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os
import sys
import time
import urllib.request
import urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ════════════════════════════════════════════════════════════════════════
# 配置
# ════════════════════════════════════════════════════════════════════════

GLM_API_KEY = os.environ.get("GLM_API_KEY", "0d44fbe7c576473c8d89b85046b1edc3.MWR2xsYm7EIVbpZW")
GLM_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
GLM_MODEL = "glm-4.6v"

# AiCad 瓶身参数有效范围（来自 bottle.py ParamDef）
BOTTLE_SCHEMA = {
    "height_mm":          {"min": 30.0, "max": 150.0, "default": 70.0},
    "body_od_mm":         {"min": 12.0, "max": 45.0,  "default": 24.0},
    "neck_od_mm":         {"min": 10.0, "max": 32.0,  "default": 18.0},
    "neck_height_mm":     {"min": 4.0,  "max": 25.0,  "default": 10.0},
    "lip_thickness_mm":   {"min": 0.5,  "max": 2.5,   "default": 1.0},
    "shoulder_height_mm": {"min": 2.0,  "max": 30.0,  "default": 10.0},
    "wall_thickness_mm":  {"min": 0.8,  "max": 3.0,   "default": 1.2},
    "bottom_thickness_mm":{"min": 1.0,  "max": 8.0,   "default": 2.0},
    "shoulder_fillet_mm": {"min": 0.0,  "max": 15.0,  "default": 3.0},
    "taper_deg":          {"min": 0.0,  "max": 8.0,   "default": 0.0},
}

VALID_SHAPES = ["cyl", "taper"]
VALID_SHOULDERS = ["round", "angular", "sloped"]
VALID_PROFILES = ["classic", "spline"]
VALID_BOTTOMS = ["flat", "concave", "convex"]

# 测试图片集（覆盖多种造型）
TEST_IMAGES = [
    {
        "id": "T1_cylindrical_standard",
        "desc": "标准圆柱形唇釉瓶，黑色盖透明瓶身",
        "url": "https://cdn.globalso.com/bmeipackaging/DSC_3559_%E5%89%AF%E6%9C%AC1.jpg",
        "expected_shape": "cyl",
        "expected_height_range": (60, 90),
        "expected_od_range": (20, 30),
    },
    {
        "id": "T2_cute_round",
        "desc": "可爱粉色圆润造型唇釉瓶",
        "url": "https://cdn.globalso.com/bmeipackaging/cute-lip-loss-tube-1.jpg",
        "expected_shape": "cyl",
        "expected_height_range": (40, 70),
        "expected_od_range": (18, 35),
    },
    {
        "id": "T3_mini_chubby",
        "desc": "迷你胖瓶身 2ml 试用装唇釉",
        "url": "https://cdn.globalso.com/bmeipackaging/5062-2.jpg",
        "expected_shape": "cyl",
        "expected_height_range": (30, 60),
        "expected_od_range": (15, 30),
    },
    {
        "id": "T4_bowling_shape",
        "desc": "保龄球造型异形唇釉瓶，透明3.5ml",
        "url": "https://cdn.globalso.com/bmeipackaging/5105B-07.png",
        "expected_shape": "cyl",  # 异形，可能提取为 spline
        "expected_height_range": (40, 80),
        "expected_od_range": (15, 35),
    },
    {
        "id": "T5_square_double",
        "desc": "方形双色注塑唇釉瓶",
        "url": "https://cdn.globalso.com/bmeipackaging/1600X1000%E9%AB%98-1_%E5%89%AF%E6%9C%AC.jpg",
        "expected_shape": "cyl",  # 方形超出当前系统支持范围
        "expected_height_range": (50, 90),
        "expected_od_range": (15, 35),
    },
    {
        "id": "T6_frosted_slim",
        "desc": "磨砂质感细长型唇釉管",
        "url": "https://ijrorwxhnlqrln5p.ldycdn.com/cloud/lpBpqKkrlkSRjljprrmoio/BM51-640-640.jpg?v=1",
        "expected_shape": "cyl",
        "expected_height_range": (60, 100),
        "expected_od_range": (14, 25),
    },
]

# ════════════════════════════════════════════════════════════════════════
# VLM 提取 Prompt
# ════════════════════════════════════════════════════════════════════════

EXTRACT_PROMPT = '''你是专业的化妆品包装工程师，擅长从产品图片中估算唇釉瓶（lip gloss tube）的尺寸参数。

请根据图片估算该唇釉**瓶身**（不含瓶盖）的参数。如果图中包含瓶盖，请只估算瓶身部分。

请严格按以下 JSON 格式输出，不要输出任何其他内容：
{
  "height_mm": <瓶身总高，含颈部，float，范围30-150>,
  "body_od_mm": <瓶身最大外径，float，范围12-45>,
  "neck_od_mm": <口部/颈部外径，float，范围10-32>,
  "neck_height_mm": <颈部高度，float，范围4-25>,
  "shape": <"cyl"=圆柱 或 "taper"=锥形>,
  "taper_deg": <锥度角，float，0表示直筒>,
  "shoulder_style": <"round"=圆弧 或 "angular"=折角 或 "sloped"=斜面>,
  "shoulder_fillet_mm": <肩部圆角半径，float，0-15>,
  "bottom_style": <"flat"=平底 或 "concave"=内凹 或 "convex"=外凸>,
  "profile_mode": <"classic"=标准轮廓 或 "spline"=自由曲线轮廓>,
  "profile_points": <如果瓶身有特殊曲线(非直筒/锥形)，提供[r,z]控制点数组；否则为[]>,
  "lip_thickness_mm": <唇口壁厚，float，0.5-2.5>,
  "wall_thickness_mm": <估算壁厚，float，0.8-3.0>,
  "confidence": <你对这次估算的置信度，0.0-1.0>,
  "shape_description": <一句话描述瓶身外形特征>
}

注意事项：
1. 尺寸单位为 mm，请根据唇釉瓶的常见尺寸范围合理估算
2. 普通唇釉瓶总高约60-90mm，外径约20-28mm，口径约16-20mm
3. 如果看不清某个参数，使用合理的默认值
4. profile_points 中的 r 是半径（不是直径），z 是从底部向上的高度'''


# ════════════════════════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════════════════════════

def download_image(url: str, save_dir: str = "tests/picture") -> tuple[str, str]:
    """下载图片并返回 (本地路径, base64编码)"""
    os.makedirs(save_dir, exist_ok=True)
    # 安全文件名: 取 URL 末段并去除特殊字符
    fname = url.split("/")[-1].split("?")[0]
    # URL-decode 然后替换不安全字符
    fname = urllib.request.unquote(fname)
    fname = fname.replace("%", "_").replace(" ", "_")
    # 只保留 ASCII 安全字符
    safe_fname = "".join(c if c.isalnum() or c in ".-_" else "_" for c in fname)
    if not safe_fname:
        safe_fname = "image.jpg"
    local_path = os.path.join(save_dir, safe_fname)

    if not os.path.exists(local_path):
        print(f"  下载: {url[:80]}...")
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            with open(local_path, "wb") as f:
                f.write(data)
            print(f"  已保存: {local_path} ({len(data)} bytes)")
        except Exception as e:
            print(f"  下载失败: {e}")
            return "", ""
    else:
        print(f"  使用缓存: {local_path}")
        with open(local_path, "rb") as f:
            data = f.read()

    # 压缩大图片以避免 GLM API base64 超时
    data, ext = _compress_image(data, max_size_kb=500, max_dim=800)
    b64 = base64.b64encode(data).decode("utf-8")
    return local_path, b64


def _compress_image(data: bytes, max_size_kb: int = 500, max_dim: int = 800) -> tuple[bytes, str]:
    """压缩图片至合理大小，返回 (compressed_bytes, format_ext)"""
    if len(data) <= max_size_kb * 1024:
        # 判断格式
        ext = "jpeg"
        if data[:4] == b"\x89PNG":
            ext = "png"
        return data, ext

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        # 转 RGB（去掉 alpha）
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        # 缩小
        w, h = img.size
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        # 压缩为 JPEG
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        compressed = buf.getvalue()
        print(f"  图片压缩: {len(data)//1024}KB → {len(compressed)//1024}KB ({img.size[0]}x{img.size[1]})")
        return compressed, "jpeg"
    except ImportError:
        return data, "jpeg"


def call_glm_vision(image_b64: str, image_url: str = "") -> dict | None:
    """调用 GLM-4V 识别图片并提取参数"""
    # 始终使用 base64 方式（避免 CDN referer 限制导致 400 错误）
    if not image_b64:
        return None
    ext = "jpeg"
    if image_b64[:4] == "iVBO":
        ext = "png"
    image_content = {
        "type": "image_url",
        "image_url": {"url": f"data:image/{ext};base64,{image_b64}"}
    }

    payload = json.dumps({
        "model": GLM_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                image_content,
                {"type": "text", "text": EXTRACT_PROMPT}
            ]
        }],
        "max_tokens": 800,
        "temperature": 0.1
    }).encode("utf-8")

    req = urllib.request.Request(GLM_API_URL, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GLM_API_KEY}"
    })

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        reply = result["choices"][0]["message"]["content"]
        return _parse_json_reply(reply)
    except Exception as e:
        print(f"  GLM API 调用失败: {e}")
        return None


def _parse_json_reply(text: str) -> dict | None:
    """从 GLM 回复中提取 JSON"""
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                text = part
                break
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试找到第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end+1])
            except json.JSONDecodeError:
                pass
        print(f"  JSON 解析失败: {text[:200]}")
        return None


# ════════════════════════════════════════════════════════════════════════
# 参数验证
# ════════════════════════════════════════════════════════════════════════

def validate_params(extracted: dict) -> dict:
    """验证提取的参数是否在 AiCad 有效范围内"""
    issues = []
    warnings = []
    fixed = {}

    # 1. 检查必要字段
    required_keys = ["height_mm", "body_od_mm", "neck_od_mm"]
    for k in required_keys:
        if k not in extracted:
            issues.append(f"缺少必要参数: {k}")

    # 2. 范围检查 & 自动修正
    for k, schema in BOTTLE_SCHEMA.items():
        val = extracted.get(k)
        if val is None:
            fixed[k] = schema["default"]
            warnings.append(f"{k}: 未提取到，使用默认值 {schema['default']}")
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            fixed[k] = schema["default"]
            warnings.append(f"{k}: 值无效({extracted[k]})，使用默认值")
            continue

        if val < schema["min"]:
            fixed[k] = schema["min"]
            warnings.append(f"{k}: {val} < 最小值 {schema['min']}，已修正")
        elif val > schema["max"]:
            fixed[k] = schema["max"]
            warnings.append(f"{k}: {val} > 最大值 {schema['max']}，已修正")
        else:
            fixed[k] = val

    # 3. 枚举检查
    shape = extracted.get("shape", "cyl")
    if shape not in VALID_SHAPES:
        warnings.append(f"shape: '{shape}' 不支持，修正为 'cyl'")
        shape = "cyl"
    fixed["shape"] = shape

    shoulder = extracted.get("shoulder_style", "round")
    if shoulder not in VALID_SHOULDERS:
        warnings.append(f"shoulder_style: '{shoulder}' 不支持，修正为 'round'")
        shoulder = "round"
    fixed["shoulder_style"] = shoulder

    profile_mode = extracted.get("profile_mode", "classic")
    if profile_mode not in VALID_PROFILES:
        profile_mode = "classic"
    fixed["profile_mode"] = profile_mode

    bottom_style = extracted.get("bottom_style", "flat")
    if bottom_style not in VALID_BOTTOMS:
        bottom_style = "flat"
    fixed["bottom_style"] = bottom_style

    # 4. 几何一致性检查
    h = fixed.get("height_mm", 70)
    od = fixed.get("body_od_mm", 24)
    nod = fixed.get("neck_od_mm", 18)
    nh = fixed.get("neck_height_mm", 10)
    sh = fixed.get("shoulder_height_mm", 10)

    if nod >= od:
        issues.append(f"颈径({nod}) >= 瓶身外径({od})，不合理")
        fixed["neck_od_mm"] = od - 4.0
        warnings.append(f"neck_od_mm 修正为 {fixed['neck_od_mm']}")

    if nh + sh > h * 0.8:
        warnings.append(f"颈高({nh})+肩高({sh}) 占总高({h})的 {(nh+sh)/h*100:.0f}%，比例偏高")

    # 5. 派生参数计算（模拟后端逻辑）
    # 内深 = 总高 - 底厚 - 颈高 * 0.3
    bt = fixed.get("bottom_thickness_mm", 2.0)
    inner_depth = h - bt - nh * 0.3
    if inner_depth < 20:
        warnings.append(f"计算内深({inner_depth:.1f}mm)偏小，可能容量不足")

    # 壁厚
    wt = fixed.get("wall_thickness_mm", 1.2)
    inner_r = od / 2 - wt
    if inner_r <= 0:
        issues.append(f"壁厚({wt})过大，内径为负")

    # 容量估算 (圆柱近似)
    capacity_ml = math.pi * (inner_r ** 2) * inner_depth / 1000
    fixed["_estimated_capacity_ml"] = round(capacity_ml, 2)

    # 6. Profile points 处理
    pts = extracted.get("profile_points", [])
    if pts and isinstance(pts, list) and len(pts) >= 3:
        fixed["profile_mode"] = "spline"
        fixed["profile_points_json"] = json.dumps(pts)
        warnings.append(f"检测到 {len(pts)} 个轮廓控制点，设为 spline 模式")
    else:
        fixed["profile_points_json"] = "[]"

    return {
        "fixed_params": fixed,
        "issues": issues,
        "warnings": warnings,
        "is_valid": len(issues) == 0,
    }


# ════════════════════════════════════════════════════════════════════════
# 装配结构验证
# ════════════════════════════════════════════════════════════════════════

def check_assembly_structure(params: dict) -> dict:
    """检查参数是否能支持完整的内部装配结构"""
    checks = []
    h = params.get("height_mm", 70)
    od = params.get("body_od_mm", 24)
    nod = params.get("neck_od_mm", 18)
    nh = params.get("neck_height_mm", 10)
    wt = params.get("wall_thickness_mm", 1.2)

    # 1. 瓶盖配合：瓶盖外径 ≈ 瓶身外径
    cap_od = od  # 常规设计: cap.outer_od == bottle.body_od
    cap_inner_id = cap_od - 1.6  # 派生：内径 = 外径 - 2*壁厚(0.8)
    checks.append({
        "item": "瓶盖配合",
        "desc": f"瓶盖外径={cap_od:.1f}, 内径={cap_inner_id:.1f}",
        "pass": cap_inner_id > nod,
        "note": f"内径须 > 颈径({nod})" if cap_inner_id <= nod else "OK",
    })

    # 2. 刷杆配合：wand.outer_od = cap.inner_id - 0.9
    wand_od = cap_inner_id - 0.9
    checks.append({
        "item": "刷杆配合",
        "desc": f"刷杆外径={wand_od:.1f} (盖内径{cap_inner_id:.1f}-0.9)",
        "pass": wand_od >= 10,
        "note": f"刷杆外径须 >= 10mm" if wand_od < 10 else "OK",
    })

    # 3. 刷杆杆径：rod_dia = wand_od * 0.2 (约)
    rod_dia = max(wand_od * 0.2, 2.0)
    checks.append({
        "item": "刷杆杆径",
        "desc": f"杆径≈{rod_dia:.1f}mm",
        "pass": rod_dia >= 1.5,
        "note": "OK",
    })

    # 4. 刮片配合：wiper.outer_od ≈ nod（安装在瓶口）
    wiper_od = nod
    wiper_hole = rod_dia + 0.3
    checks.append({
        "item": "刮片配合",
        "desc": f"刮片外径={wiper_od:.1f}, 孔径={wiper_hole:.1f}",
        "pass": wiper_od > wiper_hole + 2,
        "note": "OK" if wiper_od > wiper_hole + 2 else "刮片壁太薄",
    })

    # 5. 瓶身内腔容积
    inner_r = od / 2 - wt
    bt = params.get("bottom_thickness_mm", 2.0)
    inner_depth = h - bt - nh * 0.3
    capacity = math.pi * (inner_r ** 2) * inner_depth / 1000
    checks.append({
        "item": "内腔容量",
        "desc": f"≈{capacity:.1f}ml (内径{inner_r*2:.1f}, 深{inner_depth:.1f})",
        "pass": 0.5 <= capacity <= 35.0,
        "note": "OK" if 0.5 <= capacity <= 35.0 else "容量异常",
    })

    # 6. 螺纹空间：颈高须 >= 螺纹所需高度(pitch*turns+2)
    min_thread_h = 2.7 * 2 + 2  # pitch=2.7, turns=2, 余量=2
    checks.append({
        "item": "螺纹空间",
        "desc": f"颈高={nh:.1f}, 螺纹需≥{min_thread_h:.1f}",
        "pass": nh >= min_thread_h,
        "note": "OK" if nh >= min_thread_h else f"颈高不足，需≥{min_thread_h:.1f}mm",
    })

    # 7. 肩部过渡可行性
    sh = params.get("shoulder_height_mm", 10)
    radius_diff = (od - nod) / 2
    checks.append({
        "item": "肩部过渡",
        "desc": f"半径差={radius_diff:.1f}, 肩高={sh:.1f}",
        "pass": sh >= radius_diff * 0.5,
        "note": "OK" if sh >= radius_diff * 0.5 else "肩高不足以完成过渡",
    })

    pass_count = sum(1 for c in checks if c["pass"])
    total = len(checks)

    return {
        "checks": checks,
        "pass_count": pass_count,
        "total": total,
        "all_pass": pass_count == total,
        "score": pass_count / total if total > 0 else 0,
    }


# ════════════════════════════════════════════════════════════════════════
# 外形相似度评估
# ════════════════════════════════════════════════════════════════════════

def evaluate_shape_similarity(extracted: dict, expected: dict) -> dict:
    """评估提取参数与预期外形的匹配度"""
    scores = {}

    # 1. 形状匹配
    shape_match = extracted.get("shape") == expected.get("expected_shape")
    scores["shape_match"] = 1.0 if shape_match else 0.3

    # 2. 高度范围匹配
    h = extracted.get("height_mm", 70)
    h_range = expected.get("expected_height_range", (60, 90))
    if h_range[0] <= h <= h_range[1]:
        scores["height_score"] = 1.0
    else:
        dist = min(abs(h - h_range[0]), abs(h - h_range[1]))
        scores["height_score"] = max(0, 1.0 - dist / 30)

    # 3. 外径范围匹配
    od = extracted.get("body_od_mm", 24)
    od_range = expected.get("expected_od_range", (20, 30))
    if od_range[0] <= od <= od_range[1]:
        scores["od_score"] = 1.0
    else:
        dist = min(abs(od - od_range[0]), abs(od - od_range[1]))
        scores["od_score"] = max(0, 1.0 - dist / 15)

    # 4. 长径比合理性
    ratio = h / od if od > 0 else 0
    # 唇釉瓶常见长径比 2.5-4.5
    if 2.0 <= ratio <= 5.0:
        scores["ratio_score"] = 1.0
    else:
        scores["ratio_score"] = 0.5

    # 5. VLM 自身置信度
    confidence = extracted.get("confidence", 0.5)
    scores["vlm_confidence"] = confidence

    # 综合分
    weights = {
        "shape_match": 0.15,
        "height_score": 0.25,
        "od_score": 0.25,
        "ratio_score": 0.15,
        "vlm_confidence": 0.20,
    }
    total = sum(scores[k] * weights[k] for k in weights)
    scores["overall"] = round(total, 3)

    return scores


# ════════════════════════════════════════════════════════════════════════
# AiCad 后端生成调用
# ════════════════════════════════════════════════════════════════════════

def try_generate(params: dict, server_url: str) -> dict | None:
    """尝试调用 AiCad 后端生成瓶身"""
    # 构建生成请求
    gen_params = {
        "height_mm": params.get("height_mm", 70),
        "body_od_mm": params.get("body_od_mm", 24),
        "neck_od_mm": params.get("neck_od_mm", 18),
        "neck_height_mm": params.get("neck_height_mm", 10),
        "lip_thickness_mm": params.get("lip_thickness_mm", 1.0),
        "shape": params.get("shape", "cyl"),
        "taper_deg": params.get("taper_deg", 0.0),
        "shoulder_style": params.get("shoulder_style", "round"),
        "shoulder_fillet_mm": params.get("shoulder_fillet_mm", 3.0),
        "bottom_style": params.get("bottom_style", "flat"),
        "bottom_thickness_mm": params.get("bottom_thickness_mm", 2.0),
        "bottom_concave_mm": 1.0,
        "bottom_fillet_mm": 1.5,
        "wall_thickness_mm": params.get("wall_thickness_mm", 1.2),
        "profile_mode": params.get("profile_mode", "classic"),
        "profile_points_json": params.get("profile_points_json", "[]"),
        "profile_symmetry": "symmetric",
        "profile_b_points_json": "[]",
        "finish": f"{int(round(params.get('neck_od_mm', 18)))}-415",
        "cap_clearance_mm": 0.2,
        "thread.enabled": True,
        "thread.pitch_mm": 2.7,
        "thread.turns": 2,
        "thread.depth_mm": 0.5,
        "thread.lead_angle_deg": 3.0,
        "thread.segmented": False,
        "thread.gap_angle_deg": 20.0,
    }

    body = json.dumps({
        "product": "lip_gloss",
        "component": "bottle",
        "params": gen_params,
        "title": "VLM_test",
    }).encode("utf-8")

    url = f"{server_url}/api/generate"
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
    })

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return result
    except urllib.error.URLError as e:
        return {"error": f"连接失败: {e}"}
    except Exception as e:
        return {"error": str(e)}


# ════════════════════════════════════════════════════════════════════════
# 主测试流程
# ════════════════════════════════════════════════════════════════════════

def run_single_test(img_info: dict, server_url: str | None) -> dict:
    """运行单个图片的完整测试"""
    result = {
        "id": img_info["id"],
        "desc": img_info["desc"],
        "url": img_info["url"],
    }

    print(f"\n{'='*60}")
    print(f"测试: {img_info['id']} - {img_info['desc']}")
    print(f"{'='*60}")

    # Step 1: 下载图片
    print("\n[1/5] 下载图片...")
    local_path, b64 = download_image(img_info["url"])
    if not b64:
        result["status"] = "SKIP"
        result["error"] = "图片下载失败"
        return result
    result["local_path"] = local_path

    # Step 2: VLM 参数提取
    print("\n[2/5] GLM-4V 参数提取...")
    t0 = time.time()
    extracted = call_glm_vision(b64, img_info["url"])
    t_vlm = time.time() - t0
    result["vlm_time_s"] = round(t_vlm, 2)

    if extracted is None:
        result["status"] = "FAIL"
        result["error"] = "VLM 参数提取失败"
        return result

    print(f"  提取耗时: {t_vlm:.1f}s")
    print(f"  提取结果: {json.dumps(extracted, ensure_ascii=False, indent=2)}")
    result["extracted_params"] = extracted

    # Step 3: 参数验证
    print("\n[3/5] 参数验证...")
    validation = validate_params(extracted)
    result["validation"] = validation
    print(f"  有效: {validation['is_valid']}")
    if validation["issues"]:
        print(f"  问题: {validation['issues']}")
    if validation["warnings"]:
        for w in validation["warnings"]:
            print(f"  警告: {w}")

    # Step 4: 装配结构检查
    print("\n[4/5] 装配结构检查...")
    assembly = check_assembly_structure(validation["fixed_params"])
    result["assembly"] = assembly
    for chk in assembly["checks"]:
        status = "✓" if chk["pass"] else "✗"
        print(f"  {status} {chk['item']}: {chk['desc']} — {chk['note']}")
    print(f"  通过率: {assembly['pass_count']}/{assembly['total']}")

    # Step 5: 外形相似度
    print("\n[5/5] 外形相似度评估...")
    similarity = evaluate_shape_similarity(extracted, img_info)
    result["similarity"] = similarity
    print(f"  形状匹配: {similarity['shape_match']:.0%}")
    print(f"  高度评分: {similarity['height_score']:.0%}")
    print(f"  外径评分: {similarity['od_score']:.0%}")
    print(f"  长径比:   {similarity['ratio_score']:.0%}")
    print(f"  VLM置信:  {similarity['vlm_confidence']:.0%}")
    print(f"  综合相似度: {similarity['overall']:.1%}")

    # Step 6: 后端生成（可选）
    if server_url:
        print("\n[+] 尝试后端生成...")
        t0 = time.time()
        gen_result = try_generate(validation["fixed_params"], server_url)
        t_gen = time.time() - t0
        result["generate_time_s"] = round(t_gen, 2)
        result["generate_result"] = gen_result

        if gen_result and "error" not in gen_result:
            print(f"  生成成功! 耗时 {t_gen:.1f}s")
            qc = gen_result.get("qc", {})
            if qc:
                print(f"  QC 通过: {qc.get('pass', '?')}")
                fails = qc.get("failed_rules", [])
                if fails:
                    print(f"  QC 失败项: {fails}")
        else:
            err = gen_result.get("error", "未知错误") if gen_result else "无响应"
            print(f"  生成失败: {err}")

    result["status"] = "OK"
    return result


def print_summary(results: list[dict]):
    """打印汇总报告"""
    print("\n")
    print("=" * 70)
    print("                     VLM → AiCad 端到端测试报告")
    print("=" * 70)

    # 汇总表
    print(f"\n{'ID':<25} {'状态':<8} {'相似度':<10} {'装配':<10} {'VLM耗时':<8}")
    print("-" * 65)
    for r in results:
        status = r.get("status", "?")
        sim = r.get("similarity", {}).get("overall", 0)
        asm = r.get("assembly", {})
        asm_str = f"{asm.get('pass_count', 0)}/{asm.get('total', 0)}" if asm else "N/A"
        vlm_t = f"{r.get('vlm_time_s', 0):.1f}s"
        print(f"{r['id']:<25} {status:<8} {sim:<10.1%} {asm_str:<10} {vlm_t:<8}")

    # 统计
    ok_count = sum(1 for r in results if r.get("status") == "OK")
    avg_sim = 0
    sim_results = [r for r in results if r.get("similarity")]
    if sim_results:
        avg_sim = sum(r["similarity"]["overall"] for r in sim_results) / len(sim_results)

    asm_pass = sum(1 for r in results if r.get("assembly", {}).get("all_pass"))

    print(f"\n--- 统计 ---")
    print(f"测试数:     {len(results)}")
    print(f"成功提取:   {ok_count}/{len(results)}")
    print(f"平均相似度: {avg_sim:.1%}")
    print(f"装配全通过: {asm_pass}/{ok_count}")

    # 生成结果
    gen_results = [r for r in results if "generate_result" in r]
    if gen_results:
        gen_ok = sum(1 for r in gen_results
                     if r.get("generate_result") and "error" not in r["generate_result"])
        print(f"后端生成:   {gen_ok}/{len(gen_results)} 成功")

    # 问题分析
    print(f"\n--- 问题分析 ---")
    for r in results:
        issues = r.get("validation", {}).get("issues", [])
        asm = r.get("assembly", {})
        failed_checks = [c for c in asm.get("checks", []) if not c["pass"]]

        if issues or failed_checks:
            print(f"\n[{r['id']}] {r['desc']}")
            for i in issues:
                print(f"  参数问题: {i}")
            for c in failed_checks:
                print(f"  装配问题: {c['item']} — {c['note']}")

        gen = r.get("generate_result")
        if gen and "error" in gen:
            print(f"  生成错误: {gen['error']}")

    # 结论
    print(f"\n--- 结论 ---")
    if avg_sim >= 0.8:
        print("外形提取精度: 优秀(≥80%) — VLM 能准确识别唇釉瓶的主要尺寸参数")
    elif avg_sim >= 0.6:
        print("外形提取精度: 良好(60-80%) — VLM 能大致识别外形，部分参数需微调")
    else:
        print("外形提取精度: 一般(<60%) — 需要优化 prompt 或增加后处理逻辑")

    if asm_pass == ok_count and ok_count > 0:
        print("装配结构:     完整 — 提取参数能支持完整的四组件装配")
    elif asm_pass >= ok_count * 0.7:
        print("装配结构:     基本完整 — 多数场景装配可行，少数边界情况需处理")
    else:
        print("装配结构:     部分缺陷 — 需改进参数修正逻辑或增加跨组件约束")


def main():
    parser = argparse.ArgumentParser(description="VLM → AiCad 端到端测试")
    parser.add_argument("--server", default=None,
                        help="AiCad 后端地址 (如 http://localhost:9876)")
    parser.add_argument("--images", default="all",
                        help="测试图片 ID (逗号分隔) 或 'all'")
    args = parser.parse_args()

    # 选择测试图片
    if args.images == "all":
        images = TEST_IMAGES
    else:
        ids = [x.strip() for x in args.images.split(",")]
        images = [img for img in TEST_IMAGES if img["id"] in ids]

    print(f"VLM → AiCad 端到端测试")
    print(f"测试图片: {len(images)} 张")
    print(f"后端地址: {args.server or '(仅参数验证，不生成)'}")
    print(f"GLM 模型: {GLM_MODEL}")

    results = []
    for img in images:
        try:
            r = run_single_test(img, args.server)
            results.append(r)
        except Exception as e:
            print(f"\n!!! 测试 {img['id']} 异常: {e}")
            results.append({
                "id": img["id"],
                "desc": img["desc"],
                "status": "ERROR",
                "error": str(e),
            })
        # 避免 API 限流
        time.sleep(1)

    print_summary(results)

    # 保存详细结果
    out_path = "tests/vlm_test_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存: {out_path}")


if __name__ == "__main__":
    main()
