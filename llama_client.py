import os
import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Try to import clients
try:
    from llama_api_client import LlamaAPIClient
    HAS_OFFICIAL_CLIENT = True
except ImportError:
    HAS_OFFICIAL_CLIENT = False

try:
    import openai
    HAS_OPENAI_CLIENT = True
except ImportError:
    HAS_OPENAI_CLIENT = False

# Always import requests as fallback
import requests

# Constants
MAX_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.3
TIMEOUT = 45
LOG_FILE = "llama_runlog.txt"
MAX_LOG_MESSAGE_LENGTH = 1200

# Optional .env loading for convenience
try:
    from dotenv import load_dotenv
    env_path = Path('.') / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except Exception:
    pass

# Logging setup
logger = logging.getLogger("llama_client")
handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
if not logger.hasHandlers():
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

def get_api_url() -> str:
    """Get the Llama API URL from the environment variable."""
    return os.environ.get("LLAMA_API_URL", "")

def get_api_key() -> str:
    """Get the Llama API key from the environment variable."""
    return os.environ.get("LLAMA_API_KEY", "")

def get_model() -> str:
    """Get the model from the environment variable."""
    return os.environ.get("LLAMA_MODEL", "Llama-3.3-70B-Instruct")

def get_api_type() -> str:
    """Determine which API type to use based on environment variables."""
    # Check if OpenAI compatibility is explicitly disabled
    if os.environ.get("DISABLE_OPENAI_COMPATIBILITY", "false").lower() == "true":
        return "llama"

    api_url = get_api_url().lower()

    # Check for Llama API patterns FIRST (before generic patterns)
    if "llama.com" in api_url or "api.llama.com" in api_url:
        return "llama"

    # Check for OpenAI API patterns
    if "openai.com" in api_url or "api.openai.com" in api_url:
        return "openai"

    # Check for common OpenAI-compatible endpoints
    if any(pattern in api_url for pattern in ["ollama", "lmstudio", "together", "groq"]):
        return "openai_compatible"

    # Default to Llama (your preference)
    return "llama"

def build_payload(prompt: str, api_url: str, model: str) -> Dict[str, Any]:
    """Build the payload for the Llama API call with hardened anti-v1 instructions."""
    v2_system = (
        "You are an AutoHotkey v2 scripting specialist. OUTPUT MUST BE STRICT AutoHotkey v2. "
        "Hard requirements: (1) Begin with '#Requires AutoHotkey v2.0' (2) Use ONLY function syntax for former v1 commands: MsgBox(''), Send(''), TrayTip('title','text'), SoundSetMute(-1), SoundGetMute(), SoundSetVolume(n), SoundGetVolume(). "
        "(3) NEVER use legacy comma command syntax like 'MsgBox,', 'Send,', 'SoundSet,' or 'SoundGet,'. "
        "(4) Use braces { } for multi-line hotkey bodies. "
        "If user asks for legacy syntax, UPGRADE it to v2 instead. Return ONLY code without explanations."
    )
    if "/chat/completions" in api_url:
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": v2_system},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": MAX_TOKENS,
            "temperature": float(os.environ.get("LLAMA_TEMPERATURE", DEFAULT_TEMPERATURE))
        }
    else:
        # In completion-style APIs put the full instruction into the prompt itself
        data = {
            "prompt": (
                f"{v2_system}\n\nUSER REQUEST: {prompt}\n\nReturn only AutoHotkey v2 code:"),
            "max_tokens": MAX_TOKENS,
            "temperature": float(os.environ.get("LLAMA_TEMPERATURE", DEFAULT_TEMPERATURE)),
            "stop": None
        }
    return data

# -------------------------- Lockdown Helpers --------------------------
V1_COMMAND_PATTERN = re.compile(r"\b(MsgBox|Send|SoundSet|SoundGet|TrayTip|Sleep|Run|Click|WinActivate|WinClose|WinMove)\s*,", re.IGNORECASE)

def detect_v1_syntax(code: str) -> List[str]:
    """Return list of legacy v1-style command lines found (comma invocation style)."""
    findings = []
    for ln, line in enumerate(code.splitlines(), 1):
        if V1_COMMAND_PATTERN.search(line):
            findings.append(f"Line {ln}: {line.strip()}")
    return findings

