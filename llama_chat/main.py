# llama_chat/main.py

"""
Llama Chat Application - Entry Point

This script provides a simple command-line chat interface that uses the AHK v2 generator from the parent project.
"""

import sys
import os
import json
import requests
import subprocess
import base64
import logging
from datetime import datetime
import re
import hashlib
import ast
import time

# Optional screenshot dependency
try:
    import mss  # type: ignore
    import mss.tools  # type: ignore
except Exception:  # noqa: BLE001
    mss = None  # Fallback; screenshot tool will report missing dependency

# Ensure parent directory is in sys.path for imports
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Sandbox root where the model can autonomously create / modify files
SANDBOX_ROOT = os.path.join(parent_dir, "model_sandbox")
os.makedirs(SANDBOX_ROOT, exist_ok=True)

from llama_client import generate_ahk_code, get_api_url, get_api_key, get_model
from cli_tool_executor import run_cli_tool

# Sequential thinking handler (custom reasoning tool)
try:
    from sequential_thinking_tool import sequential_thinking_tool  # type: ignore
except Exception:  # noqa: BLE001
    sequential_thinking_tool = None

# Real tool handlers registry (local only)
CUSTOM_TOOL_HANDLERS = {}

logger = logging.getLogger("llama_chat")
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)

# Replace previous custom_handlers / registry logic with a clean registry
tool_registry = {}

json_schemas_dir = os.path.join(os.path.dirname(__file__), 'json_schemas')

# --- Real tool handlers (must be defined before registration) ---
def handle_execute_and_validate_script(args):
    """Execute Python or AHK script with validation.
    Returns dict (not JSON string) so caller can serialize uniformly."""
    script_path = args.get("script_path", "")
    script_type = args.get("script_type", "")
    result: dict = {"script_path": script_path, "script_type": script_type}
    if not script_path or not os.path.exists(script_path):
        result["error"] = "script_path missing or not found"
        return result
    parent_dir_local = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    logger.info(f"[validate] Starting validation script={script_path} type={script_type}")
    try:
        if script_type == "python":
            venv_python = os.path.join(parent_dir_local, ".venv", "Scripts", "python.exe")
            if not os.path.exists(venv_python):
                venv_python = sys.executable
            proc = subprocess.run([venv_python, script_path], capture_output=True, text=True, timeout=60)
            result.update({
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-1500:],
                "stderr": proc.stderr[-1500:],
                "success": proc.returncode == 0
            })
        elif script_type == "ahk":
            try:
                from AHK_Validator import validate_ahk_script  # type: ignore
            except Exception as e:  # noqa: BLE001
                result["error"] = f"Validator import failed: {e}"
                return result
            with open(script_path, 'r', encoding='utf-8') as f:
                code = f.read()
            valid = False
            try:
                valid = validate_ahk_script(code)
            except Exception as e:  # noqa: BLE001
                result["validation_error"] = str(e)
            result["valid"] = valid
            if valid:
                ahk_exe = "AutoHotkey.exe"
                if shutil.which(ahk_exe):
                    try:
                        proc = subprocess.run([ahk_exe, script_path], capture_output=True, text=True, timeout=20)
                        result.update({
                            "exit_code": proc.returncode,
                            "stdout": proc.stdout[-1500:],
                            "stderr": proc.stderr[-1500:],
                            "success": proc.returncode == 0
                        })
                    except Exception as e:  # noqa: BLE001
                        result["run_error"] = str(e)
                else:
                    result["warning"] = "AutoHotkey.exe not found in PATH"
            else:
                result["success"] = False
        else:
            result["error"] = "Unsupported script_type (expected 'python' or 'ahk')"
    except Exception as e:  # noqa: BLE001
        result["error"] = str(e)
    finally:
        logger.info(f"[validate] Finished script={script_path} status={result.get('success')} errors={bool(result.get('error'))}")
    return result

