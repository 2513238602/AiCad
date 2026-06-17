# -*- coding: utf-8 -*-
"""测试智谱 GLM-4V API 参数提取能力"""
import os
import urllib.request, json, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

API_KEY = os.environ.get("GLM_API_KEY", "")
if not API_KEY:
    raise SystemExit("Set GLM_API_KEY before running this API test.")
API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

PROMPT = '''你是唇釉瓶产品工程师。请根据以下描述估算参数，严格按 JSON 格式输出，不要输出任何其他内容。

描述：一个标准圆柱形唇釉瓶，总高约70mm，瓶身直径24mm，口部直径18mm，颈部高约10mm，圆弧肩部。

输出格式：
{
  "height_mm": number,
  "body_od_mm": number,
  "neck_od_mm": number,
  "neck_height_mm": number,
  "shoulder_style": "round" 或 "angular" 或 "sloped",
  "profile_mode": "classic" 或 "spline",
  "profile_points": [[r, z], ...],
  "confidence": 0.0到1.0
}'''

payload = json.dumps({
    'model': 'glm-4.6v',
    'messages': [{'role': 'user', 'content': PROMPT}],
    'max_tokens': 500,
    'temperature': 0.1
}).encode('utf-8')

req = urllib.request.Request(API_URL, data=payload, headers={
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {API_KEY}'
})

with urllib.request.urlopen(req, timeout=30) as resp:
    result = json.loads(resp.read().decode('utf-8'))
    reply = result['choices'][0]['message']['content']
    print('=== GLM REPLY ===')
    print(reply)
    print()

    # 尝试解析 JSON
    json_str = reply.strip()
    if '```' in json_str:
        parts = json_str.split('```')
        for part in parts:
            part = part.strip()
            if part.startswith('json'):
                part = part[4:].strip()
            if part.startswith('{'):
                json_str = part
                break

    try:
        parsed = json.loads(json_str)
        print('=== PARSED JSON ===')
        print(json.dumps(parsed, indent=2, ensure_ascii=False))

        # 验证关键字段
        required = ['height_mm', 'body_od_mm', 'neck_od_mm', 'profile_points']
        missing = [k for k in required if k not in parsed]
        if missing:
            print(f'\nMISSING FIELDS: {missing}')
        else:
            print('\nALL REQUIRED FIELDS PRESENT')
            pts = parsed.get('profile_points', [])
            print(f'PROFILE POINTS: {len(pts)} points')
            for i, pt in enumerate(pts):
                print(f'  [{i}] r={pt[0]:.1f}mm, z={pt[1]:.1f}mm')
    except json.JSONDecodeError as e:
        print(f'JSON PARSE FAILED: {e}')
        print(f'Raw: {json_str[:200]}')