def ensure_v2_directive(code: str) -> str:
    if not re.search(r"#Requires\s+AutoHotkey\s+v2", code, re.IGNORECASE):
        return "#Requires AutoHotkey v2.0\n#SingleInstance Force\n" + code.lstrip()
    return code

def basic_auto_convert_v1_to_v2(code: str) -> Tuple[str, List[str]]:
    """Lightweight conversions for most common legacy patterns. Returns (new_code, changes)."""
    changes = []
    # Toggle/Mute Sound patterns FIRST to avoid generic capture
    conversions = [
        # Sound toggles
        (r"(?mi)^[ \t]*SoundSet,\s*\+?1\s*,\s*,\s*(Toggle|Mute|Unmute)\b.*$", "SoundSetMute(-1)", "SoundSet toggle/mute -> SoundSetMute(-1)"),
        # Sound get mute / volume
        (r"(?mi)^[ \t]*SoundGet,\s*(\w+)\s*,\s*Master\s*,\s*Mute\b.*$", r"\1 := SoundGetMute()", "SoundGet mute -> var := SoundGetMute()"),
        (r"(?mi)^[ \t]*SoundGet,\s*(\w+)\s*,\s*Master\s*,\s*Volume\b.*$", r"\1 := SoundGetVolume()", "SoundGet volume -> var := SoundGetVolume()"),
        # Generic core command rewrites
        (r"(?mi)^[ \t]*MsgBox,\s*(.+)$", r"MsgBox(\1)", "MsgBox -> function"),
        (r"(?mi)^[ \t]*Send,\s*(.+)$", r"Send(\1)", "Send -> function"),
        (r"(?mi)^[ \t]*Sleep,\s*(\d+)\s*$", r"Sleep(\1)", "Sleep -> function"),
        (r"(?mi)^[ \t]*Run,\s*(.+)$", r"Run(\1)", "Run -> function"),
        (r"(?mi)^[ \t]*Click,\s*(.+)$", r"Click(\1)", "Click -> function"),
        (r"(?mi)^[ \t]*WinActivate,\s*(.+)$", r"WinActivate(\1)", "WinActivate -> function"),
        (r"(?mi)^[ \t]*TrayTip,\s*([^,\r\n]+)\s*,\s*([^,\r\n]+).*$", r"TrayTip(\1, \2)", "TrayTip -> function"),
        # Remaining generic SoundSet (value based) -> SoundSetVolume(value)
        (r"(?mi)^[ \t]*SoundSet,\s*([^,\r\n]+)\s*,.*$", r"SoundSetVolume(\1)", "SoundSet value -> SoundSetVolume()"),
    ]
    new_code = code
    for pattern, repl, desc in conversions:
        updated = re.sub(pattern, repl, new_code)
        if updated != new_code:
            new_code = updated
            changes.append(desc)
    # Normalize quotes to double quotes when we wrapped arguments
    new_code = re.sub(r"MsgBox\('([^']*)'\)", r'MsgBox("\1")', new_code)
    return new_code, changes

def sanitize_generation(prompt: str, code: str) -> str:
    """Enforce v2: add directive, convert legacy, and append comment with applied changes."""
    original = code
    code = ensure_v2_directive(code)
    findings = detect_v1_syntax(code)
    all_changes: List[str] = []
    if findings:
        logger.warning(f"Detected legacy v1 syntax in generation ({len(findings)} lines). Auto-converting.")
        code, changes = basic_auto_convert_v1_to_v2(code)
        all_changes.extend(changes)
        # Re-check after conversion
        if detect_v1_syntax(code):
            # Still present -> mark visibly
            code = (
                "; WARNING: Residual legacy syntax could not be auto-converted fully. Review manually.\n" + code
            )
    if all_changes:
        code = "; Auto conversions: " + ", ".join(sorted(set(all_changes))) + "\n" + code
    # Final validation (best-effort) using strict validator if available
    try:
        from AHK_Validator import validate_ahk_script as _strict_validate
        import io, sys
        buff = io.StringIO()
        old = sys.stdout
        sys.stdout = buff
        valid = _strict_validate(code)
        sys.stdout = old
        v_out = buff.getvalue().strip().replace('\n', ' | ')
        if not valid:
            logger.error(f"Post-generation validation failed: {v_out[:300]}")
            code = f"; VALIDATION FAILED (auto conversion attempted) -> {v_out}\n" + code
    except Exception as e:
        logger.debug(f"Validator not applied: {e}")
    return code