# Additional concrete handlers for CLI-like schemas (replace generic flag mapping where needed)
def handler_psutil(args):
    try:
        import psutil  # type: ignore
    except Exception as e:  # noqa: BLE001
        return {"error": f"psutil not installed: {e}"}
    action = args.get("action", "")
    if action == "cpu_usage":
        return {"cpu_percent": psutil.cpu_percent(interval=0.2)}
    if action == "memory_info":
        v = psutil.virtual_memory()
        return {"total": v.total, "available": v.available, "percent": v.percent}
    if action == "list_processes":
        procs = []
        for p in psutil.process_iter(attrs=["pid", "name"]):
            if len(procs) >= 25:
                break
            info = p.info
            procs.append(info)
        return {"processes": procs}
    return {"error": f"Unknown action '{action}'"}

def handler_tasklist(args):
    op = args.get("operation", "list")
    if op == "list":
        try:
            proc = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=15)
            return {"exit_code": proc.returncode, "output": proc.stdout[-6000:], "error": proc.stderr[-1000:]}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
    if op == "kill":
        pid = args.get("pid")
        if not pid:
            return {"error": "pid required for kill"}
        try:
            proc = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True, timeout=15)
            return {"exit_code": proc.returncode, "output": proc.stdout, "error": proc.stderr}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
    return {"error": f"Unknown operation '{op}'"}

def handler_curl(args):
    url = args.get("url")
    if not url:
        return {"error": "url required"}
    method = args.get("method", "GET").upper()
    headers_list = args.get("headers") or []
    data = args.get("data")
    headers = {}
    for h in headers_list:
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()
    try:
        resp = requests.request(method, url, headers=headers, data=data, timeout=30)
        return {"status": resp.status_code, "body": resp.text[:8000], "headers": dict(resp.headers)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}

def handler_zip(args):
    op = args.get("operation")
    files = args.get("input_files") or []
    out = args.get("output_file")
    if not op:
        return {"error": "operation required"}
    import zipfile
    if op == "zip":
        if not out:
            return {"error": "output_file required for zip"}
        try:
            with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                for f in files:
                    if os.path.exists(f):
                        zf.write(f, arcname=os.path.basename(f))
            return {"created": out, "file_count": len(files)}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
    if op == "unzip":
        if not out or not files:
            return {"error": "output_file (target dir) and input_files (archive) required"}
        archive = files[0]
        try:
            with zipfile.ZipFile(archive, 'r') as zf:
                zf.extractall(out)
            return {"extracted_to": out, "entries": len(zf.namelist())}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
    return {"error": f"Unsupported operation '{op}'"}

def handler_sequential(args):
    if sequential_thinking_tool:
        return sequential_thinking_tool(args)
    return {"error": "Sequential tool not available"}

SAFE_GIT_CMDS = {"status", "diff", "log", "show", "branch", "rev-parse", "remote", "ls-files"}
def handler_git(args):
    cmd = args.get("command")
    extra = args.get("args") or []
    if not cmd:
        return {"error": "command required"}
    if cmd not in SAFE_GIT_CMDS:
        return {"error": f"disallowed git command '{cmd}'"}
    full = ["git", cmd] + [str(a) for a in extra]
    try:
        proc = subprocess.run(full, capture_output=True, text=True, timeout=40)
        return {"exit_code": proc.returncode, "stdout": proc.stdout[-6000:], "stderr": proc.stderr[-4000:], "cmd": " ".join(full)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "cmd": " ".join(full)}

def handler_ffmpeg(args):
    input_file = args.get("input_file")
    output_file = args.get("output_file")
    if not input_file or not output_file:
        return {"error": "input_file and output_file required"}
    cmd = ["ffmpeg", "-y", "-i", input_file]
    if args.get("codec"):
        cmd += ["-c:v", args["codec"]]
    if args.get("bitrate"):
        cmd += ["-b:v", args["bitrate"]]
    for ea in args.get("extra_args") or []:
        cmd.append(str(ea))
    cmd.append(output_file)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return {"exit_code": proc.returncode, "stderr": proc.stderr[-8000:], "stdout": proc.stdout[-2000:], "cmd": " ".join(cmd)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "cmd": " ".join(cmd)}

def handler_imagemagick(args):
    input_file = args.get("input_file")
    output_file = args.get("output_file")
    op = args.get("operation")
    if not input_file or not output_file or not op:
        return {"error": "input_file, output_file, operation required"}
    base_cmd = ["magick", input_file]
    op_args = args.get("operation_args") or []
    base_cmd += op_args
    base_cmd.append(output_file)
    try:
        proc = subprocess.run(base_cmd, capture_output=True, text=True, timeout=120)
        return {"exit_code": proc.returncode, "stderr": proc.stderr[-4000:], "stdout": proc.stdout[-1000:], "cmd": " ".join(base_cmd)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "cmd": " ".join(base_cmd)}

