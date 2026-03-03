# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
WEB_ROOT = PROJECT_ROOT / "web"
DIST_ROOT = PROJECT_ROOT / "web" / "dist"  # Vue build output
ART_ROOT = PROJECT_ROOT / "artifacts"

import sys
sys.path.insert(0, str(SRC_ROOT))

from products.lip_gloss.components.registry import schema as registry_schema, get_component
from core.param_system import get_derived_registry
from core.component_state import get_state_manager
from core.assembly import compute_assembly_positions, compute_assembly_report
# 确保派生规则已注册（包含跨组件规则）
import products.lip_gloss.derived_params  # noqa: F401

SERVER_VERSION = "2026-02-22-v3"


def _json_bytes(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _safe_join(root: Path, rel: str) -> Path:
    p = (root / rel.lstrip("/")).resolve()
    if not str(p).startswith(str(root.resolve())):
        raise ValueError("path escape")
    return p


def _file_url(abs_path: str | None) -> str | None:
    if not abs_path:
        return None
    p = Path(abs_path).resolve()
    if not str(p).startswith(str(ART_ROOT.resolve())):
        return None
    rel = p.relative_to(ART_ROOT)
    return "/artifacts/" + "/".join(rel.parts)


def _qc_fail_reason(res: dict) -> str | None:
    qc = (res or {}).get("qc") or {}
    if not isinstance(qc, dict):
        return None
    if qc.get("ok", True) is True:
        return None
    checks = qc.get("checks") or []
    for c in checks:
        if isinstance(c, dict) and c.get("severity") == "hard" and (c.get("ok") is False):
            return c.get("msg") or "QC hard fail"
    for c in checks:
        if isinstance(c, dict) and (c.get("ok") is False):
            return c.get("msg") or "QC fail"
    return "QC fail"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, ctype: str, data: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, code: int, obj):
        self._send(code, "application/json; charset=utf-8", _json_bytes(obj))

    def _handle_rebuild(self):
        """一键重建前端（GET/POST 均可调用）"""
        print("[REBUILD] Starting npm run build...", flush=True)
        try:
            import os
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["CHCP"] = "65001"
            result = subprocess.run(
                "npm run build",
                cwd=str(WEB_ROOT),
                capture_output=True, timeout=120,
                shell=True,
                env=env,
            )

            def _safe_decode(b: bytes) -> str:
                if not b:
                    return ""
                for enc in ("utf-8", "gbk", "latin-1"):
                    try:
                        return b.decode(enc)
                    except (UnicodeDecodeError, LookupError):
                        continue
                return b.decode("utf-8", errors="replace")

            stdout = _safe_decode(result.stdout)
            stderr = _safe_decode(result.stderr)
            import re
            stdout = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', stdout)
            stderr = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', stderr)

            if result.returncode == 0:
                print("[REBUILD] Success!", flush=True)
                return self._send_json(200, {
                    "ok": True,
                    "message": "rebuild success",
                    "stdout": stdout[-500:],
                })
            else:
                print(f"[REBUILD] Failed (exit {result.returncode})", flush=True)
                return self._send_json(500, {
                    "ok": False,
                    "error": f"build failed (exit {result.returncode})",
                    "stderr": stderr[-1000:],
                    "stdout": stdout[-500:],
                })
        except subprocess.TimeoutExpired:
            return self._send_json(500, {"ok": False, "error": "build timeout (120s)"})
        except Exception as e:
            import traceback
            return self._send_json(500, {
                "ok": False,
                "error": f"rebuild exception: {e}",
                "traceback": traceback.format_exc()[-500:],
            })

    # ================================================================
    #  GET
    # ================================================================
    def do_GET(self):
        u = urlparse(self.path)
        path = u.path

        if path == "/api/ping":
            return self._send_json(200, {"version": SERVER_VERSION})

        if path == "/api/rebuild":
            return self._handle_rebuild()

        if path == "/api/schema":
            return self._send_json(200, registry_schema())

        if path == "/api/derived_rules":
            registry = get_derived_registry()
            return self._send_json(200, registry.export_for_frontend())

        if path == "/api/state":
            state_mgr = get_state_manager()
            return self._send_json(200, state_mgr.export_state())

        if path == "/api/assembly":
            state_mgr = get_state_manager()
            generated = state_mgr.get_all_generated()
            # 支持 ?components=bottle,cap 过滤：只计算 viewer 中实际存在的组件
            qs = parse_qs(u.query)
            comp_filter = qs.get("components", [None])[0]
            if comp_filter:
                wanted = set(c.strip() for c in comp_filter.split(",") if c.strip())
                generated = {k: v for k, v in generated.items() if k in wanted}
            if not generated:
                return self._send_json(200, {
                    "positions": {},
                    "interference": [],
                    "ok": True,
                    "hard_count": 0,
                    "soft_count": 0,
                    "summary": "无已生成组件",
                })
            report = compute_assembly_report(generated)
            return self._send_json(200, report)

        if path.startswith("/api/constraints/"):
            component = path[len("/api/constraints/"):]
            if not component:
                return self._send_json(400, {"error": "missing component"})
            state_mgr = get_state_manager()
            constraints = state_mgr.get_all_constraints_for_component(component)
            return self._send_json(200, {
                "component": component,
                "constraints": constraints,
                "generated": list(state_mgr.get_all_generated().keys()),
            })

        if path == "/" or path == "/index.html":
            p = DIST_ROOT / "index.html"
            if not p.exists():
                p = WEB_ROOT / "index.html"
            if not p.exists():
                return self._send_json(404, {"error": "web/index.html not found"})
            return self._send(200, "text/html; charset=utf-8", p.read_bytes())

        # Vite 构建产物静态资源 (JS/CSS)
        if path.startswith("/assets/"):
            rel = unquote(path[len("/assets/"):])
            try:
                p = _safe_join(DIST_ROOT / "assets", rel)
            except Exception as e:
                return self._send_json(400, {"error": str(e)})
            if not p.exists() or not p.is_file():
                return self._send_json(404, {"error": "not found"})
            ctype, _ = mimetypes.guess_type(str(p))
            return self._send(200, (ctype or "application/octet-stream"), p.read_bytes())

        if path.startswith("/artifacts/"):
            rel = path[len("/artifacts/"):]
            try:
                p = _safe_join(ART_ROOT, rel)
            except Exception as e:
                return self._send_json(400, {"error": str(e)})
            if not p.exists() or not p.is_file():
                return self._send_json(404, {"error": "not found"})
            ctype, _ = mimetypes.guess_type(str(p))
            return self._send(200, (ctype or "application/octet-stream"), p.read_bytes())

        if path.startswith("/web/"):
            rel = unquote(path[len("/web/"):])
            try:
                p = _safe_join(WEB_ROOT, rel)
            except Exception as e:
                return self._send_json(400, {"error": str(e)})
            if not p.exists() or not p.is_file():
                return self._send_json(404, {"error": "not found"})
            ctype, _ = mimetypes.guess_type(str(p))
            return self._send(200, (ctype or "application/octet-stream"), p.read_bytes())

        return self._send_json(404, {"error": "unknown route"})

    # ================================================================
    #  DELETE
    # ================================================================
    def do_DELETE(self):
        u = urlparse(self.path)
        path = u.path

        if path == "/api/generated":
            state_mgr = get_state_manager()
            state_mgr.clear()
            return self._send_json(200, {"ok": True, "message": "all cleared"})

        if path.startswith("/api/generated/"):
            component = path[len("/api/generated/"):]
            if not component:
                return self._send_json(400, {"error": "missing component"})
            state_mgr = get_state_manager()
            state_mgr.clear(component)
            return self._send_json(200, {"ok": True, "component": component})

        return self._send_json(404, {"error": "unknown route"})

    # ================================================================
    #  POST
    # ================================================================
    def do_POST(self):
        u = urlparse(self.path)
        path = u.path

        # 一键重建前端
        if path == "/api/rebuild":
            return self._handle_rebuild()

        # 存储已生成组件的参数
        if path.startswith("/api/generated/"):
            component = path[len("/api/generated/"):]
            if not component:
                return self._send_json(400, {"error": "missing component"})
            try:
                n = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(n) if n > 0 else b"{}"
                req = json.loads(raw.decode("utf-8"))
            except Exception as e:
                return self._send_json(400, {"error": f"bad json: {e}"})

            params = req.get("params", {})
            state_mgr = get_state_manager()
            state_mgr.set_generated(component, params)
            return self._send_json(200, {
                "ok": True,
                "component": component,
                "param_count": len(params),
            })

        if path != "/api/generate":
            return self._send_json(404, {"error": "unknown route"})

        try:
            n = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(n) if n > 0 else b"{}"
            req = json.loads(raw.decode("utf-8"))
        except Exception as e:
            return self._send_json(400, {"error": f"bad json: {e}"})

        product = req.get("product", "lip_gloss")
        component = req.get("component", "cap")
        preset_id = req.get("preset_id", None)
        params = req.get("params", {}) or {}
        title = req.get("title", None)

        try:
            comp = get_component(product, component)
        except Exception as e:
            return self._send_json(400, {"error": str(e)})

        # 重新生成前先清除该组件的旧状态，防止自身约束自身
        try:
            state_mgr = get_state_manager()
            state_mgr.clear(component)
        except Exception:
            pass

        t0 = None
        _time_mod = None
        try:
            import time as _time_mod
            t0 = _time_mod.perf_counter()
        except Exception:
            t0 = None
            _time_mod = None

        try:
            outroot = str(ART_ROOT / "webui")
            res = comp.generate(preset_id=preset_id, user_params=params, outroot=outroot, title=title)

            try:
                if t0 is not None and _time_mod is not None:
                    res["time_sec"] = round(_time_mod.perf_counter() - t0, 3)
            except Exception:
                pass

            # QC 不通过 => 强制 FAIL
            reason = _qc_fail_reason(res)
            if reason is not None:
                res["ok"] = False
                res["error"] = res.get("error") or f"QC_FAIL: {reason}"
                res["step"] = None
                res["stl"] = None
                res["svg"] = None
                res["step_url"] = None
                res["stl_url"] = None
                res["svg_url"] = None
                return self._send_json(200, res)

            res["step_url"] = _file_url(res.get("step"))
            res["stl_url"] = _file_url(res.get("stl"))
            res["svg_url"] = _file_url(res.get("svg"))

            # 自动存储组件参数到状态管理器
            try:
                state_mgr = get_state_manager()
                final_params = res.get("qc", {}).get("params", params)
                state_mgr.set_generated(component, final_params)
                res["state_saved"] = True
            except Exception:
                res["state_saved"] = False

            # 计算装配位置和干涉报告
            try:
                state_mgr = get_state_manager()
                generated = state_mgr.get_all_generated()
                if generated:
                    assembly = compute_assembly_report(generated)
                    res["assembly"] = assembly
            except Exception:
                pass

            return self._send_json(200, res)

        except Exception as e:
            return self._send_json(500, {"error": f"generate failed: {e}"})


def _kill_old_processes_on_port(port: int):
    """启动前自动杀掉占用同一端口的旧进程（Windows）"""
    import os
    try:
        result = subprocess.run(
            f'netstat -ano | findstr ":{port}.*LISTENING"',
            shell=True, capture_output=True, text=True, timeout=5,
        )
        my_pid = os.getpid()
        killed = []
        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5:
                try:
                    pid = int(parts[-1])
                    if pid != my_pid and pid > 0:
                        subprocess.run(f"taskkill /F /PID {pid}", shell=True,
                                       capture_output=True, timeout=5)
                        killed.append(pid)
                except (ValueError, subprocess.TimeoutExpired):
                    pass
        if killed:
            print(f"[WEB] Killed old processes on port {port}: {killed}")
            import time
            time.sleep(0.5)  # 等待端口释放
    except Exception as e:
        print(f"[WEB] Warning: could not check port {port}: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8010)
    args = ap.parse_args()

    # 自动清理占用端口的旧进程
    _kill_old_processes_on_port(args.port)

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[WEB] http://{args.host}:{args.port}")
    print(f"[WEB] Server version: {SERVER_VERSION}")
    print(f"[WEB] DIST_ROOT: {DIST_ROOT} exists={DIST_ROOT.exists()}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