def make_api_call(api_url: str, payload: Dict[str, Any], api_key: str) -> str:
    """Make the Llama API call."""
    headers = {"Content-Type": "application/json"}
    if not api_key:
        return "[ERROR] Missing LLAMA_API_KEY."
    headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = requests.post(api_url, json=payload, headers=headers, timeout=TIMEOUT)
        logger.info(f"Llama API response status={resp.status_code}")
        if resp.status_code == 404 and not api_url.endswith('/chat/completions'):
            # Auto retry with chat/completions suffix BEFORE raising
            retry_url = api_url.rstrip('/') + '/chat/completions'
            logger.warning(f"404 at base URL, retrying with {retry_url}")
            resp = requests.post(retry_url, json=payload, headers=headers, timeout=TIMEOUT)
            logger.info(f"Retry status={resp.status_code}")
        if resp.status_code in (400, 401, 403):
            snippet = resp.text[:400]
            logger.error(f"Client error {resp.status_code}: {snippet}")
            if resp.status_code == 401:
                return "[ERROR] 401 Unauthorized – verify LLAMA_API_KEY and that it has access to the model."
            if resp.status_code == 403:
                return "[ERROR] 403 Forbidden – key lacks permission for model or endpoint."
            return f"[ERROR] 400 Bad Request – {snippet}"
        resp.raise_for_status()
        try:
            result = resp.json()
        except ValueError:
            logger.error(f"Non-JSON response: {resp.text[:400]}")
            return f"[ERROR] Non-JSON response: {resp.text[:200]}"
        # Universal debug dump if enabled
        if os.environ.get("LLAMA_DEBUG") == '1':
            logger.warning(f"DEBUG RAW JSON: {str(result)[:MAX_LOG_MESSAGE_LENGTH]}")
        # Explicit error object handling
        for ek in ("error", "detail"):
            if ek in result and isinstance(result[ek], (str, dict)):
                err_val = result[ek]
                if isinstance(err_val, dict):
                    msg = err_val.get('message') or err_val.get('error') or str(err_val)
                else:
                    msg = err_val
                return f"[ERROR] API reported: {msg}"[:500]
        # Chat format
        code = ""
        if isinstance(result.get("choices"), list) and result["choices"]:
            choice = result["choices"][0]
            # Try multiple possible fields
            code = (
                choice.get("message", {}).get("content")
                or choice.get("content")
                or choice.get("text")
                or ""
            )
        if not code:
            # Some providers nest output differently
            for k in ("output", "data", "result"):
                v = result.get(k)
                if isinstance(v, str) and v.strip():
                    code = v
                    break
                if isinstance(v, dict):
                    inner = v.get("text") or v.get("content")
                    if inner:
                        code = inner
                        break
        if not code:
            # New Llama format: completion_message.content.text
            cm = result.get('completion_message')
            if isinstance(cm, dict):
                content = cm.get('content')
                if isinstance(content, dict):
                    text_val = content.get('text')
                    if isinstance(text_val, str) and text_val.strip():
                        code = text_val
        if not code:
            # Final fallback: return serialized JSON snippet for diagnostics
            snippet = str(result)[:600]
            logger.warning(f"Empty code extracted. Raw JSON snippet: {snippet}")
            return "[ERROR] Empty response content. Raw JSON snippet logged for diagnostics."
        code = code.strip()
        # Strip Markdown fences if present
        if code.startswith('```'):
            # remove first fence line
            parts = code.split('\n')
            if parts:
                # drop leading ```lang and trailing ```
                if parts[0].startswith('```'):
                    parts = parts[1:]
                # Check for trailing ``` more carefully
                while parts and parts[-1].strip() in ('```', ''):
                    parts = parts[:-1]
                code = '\n'.join(parts).strip()
        logger.info(f"Llama API result chars={len(code)}")
        return code or "[ERROR] Empty response from Llama API."
    except requests.Timeout:
        return "[ERROR] Request timed out. Increase timeout or simplify prompt."
    except Exception as e:
        logger.error(f"Llama API error: {e}")
        return f"[ERROR] {e}"