def handler_notepad(args):
    file_path = args.get("file_path")
    action = args.get("action", "open")
    content = args.get("content")
    if not file_path:
        return {"error": "file_path required"}
    if action == "save":
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content or "")
            return {"saved": file_path, "bytes": len(content or "")}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}
    if action == "open":
        if os.path.exists(file_path):
            return {"exists": True, "size": os.path.getsize(file_path)}
        return {"exists": False}
    return {"error": f"Unsupported action '{action}'"}

import shutil  # placed after handler defs for clarity

def _slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-+", "-", text).strip('-') or 'script'

def handle_generate_ahk(args):
    """Generate AHK code, save, then auto-chain validation + manifest update."""
    prompt = args.get('prompt', '').strip()
    code = generate_ahk_code(prompt)
    out_dir = os.path.join(SANDBOX_ROOT, "ahk")
    os.makedirs(out_dir, exist_ok=True)
    base_slug = _slug(prompt.split('\n')[0][:60]) if prompt else 'generated'
    ts = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    file_path = os.path.join(out_dir, f"auto_{base_slug}_{ts}.ahk")
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(code if code.endswith('\n') else code + '\n')
    except Exception as e:  # noqa: BLE001
        return {"error": f"Failed to save AHK code: {e}", "code": code[:5000]}
    # Validation step
    validation = handle_execute_and_validate_script({"script_path": file_path, "script_type": "ahk"})
    # If validation returns dict already, keep; if string JSON, parse
    if isinstance(validation, str):
        try:
            validation_obj = json.loads(validation)
        except Exception:  # noqa: BLE001
            validation_obj = {"raw": validation}
    else:
        validation_obj = validation
    # Manifest update step
    # Manifest enrichment
    manifest_path = os.path.join(SANDBOX_ROOT, "MANIFEST.json")
    manifest = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as mf:
                manifest = json.load(mf)
        except Exception:  # noqa: BLE001
            manifest = {}
    files_meta = manifest.get('files', {})
    sha256 = hashlib.sha256(code.encode('utf-8', errors='ignore')).hexdigest()
    files_meta[file_path.replace(parent_dir+os.sep, '')] = {
        'language': 'ahk',
        'created': datetime.utcnow().isoformat() + 'Z',
        'size': len(code),
        'lines': code.count('\n') + 1,
        'sha256': sha256,
        'prompt_excerpt': prompt[:160],
        'valid': isinstance(validation_obj, dict) and validation_obj.get('valid'),
    }
    manifest['files'] = files_meta
    manifest['updated'] = datetime.utcnow().isoformat() + 'Z'
    try:
        with open(manifest_path, 'w', encoding='utf-8') as mf:
            json.dump(manifest, mf, indent=2)
    except Exception as e:  # noqa: BLE001
        validation_obj = {'error': f"Manifest write failed: {e}", **(validation_obj if isinstance(validation_obj, dict) else {})}
    annotated = code + ("\n" if not code.endswith('\n') else "") + f"; --- Saved to: {file_path} ---"\
        + "\n; Prompt: " + prompt[:300].replace('\n', ' ')[:300]
    return {
        "file_path": file_path,
        "code": annotated,
        "language": "ahk",
        "prompt": prompt,
        "validation": validation_obj,
        "manifest_updated": True
    }

