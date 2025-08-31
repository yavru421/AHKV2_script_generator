"""
Enhanced AHK v2 Validator
=========================

Goal: Catch common AHK v1 -> v2 issues that the simpler validators miss and
provide concrete auto-fix suggestions so that a script that "validates" is
far more likely to actually run under AutoHotkey v2.

This validator focuses on the biggest sources of silent failure observed in
generated scripts:
 1. Legacy command-style syntax (Cmd, Param1, Param2, ...) instead of v2
    function-call style (Cmd(Param1, Param2)).
 2. Deprecated / renamed commands (SoundSet/SoundGet/TrayTip, etc.).
 3. Hotkey blocks missing braces or return.
 4. Unbalanced braces / parens / quotes.
 5. Provides an optional auto-fix preview for simple deterministic rewrites.

It does NOT attempt to be a full parser; instead it applies targeted heuristics
for high-confidence detection with low false positive rate.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Commands that in v2 must be used as functions. (Not exhaustive, focus on those we saw.)
COMMAND_STYLE_KEYWORDS = {
    "MsgBox",
    "TrayTip",
    "Send",
    "Click",
    "Run",
    "Sleep",
    "SoundSet",
    "SoundGet",
    "SoundSetMute",
    "SoundGetMute",
}

# Remapping / guidance for deprecated v1-era names.
DEPRECATED_REMAP = {
    "SoundSet": "SoundSetVolume() or SoundSetMute() (toggle: SoundSetMute(-1))",
    "SoundGet": "SoundGetVolume() or SoundGetMute()",
    # Provide modern function call examples for common command-style patterns
    "TrayTip": "TrayTip('Title', 'Text')",
    "MsgBox": "MsgBox('Text')",
}

HOTKEY_PATTERN = re.compile(r"^([^;].*?)::(.*)$")  # Capture hotkey definitions


@dataclass
class ValidationIssue:
    line_no: int
    severity: str  # 'error' | 'warning' | 'info'
    message: str
    original: str
    suggestion: Optional[str] = None

    def format(self) -> str:
        base = f"{self.severity.upper()}: Line {self.line_no}: {self.message}"  # noqa: E501
        if self.suggestion:
            base += f" | Suggestion: {self.suggestion}"
        return base


def _split_command_parameters(raw: str) -> List[str]:
    """Split command-style parameters (comma separated) ignoring commas in quotes.

    This is intentionally simple and not a full CSV parser. It handles:
      - Quoted segments with single or double quotes.
      - Escaped quotes are not processed (AHK v1 rarely used them here).
    """
    parts: List[str] = []
    current = []
    in_quote: Optional[str] = None
    for ch in raw:
        if in_quote:
            if ch == in_quote:
                in_quote = None
            current.append(ch)
        else:
            if ch in ('"', "'"):
                in_quote = ch
                current.append(ch)
            elif ch == ',':
                parts.append(''.join(current).strip())
                current = []
            else:
                current.append(ch)
    if current:
        parts.append(''.join(current).strip())
    # Remove empty trailing params
    while parts and parts[-1] == '':
        parts.pop()
    return parts


def _auto_command_to_function(line: str) -> Optional[str]:
    """Convert a v1 command-style line to a v2 function call if safe.

    Only attempts when the pattern is high confidence: Keyword, params...
    Returns None if no safe rewrite.
    """
    # Pattern: Command, param1, param2 ... (no leading '#', not a hotkey)
    m = re.match(r"^(?P<cmd>[A-Za-z_][A-Za-z0-9_]*)\s*,\s*(?P<rest>.*)$", line)
    if not m:
        return None
    cmd = m.group('cmd')
    if cmd not in COMMAND_STYLE_KEYWORDS:
        return None
    rest = m.group('rest').strip()
    params = _split_command_parameters(rest)
    # Simplistic heuristic: wrap bare words (no quotes, not digits, not expression chars) in quotes.
    fixed_params: List[str] = []
    for p in params:
        if not p:
            continue
        if re.match(r"^[A-Za-z0-9_]+$", p):
            # Wrap in quotes for safety
            fixed_params.append(f"'{p}'")
        else:
            fixed_params.append(p)
    call = f"{cmd}({', '.join(fixed_params)})"
    return call


def validate_ahk_script_enhanced(script_text: str, auto_fix_preview: bool = True) -> Tuple[bool, List[ValidationIssue], Optional[str]]:
    """Validate script and optionally produce an auto-fix preview.

    Returns (is_valid, issues, fixed_preview)
    is_valid is False if any 'error' issues were found.
    fixed_preview is a transformed script (best-effort) if auto_fix_preview is True.
    """
    if not script_text or not script_text.strip():
        return False, [ValidationIssue(0, 'error', 'Empty script', '')], None

    lines = script_text.splitlines()
    issues: List[ValidationIssue] = []
    transformed: List[str] = []

    brace_balance = 0
    paren_balance = 0
    in_hotkey_block = False

    for idx, original_line in enumerate(lines, start=1):
        line = original_line.rstrip('\n')
        stripped = line.strip()
        if not stripped or stripped.startswith(';'):
            transformed.append(line)
            continue

        # Track balances (rough)
        brace_balance += stripped.count('{') - stripped.count('}')
        paren_balance += stripped.count('(') - stripped.count(')')

        # Hotkey detection
        hm = HOTKEY_PATTERN.match(stripped)
        if hm:
            in_hotkey_block = True
            # If there's inline code after ::, ensure it is function style
            after = hm.group(2).strip()
            if after and not after.startswith('{') and ',' in after:
                issues.append(ValidationIssue(idx, 'warning', 'Possible v1 command syntax inside hotkey', original_line))
            transformed.append(line)
            continue

        # Closing hotkey block detection
        if in_hotkey_block and stripped == '}':
            in_hotkey_block = False
            transformed.append(line)
            continue

        # Detect deprecated commands / legacy command-style usage
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*,", stripped):
            cmd_name = stripped.split(',', 1)[0].strip()
            msg = 'Legacy command-style syntax not valid in v2; use function call syntax.'
            suggestion = DEPRECATED_REMAP.get(cmd_name)
            auto_line = None
            if auto_fix_preview:
                auto_line = _auto_command_to_function(stripped)
            if auto_line:
                suggestion = suggestion or auto_line
                transformed.append(auto_line)
            else:
                transformed.append(line)
            issues.append(ValidationIssue(idx, 'error', msg, original_line, suggestion))
            continue

        # Deprecated function names inside expressions (e.g., SoundSet(...)) - supply guidance
        for deprecated, repl in DEPRECATED_REMAP.items():
            # Whole word and not part of something longer
            if re.search(rf"\b{re.escape(deprecated)}\b", stripped):
                # If already using parentheses, treat as warning instead of error
                sev = 'warning'
                issues.append(ValidationIssue(idx, sev, f"Use modern variant instead of '{deprecated}'.", original_line, repl))

        transformed.append(line)

    if brace_balance != 0:
        issues.append(ValidationIssue(0, 'error', f'Unbalanced braces: {brace_balance} net', ''))
    if paren_balance != 0:
        issues.append(ValidationIssue(0, 'error', f'Unbalanced parentheses: {paren_balance} net', ''))

    # Simple unmatched quotes scan (per line)
    for idx, original_line in enumerate(lines, start=1):
        if original_line.count('"') % 2 != 0 or original_line.count("'") % 2 != 0:
            issues.append(ValidationIssue(idx, 'error', 'Unmatched quotes', original_line))

    is_valid = not any(i.severity == 'error' for i in issues)
    fixed_preview = None
    if auto_fix_preview:
        fixed_preview = '\n'.join(transformed)
    return is_valid, issues, fixed_preview


def validate_ahk_script(script_text: str) -> bool:
    """Compatibility shim so this module can be used like the others.

    Prints issues and returns boolean validity.
    """
    valid, issues, _ = validate_ahk_script_enhanced(script_text, auto_fix_preview=False)
    for issue in issues:
        print(issue.format())
    if valid:
        print('Validation: OK (enhanced)')
    return valid


if __name__ == '__main__':
    import argparse, sys, pathlib
    p = argparse.ArgumentParser(description='Enhanced AHK v2 validator')
    p.add_argument('script', help='Path to .ahk script file')
    p.add_argument('--preview-fix', action='store_true', help='Show auto-fix preview')
    args = p.parse_args()
    path = pathlib.Path(args.script)
    if not path.is_file():
        print(f"ERROR: File not found: {path}")
        sys.exit(1)
    text = path.read_text(encoding='utf-8', errors='ignore')
    valid, issues, fixed = validate_ahk_script_enhanced(text, auto_fix_preview=args.preview_fix)
    for issue in issues:
        print(issue.format())
    print(f"Result: {'VALID' if valid else 'INVALID'}")
    if fixed and args.preview_fix:
        print('\n--- Auto-fix Preview (best-effort) ---\n')
        print(fixed)
    sys.exit(0 if valid else 2)