def generate_ahk_code_openai(prompt: str) -> str:
    """Generate AHK v2 code using OpenAI or OpenAI-compatible API."""
    api_url = get_api_url()
    api_key = get_api_key()
    model = get_model()

    if not api_url or not api_key:
        return "[ERROR] Missing API configuration for OpenAI-compatible endpoint."

    try:
        # Use openai library if available and it's actual OpenAI
        if HAS_OPENAI_CLIENT and "openai.com" in api_url.lower():
            import openai # type: ignore
            client = openai.OpenAI(api_key=api_key)

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an AutoHotkey v2 scripting specialist. Return ONLY valid AHK v2 code unless asked otherwise."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_tokens=MAX_TOKENS,
                temperature=float(os.environ.get("LLAMA_TEMPERATURE", DEFAULT_TEMPERATURE))
            )

            content = response.choices[0].message.content
            code = content.strip() if content is not None else ""
            logger.info(f"OpenAI client result chars={len(code)}")

        else:
            # Use requests for OpenAI-compatible endpoints
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }

            # Ensure URL ends with the right endpoint
            if not api_url.endswith('/chat/completions'):
                api_url = api_url.rstrip('/') + '/v1/chat/completions'

            payload = {
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an AutoHotkey v2 expert. Generate ONLY working AHK v2 code. Always include '#Requires AutoHotkey v2.0' at the top. Use proper v2 syntax: MsgBox('text'), Send('{key}'), SoundSetMute(-1), SoundGetMute(), TrayTip('title', 'text'). Use braces {} for hotkey bodies. No v1 comma syntax. Test your code mentally before responding."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": MAX_TOKENS,
                "temperature": float(os.environ.get("LLAMA_TEMPERATURE", DEFAULT_TEMPERATURE))
            }

            response = requests.post(api_url, json=payload, headers=headers, timeout=TIMEOUT)
            response.raise_for_status()

            result = response.json()
            code = result["choices"][0]["message"]["content"].strip()
            logger.info(f"OpenAI-compatible result chars={len(code)}")

        # Strip Markdown fences if present
    if code.startswith('```'):
            parts = code.split('\n')
            if parts and parts[0].startswith('```'):
                parts = parts[1:]
            while parts and parts[-1].strip() in ('```', ''):
                parts = parts[:-1]
            code = '\n'.join(parts).strip()
    code = sanitize_generation(prompt, code)
    return code or "[ERROR] Empty response from API."

    except Exception as e:
        logger.error(f"OpenAI-compatible client error: {e}")
        return f"[ERROR] OpenAI-compatible client failed: {e}"

def generate_ahk_code_llama_official(prompt: str) -> str:
    """Generate AHK v2 code using the official LlamaAPIClient."""
    if not HAS_OFFICIAL_CLIENT:
        return "[ERROR] Official client not available"

    try:
        from llama_api_client import LlamaAPIClient
        client = LlamaAPIClient()

        response = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are an AutoHotkey v2 scripting specialist. Generate ONLY AutoHotkey v2 syntax. Use parentheses for function calls like MsgBox('text'), Send('{key}'), SoundSetMute(-1). Use braces {} for hotkey bodies. No v1 comma syntax. Return only code."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model=get_model(),
            stream=False,
            temperature=float(os.environ.get("LLAMA_TEMPERATURE", DEFAULT_TEMPERATURE)),
            max_completion_tokens=MAX_TOKENS,
            top_p=0.9,
            repetition_penalty=1
        )

        # Extract content from response
        if isinstance(response, dict) and "choices" in response and response["choices"]:
            choice = response["choices"][0]
            message = choice.get("message", {})
            code = message.get("content", "").strip()
            logger.info(f"Official client result chars={len(code)}")

            # Strip Markdown fences if present
            if code.startswith('```'):
                parts = code.split('\n')
                if parts and parts[0].startswith('```'):
                    parts = parts[1:]
                while parts and parts[-1].strip() in ('```', ''):
                    parts = parts[:-1]
                code = '\n'.join(parts).strip()
            code = sanitize_generation(prompt, code)
            return code or "[ERROR] Empty response from Llama API."

        return "[ERROR] Unexpected response format from official client."

    except Exception as e:
        logger.error(f"Official client error: {e}")
        return f"[ERROR] Official client failed: {e}"