def handle_generate_python(args):
    prompt = args.get('prompt', '').strip()
    # Reuse AHK generator temporarily by prompting for Python (placeholder for dedicated Python model)
    py_prompt = f"Generate a complete, runnable Python script for the following requirement. Include if __name__ == '__main__' when appropriate. {prompt}"
    code = generate_ahk_code(py_prompt)  # TODO: replace with real python model call
    # Heuristic cleanup: ensure .py style (strip any AHK directive accidentally)
    code_lines = [ln for ln in code.split('\n') if not ln.startswith('#Requires AutoHotkey')]
    code = '\n'.join(code_lines)
    out_dir = os.path.join(SANDBOX_ROOT, "python")
    os.makedirs(out_dir, exist_ok=True)
    base_slug = _slug(prompt.split('\n')[0][:60]) if prompt else 'generated'
    ts = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    file_path = os.path.join(out_dir, f"auto_{base_slug}_{ts}.py")
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(code if code.endswith('\n') else code + '\n')
    except Exception as e:  # noqa: BLE001
        return {"error": f"Failed to save Python code: {e}", "code": code[:5000]}
    validation = handle_execute_and_validate_script({"script_path": file_path, "script_type": "python"})
    if isinstance(validation, str):
        try:
            validation_obj = json.loads(validation)
        except Exception:
            validation_obj = {"raw": validation}
    else:
        validation_obj = validation
    # Extract imports for metadata
    deps = []
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for n in node.names:
                    deps.append(n.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    deps.append(node.module.split('.')[0])
        deps = sorted(set(deps))[:50]
    except Exception:
        pass
    manifest_path = os.path.join(SANDBOX_ROOT, "MANIFEST.json")
    manifest = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as mf:
                manifest = json.load(mf)
        except Exception:
            manifest = {}
    files_meta = manifest.get('files', {})
    sha256 = hashlib.sha256(code.encode('utf-8', errors='ignore')).hexdigest()
    files_meta[file_path.replace(parent_dir+os.sep, '')] = {
        'language': 'python',
        'created': datetime.utcnow().isoformat() + 'Z',
        'size': len(code),
        'lines': code.count('\n') + 1,
        'sha256': sha256,
        'prompt_excerpt': prompt[:160],
        'imports': deps,
        'validation_exit': validation_obj.get('exit_code') if isinstance(validation_obj, dict) else None,
        'validation_success': validation_obj.get('success') if isinstance(validation_obj, dict) else None,
    }
    manifest['files'] = files_meta
    manifest['updated'] = datetime.utcnow().isoformat() + 'Z'
    try:
        with open(manifest_path, 'w', encoding='utf-8') as mf:
            json.dump(manifest, mf, indent=2)
    except Exception:
        pass
    return {
        "file_path": file_path,
        "code": code,
        "language": "python",
        "prompt": prompt,
        "validation": validation_obj,
        "dependencies": deps,
        "manifest_updated": True
    }

CUSTOM_TOOL_HANDLERS.update({
    "generate_ahk_code": handle_generate_ahk,
    "generate_python_code": handle_generate_python,
    "execute_and_validate_script": handle_execute_and_validate_script,
    "psutil_tool": handler_psutil,
    "tasklist_tool": handler_tasklist,
    "curl_tool": handler_curl,
    "zip_tool": handler_zip,
    "sequential_thinking_tool": handler_sequential,
    "git_tool": handler_git,
    "ffmpeg_tool": handler_ffmpeg,
    "imagemagick_tool": handler_imagemagick,
    "notepad_tool": handler_notepad,
    # Filesystem sandbox tool will be added after its handler below
})

def register_tool(schema: dict):
    """Register a tool schema with appropriate handler (custom or universal)."""
    if not isinstance(schema, dict):
        return
    # Support both our earlier function style and plain name style
    function_block = schema.get('function')
    if function_block and isinstance(function_block, dict):
        tool_name = function_block.get('name')
    else:
        tool_name = schema.get('name')
    if not tool_name:
        return
    handler = CUSTOM_TOOL_HANDLERS.get(tool_name)
    if not handler:
        if tool_name == 'take_screenshot_and_send':
            handler = lambda args: screenshot_handler(args)  # noqa: E731
        else:
            handler = run_cli_tool
    tool_registry[tool_name] = (schema, handler)

# Filesystem sandbox tool handler
def handler_filesystem(args: dict):
    action = args.get("action")
    rel_path = args.get("path") or ""
    target = os.path.abspath(os.path.join(SANDBOX_ROOT, rel_path)) if rel_path else SANDBOX_ROOT
    # Security: ensure within sandbox
    if not target.startswith(os.path.abspath(SANDBOX_ROOT)):
        return {"error": "Path escapes sandbox"}
    try:
        if action == "mkdir":
            if not rel_path:
                return {"error": "path required for mkdir"}
            os.makedirs(target, exist_ok=True)
            return {"created": rel_path, "type": "dir"}
        if action == "write":
            if not rel_path:
                return {"error": "path required for write"}
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'w', encoding='utf-8') as f:
                f.write(args.get("content", ""))
            return {"written": rel_path, "bytes": len(args.get("content", ""))}
        if action == "append":
            if not rel_path:
                return {"error": "path required for append"}
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'a', encoding='utf-8') as f:
                f.write(args.get("content", ""))
            return {"appended": rel_path, "bytes": len(args.get("content", ""))}
        if action == "read":
            if not rel_path or not os.path.isfile(target):
                return {"error": "file not found"}
            with open(target, 'r', encoding='utf-8') as f:
                data = f.read()
            # Truncate large content
            truncated = len(data) > 8000
            return {"path": rel_path, "content": data[:8000], "truncated": truncated}
        if action == "list":
            import fnmatch
            pattern = args.get("pattern")
            recursive = args.get("recursive", False)
            entries = []
            base_len = len(SANDBOX_ROOT) + 1
            if recursive:
                for root, dirs, files in os.walk(target):
                    for d in dirs:
                        p = os.path.join(root, d)
                        rel = p[base_len:]
                        entries.append({"path": rel, "type": "dir"})
                    for f in files:
                        p = os.path.join(root, f)
                        rel = p[base_len:]
                        if not pattern or fnmatch.fnmatch(f, pattern):
                            entries.append({"path": rel, "type": "file"})
            else:
                for item in os.listdir(target):
                    p = os.path.join(target, item)
                    rel = p[len(SANDBOX_ROOT)+1:]
                    if pattern and not fnmatch.fnmatch(item, pattern):
                        continue
                    entries.append({"path": rel, "type": "dir" if os.path.isdir(p) else "file"})
            return {"entries": entries[:500], "count": len(entries)}
        if action == "delete":
            if not rel_path:
                return {"error": "path required for delete"}
            if os.path.isdir(target):
                shutil.rmtree(target)
                return {"deleted": rel_path, "type": "dir"}
            if os.path.isfile(target):
                os.remove(target)
                return {"deleted": rel_path, "type": "file"}
            return {"error": "target not found"}
        if action == "manifest_update":
            manifest_path = os.path.join(SANDBOX_ROOT, "MANIFEST.json")
            manifest = {}
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                except Exception:  # noqa: BLE001
                    manifest = {}
            manifest['updated'] = datetime.utcnow().isoformat() + 'Z'
            manifest['entries'] = manifest.get('entries', 0) + 1
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, indent=2)
            return {"manifest": manifest}
        return {"error": f"Unsupported action '{action}'"}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}

