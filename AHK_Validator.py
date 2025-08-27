"""
Smart AHK v2 Validator - Actually checks for real AHK v2 compatibility
"""
import re
from typing import List, Dict, Set

# Known AHK v2 functions and their correct syntax
AHK_V2_FUNCTIONS = {
    'MsgBox', 'Send', 'Click', 'Sleep', 'Run', 'WinActivate', 'WinClose', 'WinMove',
    'SoundSetVolume', 'SoundSetMute', 'SoundGetVolume', 'SoundGetMute',
    'TrayTip', 'ToolTip', 'FileRead', 'FileAppend', 'RegRead', 'RegWrite',
    'SetTimer', 'WinGetTitle', 'WinGetPos', 'WinGetClass', 'ControlSend',
    'FormatTime', 'A_Now', 'A_ScreenWidth', 'A_ScreenHeight'
}

# Functions that changed from v1 to v2 (common mistakes)
V1_TO_V2_CHANGES = {
    'SoundGet': 'SoundGetVolume or SoundGetMute',
    'SoundSet': 'SoundSetVolume or SoundSetMute',
    'StringReplace': 'StrReplace',
    'StringSplit': 'StrSplit',
    'StringLen': 'StrLen',
    'IfWinActive': 'if WinActive()',
    'IfWinExist': 'if WinExist()',
    'SetWorkingDir': 'DirCreate or DirSelect',
    'FileSelectFile': 'FileSelect',
    'FileSelectFolder': 'DirSelect',
    'Transform': 'various v2 functions',
    'Loop, Parse': 'Loop Parse',
    'Loop, Read': 'Loop Read',
    'Loop, Files': 'Loop Files'
}

def validate_ahk_script(script_text: str) -> bool:
    """
    Smart AHK v2 validator that catches real compatibility issues.
    """
    if not script_text or not script_text.strip():
        print("Validation error: Empty script")
        return False

    lines = script_text.split('\n')
    errors = []
    warnings = []
    has_v2_directive = False

    for line_num, line in enumerate(lines, 1):
        original_line = line
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith(';'):
            continue

        # Check for v2 directive
        if '#Requires AutoHotkey v2' in line:
            has_v2_directive = True
            continue

        # Check for v1-style function calls (comma separated parameters)
        v1_function_pattern = r'(\w+),\s*[^;]*$'
        if re.search(v1_function_pattern, line) and '::' not in line and not line.startswith('#'):
            # Common v1 patterns that don't work in v2
            if any(pattern in line for pattern in ['MsgBox,', 'Send,', 'SoundSet,', 'SoundGet,']):
                errors.append(f"Line {line_num}: v1 syntax detected. Use parentheses: MsgBox('text'), Send('key')")

        # Check for deprecated v1 functions
        for v1_func, v2_replacement in V1_TO_V2_CHANGES.items():
            # Only match whole words, not parts of other function names
            if re.search(r'\b' + re.escape(v1_func) + r'\b', line):
                # Don't flag if it's actually the correct v2 version
                if v1_func == 'SoundSet' and ('SoundSetMute' in line or 'SoundSetVolume' in line):
                    continue
                if v1_func == 'SoundGet' and ('SoundGetMute' in line or 'SoundGetVolume' in line):
                    continue
                errors.append(f"Line {line_num}: '{v1_func}' not available in v2. Use: {v2_replacement}")

        # Check for specific problematic patterns
        if 'SoundGetMute(' in line:
            # This function exists but check if it's used correctly
            if not re.search(r'SoundGetMute\(\)', line):
                warnings.append(f"Line {line_num}: SoundGetMute() takes no parameters in v2")

        # Check for missing braces on hotkeys
        if '::' in line and not line.endswith('::'):
            # Single line hotkey
            continue
        elif line.endswith('::'):
            # Check if next non-empty line has opening brace or is indented
            next_line_found = False
            for next_line_num in range(line_num, min(line_num + 3, len(lines))):
                if next_line_num < len(lines):
                    next_line = lines[next_line_num].strip()
                    if next_line and not next_line.startswith(';'):
                        if not (next_line.startswith('{') or lines[next_line_num].startswith('    ') or lines[next_line_num].startswith('\t')):
                            errors.append(f"Line {line_num}: Hotkey missing opening brace or proper indentation")
                        next_line_found = True
                        break

    # Check brace balance
    brace_count = script_text.count('{') - script_text.count('}')
    if brace_count != 0:
        errors.append(f"Unbalanced braces: {brace_count} extra {'opening' if brace_count > 0 else 'closing'}")

    # Check parentheses balance
    paren_count = script_text.count('(') - script_text.count(')')
    if paren_count != 0:
        errors.append(f"Unbalanced parentheses: {paren_count} extra {'opening' if paren_count > 0 else 'closing'}")

    # Warnings
    if not has_v2_directive and len(script_text.strip()) > 10:
        warnings.append("Consider adding '#Requires AutoHotkey v2.0' directive")

    # Report results
    if warnings:
        for warning in warnings:
            print(f"Validation warning: {warning}")

    if errors:
        for error in errors:
            print(f"Validation error: {error}")
        return False

    print("Validation: OK")
    return True

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python AHK_Validator.py <script.ahk>")
        sys.exit(1)

    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            script = f.read()
        result = validate_ahk_script(script)
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)