def generate_ahk_code(prompt: str) -> str:
    """Generate AHK v2 code from a natural language prompt using the best available API."""
    api_type = get_api_type()
    logger.info(f"Using API type: {api_type} for prompt_len={len(prompt)}")

    # Try the appropriate client based on API type
    if api_type in ["openai", "openai_compatible"]:
        result = generate_ahk_code_openai(prompt)
        if not result.startswith('[ERROR]'):
            return result
        logger.warning("OpenAI-compatible client failed, trying Llama")

    # Try official Llama client if available
    if HAS_OFFICIAL_CLIENT and api_type == "llama":
        result = generate_ahk_code_llama_official(prompt)
        if not result.startswith('[ERROR]'):
            return result
        logger.warning("Official Llama client failed, falling back to requests")

    # Fallback to requests-based implementation
    api_url = get_api_url().rstrip('/')
    if api_url.endswith('/v1'):
        api_url += '/chat/completions'
    api_key = get_api_key()
    model = get_model()
    if not api_url or not api_key:
        return (
            "[ERROR] Missing API configuration. Set these environment variables:\n"
            "LLAMA_API_URL=https://api.openai.com/v1 (or your provider URL)\n"
            "LLAMA_API_KEY=YOUR_KEY_HERE\n"
            "LLAMA_MODEL=gpt-4 (or your model name)\n"
            "Then restart or click Generate again."
        )
    logger.info(f"Fallback API call: model={model} url={api_url} prompt_len={len(prompt)}")
    payload = build_payload(prompt, api_url, model)
    result = make_api_call(api_url, payload, api_key)
    if result.startswith('[ERROR]'):
        fb = _fallback_generate(prompt)
        return fb + "\n\n; NOTE: Above produced by offline fallback due to API error:\n; " + result
    return sanitize_generation(prompt, result)