CUSTOM_TOOL_HANDLERS["filesystem_tool"] = handler_filesystem

# Auto register all schemas
if os.path.isdir(json_schemas_dir):
    for fname in os.listdir(json_schemas_dir):
        if fname.endswith('.json'):
            try:
                with open(os.path.join(json_schemas_dir, fname), 'r', encoding='utf-8') as f:
                    schema = json.load(f)
                register_tool(schema)
            except Exception as e:
                logger.warning(f"Failed to register schema {fname}: {e}")

# Simplified tool call handler now using registry exclusively (duplicate legacy
# handle_execute_and_validate_script removed above).

def screenshot_handler(args: dict):
    """Handle screenshot tool: if no image_paths provided, capture one temp screenshot (if mss present)."""
    image_paths = args.get("image_paths") or []
    context_text = args.get("context_text", "")
    generated_temp = []
    if not image_paths:
        if mss is None:
            return {"error": "mss not installed; cannot capture screenshot.", "context": context_text}
        # Capture one screen
        tmp_name = os.path.join(os.getcwd(), "screenshot_tool_preview.png")
        try:
            with mss.mss() as sct:  # type: ignore
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                mss.tools.to_png(sct_img.rgb, sct_img.size, output=tmp_name)  # type: ignore
            image_paths = [tmp_name]
            generated_temp = [tmp_name]
        except Exception as e:  # noqa: BLE001
            return {"error": f"Failed to capture screenshot: {e}"}
    images_payload = []
    for p in image_paths:
        try:
            with open(p, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode('utf-8')
            images_payload.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"}
            })
        except Exception as e:  # noqa: BLE001
            images_payload.append({"type": "text", "text": f"[ERROR] Could not read {p}: {e}"})
    message = []
    if context_text:
        message.append({"type": "text", "text": context_text})
    message.extend(images_payload)
    return {"context": context_text, "images": image_paths, "generated_temp": generated_temp, "message_payload": message}


def build_tool_payloads():
    """Return list of tool specs formatted for API from registry schemas."""
    payloads = []
    for schema, _handler in tool_registry.values():
        if 'type' in schema and schema.get('type') == 'function' and 'function' in schema:
            payloads.append(schema)
        else:
            # Convert simple schema to function style
            payloads.append({
                "type": "function",
                "function": {
                    "name": schema.get('name'),
                    "description": schema.get('description', '')[:400],
                    "parameters": schema.get('parameters', {"type": "object", "properties": {}})
                }
            })
    return payloads


def build_system_prompt():
    """Construct a focused system prompt tuned to the user's terse, execution‑oriented style."""
    tool_summaries = []
    for name, (schema, _handler) in tool_registry.items():
        if 'function' in schema and isinstance(schema['function'], dict):
            desc = schema['function'].get('description', '')
        else:
            desc = schema.get('description', '')
        tool_summaries.append(f"{name}: {desc[:110]}")

    return (
        "You are an action-focused assistant inside a development/runtime console.\n"
        "Style: concise, direct, no filler, no self-limit disclaimers, match user's blunt tone without mirroring profanity.\n"
        "Primary goals: (1) Understand intent quickly. (2) If a tool can progress the task, call it immediately. (3) Return synthesized, high-signal results.\n"
        "Behavior rules: \n"
        "- Never say you 'do not have access'—you have tool abstractions and must attempt execution via them.\n"
        "- When user asks for validation, generation, execution, inspection, or improvement: choose / chain tools automatically.\n"
        "- Summarize outputs: show key metrics, status, errors, next actionable suggestion. Avoid verbose raw dumps unless user asks.\n"
        "- If input info is insufficient, ask ONLY the minimal clarifying question required to proceed.\n"
        "- Avoid repeating the full tool list after first response.\n"
        "- For code generation: produce clean AHK v2 or Python; mention critical caveats only.\n"
        "- For failures: briefly state root cause + next fix step.\n"
        "- Maintain a running mental model; don't re-explain solved steps.\n"
    "Rules of Engagement (enforce these):\n"
    "1. Always generate COMPLETE runnable code blocks (no placeholders like ...).\n"
    "2. Always SAVE generated AHK/Python code to a file before any execution or validation.\n"
    "3. Use file naming pattern: auto_<purpose>_<yyyy-mm-dd_HHMMSS>.<ext>. Provide path to user.\n"
    "4. After saving, summarize: file path, main entry points, next recommended action/tool.\n"
    "5. Only request clarification if a required parameter is ambiguous AND guessing risks wrong behavior.\n"
    "6. Chain tools (generation -> save -> validate -> (optional) execute -> (optional) screenshot) without waiting if safe.\n"
    "7. On errors: output concise root cause + ordered fix plan; offer to apply fix.\n"
    "8. Avoid unnecessary reiteration of rules after first response.\n"
    "9. Use screenshot tool only when visual state verification adds value or user requests it.\n"
    "10. Provide diff-style summaries when revising code.\n"
        "Available tools (internal summary – do not restate verbatim to user unless asked):\n" +
        " | ".join(tool_summaries)
    )