def fix_ahk_code(original_prompt: str, broken_code: str) -> str:
    """
    Smart AHK v2 code fixer that applies known fixes before asking AI.
    """
    fixed_code = broken_code
    fixes_applied = []

    # Apply automatic fixes for common AHK v2 issues

    # 1. Add v2 directive if missing
    if not re.search(r'#Requires\s+AutoHotkey\s+v2', fixed_code, re.IGNORECASE):
        fixed_code = "#Requires AutoHotkey v2.0\n#SingleInstance Force\n\n" + fixed_code
        fixes_applied.append("Added v2 directive")

    # 2. Fix v1 comma syntax to v2 parentheses
    v1_fixes = {
        # Order matters: handle sound toggles first
        r'(?mi)^[ \t]*SoundSet,\s*\+?1\s*,\s*,\s*(Toggle|Mute|Unmute)\b.*$': 'SoundSetMute(-1)',
        r'\bMsgBox,\s*([^,\r\n]+)': r'MsgBox("\1")',
        r'\bSend,\s*([^,\r\n]+)': r'Send(\1)',
        r'\bSleep,\s*(\d+)': r'Sleep(\1)',
        r'\bRun,\s*([^,\r\n]+)': r'Run(\1)',
        r'\bClick,\s*([^,\r\n]+)': r'Click(\1)',
        r'\bWinActivate,\s*([^,\r\n]+)': r'WinActivate(\1)',
        r'\bTrayTip,\s*([^,\r\n]+),\s*([^,\r\n]+)': r'TrayTip(\1, \2)',
    }

    for pattern, replacement in v1_fixes.items():
        old_code = fixed_code
        fixed_code = re.sub(pattern, replacement, fixed_code, flags=re.MULTILINE)
        if fixed_code != old_code:
            fixes_applied.append(f"Fixed v1 syntax: {pattern.split('\\')[1]}")

    # 3. Fix deprecated v1 functions
    deprecated_fixes = {
        r'(?mi)^[ \t]*SoundGet,\s*(\w+)\s*,\s*Master\s*,\s*Mute\b.*$': r'\1 := SoundGetMute()',
        r'(?mi)^[ \t]*SoundGet,\s*(\w+)\s*,\s*Master\s*,\s*Volume\b.*$': r'\1 := SoundGetVolume()',
        r'\bSoundSet,\s*([^,\r\n]+),\s*([^,\r\n]+),\s*([^,\r\n]+)': r'SoundSetVolume(\1)',
        r'\bStringReplace,\s*(\w+),\s*([^,\r\n]+),\s*([^,\r\n]+),\s*([^,\r\n]+)': r'\1 := StrReplace(\2, \3, \4)',
        r'\bStringSplit,\s*(\w+),\s*([^,\r\n]+),\s*([^,\r\n]+)': r'\1 := StrSplit(\2, \3)',
    }

    for pattern, replacement in deprecated_fixes.items():
        old_code = fixed_code
        fixed_code = re.sub(pattern, replacement, fixed_code, flags=re.MULTILINE)
        if fixed_code != old_code:
            fixes_applied.append("Fixed deprecated function")

    # 4. Fix hotkey brace issues
    lines = fixed_code.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        if '::' in line and line.strip().endswith('::'):
            # Single line hotkey needs proper formatting
            if i + 1 < len(lines) and lines[i + 1].strip():
                next_line = lines[i + 1].strip()
                if not next_line.startswith('{') and not next_line.startswith(';'):
                    # Need to add braces - insert opening brace after hotkey line
                    lines.insert(i + 1, '{')
                    # Find the end of the hotkey block
                    j = i + 2
                    while j < len(lines) and lines[j].strip() and not lines[j].strip().startswith('}'):
                        j += 1
                    # Insert closing brace
                    lines.insert(j, '}')
                    fixes_applied.append("Added missing hotkey braces")
        i += 1
    fixed_code = '\n'.join(lines)

    # 5. Fix quote issues (double quotes for strings)
    fixed_code = re.sub(r"'([^']*)'", r'"\1"', fixed_code)

    # 6. Fix common TrayTip syntax
    fixed_code = re.sub(r'TrayTip\s*\(\s*([^,)]+)\s*,\s*([^,)]+)\s*\)', r'TrayTip(\1, \2)', fixed_code)

    # If we made automatic fixes, validate and return if good
    if fixes_applied:
        from AHK_Validator import validate_ahk_script
        try:
            # Capture validation output
            import io
            import sys
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()

            is_valid = validate_ahk_script(fixed_code)

            validation_output = sys.stdout.getvalue()
            sys.stdout = old_stdout

            if is_valid:
                fixes_summary = "; Auto-fixes applied: " + ", ".join(fixes_applied) + "\n"
                return fixes_summary + fixed_code
        except Exception:
            pass

    # If automatic fixes weren't enough, ask AI for help
    detailed_fix_prompt = f"""Fix this AutoHotkey v2 script. Common issues to check:

1. Use #Requires AutoHotkey v2.0 directive
2. Use parentheses for functions: MsgBox('text'), Send('key'), not comma syntax
3. Use SoundSetMute(-1) and SoundGetMute(), not SoundSet/SoundGet
4. Use proper quotes: "text" not 'text'
5. Use braces for hotkeys: F1::{{ code }}
6. Use v2 syntax: if WinActive() not IfWinActive

Original request: {original_prompt}

Code to fix:
{broken_code}

Return ONLY the corrected AutoHotkey v2 code with proper syntax."""

    api_type = get_api_type()
    logger.info(f"Using API type: {api_type} for fix, prompt_len={len(detailed_fix_prompt)}")

    # Try the appropriate client based on API type
    if api_type in ["openai", "openai_compatible"]:
        result = generate_ahk_code_openai(detailed_fix_prompt)
        if not result.startswith('[ERROR]'):
            return result
        logger.warning("OpenAI-compatible client failed for fix, trying Llama")

    # Try official Llama client if available
    if HAS_OFFICIAL_CLIENT and api_type == "llama":
        result = generate_ahk_code_llama_official(detailed_fix_prompt)
        if not result.startswith('[ERROR]'):
            return result
        logger.warning("Official Llama client failed for fix, falling back to requests")

    # Fallback to requests-based implementation
    api_url = get_api_url().rstrip('/')
    if api_url.endswith('/v1'):
        api_url += '/chat/completions'
    api_key = get_api_key()
    model = get_model()

    if not api_url or not api_key:
        # Return automatic fixes if we can't reach API
        if fixes_applied:
            return f"; Auto-fixes applied: {', '.join(fixes_applied)}\n{fixed_code}"
        return "[ERROR] Missing API configuration for fixing script."

    logger.info(f"Fallback fix call: model={model} url={api_url} prompt_len={len(detailed_fix_prompt)}")
    payload = build_payload(detailed_fix_prompt, api_url, model)
    result = make_api_call(api_url, payload, api_key)

    if result.startswith('[ERROR]'):
        # Return automatic fixes as fallback
        if fixes_applied:
            return f"; Auto-fixes applied: {', '.join(fixes_applied)}\n{fixed_code}"
        return f"; ERROR: Could not fix script via API\n; {result}\n\n{broken_code}"

    result = sanitize_generation(original_prompt, result)
    return result
    p = prompt.lower()
    lines = [
        "; Auto-generated fallback AHK v2 script (no API)",
        "#Requires AutoHotkey v2.0",
        "#SingleInstance Force",
        "; Fallback generator enforces pure v2 syntax (no legacy commas)",
    ]
    """Heuristic offline fallback so user still gets something if API fails."""
    p = prompt.lower()
    lines = ["; Auto-generated fallback AHK v2 script (no API)", "#Requires AutoHotkey v2.0", "#SingleInstance Force"]
            "^!WheelUp:: Send('{Volume_Up}')",
            "^!WheelDown:: Send('{Volume_Down}')",
            "; Control volume with Ctrl+Alt + Mouse Wheel",
            "^!WheelUp::Send '{Volume_Up}'",
            "^!WheelDown::Send '{Volume_Down}'",
        ]
            "^!m:: {",
            "    SoundSetMute(-1)",
            "    TrayTip('Audio', 'Mute toggled')",
            "}",
            "    SoundSetMute -1",
            "    TrayTip 'Audio', 'Mute toggled', 1000",
            "}"
        ]
    if 'clipboard' in p:
        lines += [
            "    txt := A_Clipboard",
            "global ClipHist := []",
            "^!c:: {",
            "    txt := A_Clipboard",
            "    if (txt != '' && (ClipHist.Length() = 0 || ClipHist[1] != txt)) {",
            "        ClipHist.InsertAt(1, txt)",
            "        if ClipHist.Length() > 10",
            "            ClipHist.Pop()",
            "    }",
            "}",
            "^!v:: {",
            "    if ClipHist.Length() = 0 return",
            "    Gui gui: New +AlwaysOnTop -Resize",
            "    gui.Add('Text',, 'Select clipboard item:')",
            "    lb := gui.Add('ListBox','vPick w300 h200', ClipHist)",
            "    gui.Add('Button','Default','Paste')",
            "    gui.OnEvent('Close', (*) => gui.Destroy())",
            "    gui.OnEvent('Escape', (*) => gui.Destroy())",
            "    gui.OnEvent('Click', (*) => {",
            "            Send('^v')",
            "        if val != '' {",
            "            A_Clipboard := val",
            "            Send '^v'",
            "        }",
            "        gui.Destroy()",
            "    })",
            "    gui.Show()",
            "}"
        ]
    if len(lines) <= 3:  # Nothing matched
            "^!h:: MsgBox('Hello from fallback generator!')"
            "; Unable to infer specific intent, provide skeleton.",
            "; Hotkey example: Ctrl+Alt+H shows a message box.",
    script = '\n'.join(lines)
    script = sanitize_generation(prompt, script)
    return script
        ]
    lines.append("; End of fallback script")
    return '\n'.join(lines)

def diagnose_llama() -> str:
    """Return a multi-line diagnostic of current Llama env + a tiny test call (without large prompt)."""
    test_prompt = "Return the word OK only."
    os.environ.setdefault('LLAMA_TEMPERATURE', '0')
    out = [
        f"LLAMA_API_URL={os.environ.get('LLAMA_API_URL')}",
        f"LLAMA_MODEL={os.environ.get('LLAMA_MODEL')}",
        f"Key present={bool(os.environ.get('LLAMA_API_KEY'))}",
    ]
    try:
        r = generate_ahk_code(test_prompt)
        out.append(f"Test response: {r[:120]}")
    except Exception as e:
        out.append(f"Exception: {e}")
    return "\n".join(out)

# Example usage
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    if len(sys.argv) != 2:
        print("Usage: python llama_client.py <prompt>")
        sys.exit(1)
    prompt = sys.argv[1]
    result = generate_ahk_code(prompt)
    print(result)