class ChatSession:
    def __init__(self):
        self.history = []  # OpenAI/Llama-style message dicts

    def add_user_message(self, message: str):
        self.history.append({"role": "user", "content": message})

    def add_assistant_message(self, message: str):
        self.history.append({"role": "assistant", "content": message})

    def display_history(self):
        for msg in self.history:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                print(f"You: {content}")
            elif role == "assistant":
                print(f"Assistant: {content}")
            elif role == "tool":
                print(f"[TOOL]: {content}")
        print("\n---\n")

    def call_llama_api(self, tools=None, tool_results=None):
        api_url = get_api_url()
        api_key = get_api_key()
        model = get_model()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": model,
            "messages": self.history,
        }
        if tools:
            payload["tools"] = tools
        if tool_results:
            payload["tool_results"] = tool_results
        resp = requests.post(api_url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def handle_tool_call(self, tool_call):
        fn = tool_call["function"]["name"]
        args = json.loads(tool_call["function"]["arguments"])
        entry = tool_registry.get(fn)
        if not entry:
            return {"tool_call_id": tool_call["id"], "role": "tool", "name": fn, "content": "[ERROR] Unknown tool"}
        schema, handler = entry
        try:
            logger.info(f"[tool] START {fn} args_keys={list(args.keys())}")
            if handler is run_cli_tool:
                result = handler(args, schema)
            else:
                result = handler(args)
            envelope = {}
            if isinstance(result, dict):
                envelope = {
                    "tool": fn,
                    "status": "ok" if 'error' not in result else 'error',
                    "summary": {k: v for k, v in result.items() if k not in ('code',)},
                }
                if 'code' in result:
                    envelope['code'] = result['code']
                result_str = json.dumps(envelope, ensure_ascii=False, indent=2)
            elif isinstance(result, (str, bytes)):
                result_str = result if isinstance(result, str) else result.decode('utf-8', errors='replace')
            else:
                result_str = json.dumps({"tool": fn, "status": "ok", "data": str(result)}, ensure_ascii=False)
            logger.info(f"[tool] END {fn} status={'error' if 'error' in result_str.lower() else 'ok'}")
            return {"tool_call_id": tool_call["id"], "role": "tool", "name": fn, "content": result_str}
        except Exception as e:
            logger.exception(f"Tool '{fn}' failed")
            return {"tool_call_id": tool_call["id"], "role": "tool", "name": fn, "content": f"[ERROR] {e}"}

    def take_screenshot(self, image_path):
        if mss is None:
            raise RuntimeError("mss is not installed. Please install with 'pip install mss'.")
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Full screen
            sct_img = sct.grab(monitor)
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=image_path)
        return image_path

    def image_to_base64(self, image_path):
        with open(image_path, "rb") as img:
            return base64.b64encode(img.read()).decode('utf-8')

    def handle_take_screenshot_and_send(self, args):
        return screenshot_handler(args)

    def chat(self):
        print("Welcome to Llama Chat! Type your message. Type 'exit' to quit.")
        # Dynamic system prompt reflecting current tools
        self.history.insert(0, {"role": "system", "content": build_system_prompt()})
        tools_payload = build_tool_payloads()

        def extract_and_save_code(text: str):
            """Detect code in assistant free-form output, save to sandbox, optionally validate/execute."""
            if not text or not isinstance(text, str):
                return None
            code_blocks = []
            if '```' in text:
                parts = text.split('```')
                for i in range(1, len(parts), 2):
                    block = parts[i]
                    # strip optional language tag first line
                    lines = block.split('\n')
                    if lines and len(lines[0]) < 25 and not lines[0].strip().startswith('#') and not lines[0].strip().startswith('import') and not lines[0].strip().startswith('def '):
                        # treat first line as lang tag
                        lang_tag = lines[0].strip().lower()
                        block = '\n'.join(lines[1:])
                    code_blocks.append(block.strip())
            else:
                # Heuristic single-block detection
                if ('#Requires AutoHotkey' in text) or ('Send(' in text and '::' in text) or text.strip().startswith('import ') or 'def ' in text:
                    code_blocks.append(text.strip())
            saved = []
            for code in code_blocks:
                if not code or len(code) < 8:
                    continue
                # Determine language
                lang = 'ahk' if '#Requires AutoHotkey' in code or '::' in code else 'python' if ('import ' in code or 'def ' in code) else 'txt'
                subdir = 'ahk_freeform' if lang == 'ahk' else 'py_freeform' if lang == 'python' else 'raw_freeform'
                out_dir = os.path.join(SANDBOX_ROOT, subdir)
                os.makedirs(out_dir, exist_ok=True)
                ts = time.strftime('%Y-%m-%d_%H%M%S')
                fname = f"auto_free_{int(time.time())}_{len(saved)}.{ 'ahk' if lang=='ahk' else ('py' if lang=='python' else 'txt') }"
                fpath = os.path.join(out_dir, fname)
                try:
                    with open(fpath, 'w', encoding='utf-8') as f:
                        f.write(code if code.endswith('\n') else code+'\n')
                except Exception as e:  # noqa: BLE001
                    continue
                action_summary = {"file": fpath.replace(parent_dir+os.sep, ''), "lang": lang, "bytes": len(code)}
                # Optional auto validate/execute gated by env var
                if os.environ.get('AUTO_VALIDATE_GENERATED') == '1' and lang in ('ahk','python'):
                    val = handle_execute_and_validate_script({"script_path": fpath, "script_type": 'ahk' if lang=='ahk' else 'python'})
                    if isinstance(val, dict):
                        action_summary['validation'] = {k: val.get(k) for k in ('success','exit_code','valid','error','warning') if k in val}
                saved.append(action_summary)
            if saved:
                envelope = {"auto_saved_blocks": saved}
                tool_msg = {"role": "tool", "name": "auto_save_freeform", "tool_call_id": f"auto_save_{int(time.time())}", "content": json.dumps(envelope, ensure_ascii=False, indent=2)}
                self.history.append(tool_msg)
                print(f"[AUTO-SAVE] {len(saved)} block(s) saved.")

        while True:
            user_input = input("You: ").strip()
            if user_input.lower() in ("exit", "quit"):
                print("Goodbye!")
                break
            if not user_input:
                continue
            self.add_user_message(user_input)
            # Call Llama API with dynamic tool payloads
            response = self.call_llama_api(tools=tools_payload)
            cm = response.get("completion_message")
            if not cm:
                print("[ERROR] No completion_message in response.")
                continue
            stop_reason = cm.get("stop_reason")
            if stop_reason == "tool_calls":
                tool_calls = cm.get("tool_calls", [])
                tool_results = []
                auto_planned = False
                for tc in tool_calls:
                    tool_result = self.handle_tool_call(tc)
                    tool_results.append(tool_result)
                    self.history.append(tool_result)
                # Heuristic planner: auto screenshot if UI keywords & successful validation
                auto_calls = []
                try:
                    for tr in tool_results:
                        content = tr.get('content', '')
                        if 'generate_ahk_code' in content or 'generate_python_code' in content:
                            if 'MsgBox' in content or 'WinActivate' in content or 'Click(' in content:
                                if not auto_planned:
                                    auto_calls.append({
                                        'function': {'name': 'take_screenshot_and_send', 'arguments': json.dumps({'image_paths': []})},
                                        'id': f'auto_screenshot_{len(auto_calls)}'
                                    })
                                    auto_planned = True
                except Exception:
                    pass
                for ac in auto_calls:
                    ar = self.handle_tool_call(ac)
                    tool_results.append(ar)
                    self.history.append(ar)
                # Re-call with all tool results
                response2 = self.call_llama_api(tools=tools_payload, tool_results=tool_results)
                cm2 = response2.get("completion_message")
                if cm2 and cm2.get("content", {}).get("text"):
                    assistant_text = cm2["content"]["text"]
                    self.add_assistant_message(assistant_text)
                else:
                    self.add_assistant_message("[ERROR] No assistant message after tool call.")
            else:
                # Normal assistant message
                content = cm.get("content", {})
                text = content.get("text") if isinstance(content, dict) else content
                if text is None:
                    text = "[No response]"
                self.add_assistant_message(str(text))
                # Attempt auto code extraction & save
                extract_and_save_code(str(text))
            self.display_history()

def validate_registered_tools(deep: bool = False):
    print("\n[Tool Validation] Registered tools:")
    for tool_name, (schema, handler) in tool_registry.items():
        style = 'function' if 'function' in schema else 'cli'
        handler_type = 'custom' if handler is not run_cli_tool else 'generic'
        print(f"- {tool_name} ({style}) handler={handler_type}")
        if deep and handler is not run_cli_tool and tool_name == 'generate_ahk_code':
            try:
                preview = handler({'prompt': 'Return OK only.'})
                snippet = (preview[:40] + '...') if isinstance(preview, str) and len(preview) > 43 else preview
                print(f"  Sample OK call -> {snippet}")
            except Exception as e:
                print(f"  [WARN] Deep test failed: {e}")
    print("[Tool Validation] Done.\n")

if __name__ == "__main__":
    deep = os.environ.get('LLAMA_TOOL_DEEP_TEST') == '1'
    validate_registered_tools(deep=deep)
    ChatSession().chat()
