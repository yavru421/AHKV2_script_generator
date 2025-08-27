"""
Simplified AHK v2 Validator - More Permissive Approach
Focuses on basic structure validation rather than full syntax parsing.
"""
import re
from typing import List, Tuple

def validate_ahk_script_simple(script_text: str) -> bool:
    """
    Simplified AHK v2 validation that's much more permissive.
    Only checks for major structural issues, not detailed syntax.
    """
    if not script_text or not script_text.strip():
        print("Validation error: Empty script")
        return False

    lines = script_text.split('\n')
    errors = []

    # Check for basic structural issues
    brace_count = 0
    paren_count = 0

    for line_num, line in enumerate(lines, 1):
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith(';'):
            continue

        # Count braces and parentheses
        brace_count += line.count('{') - line.count('}')
        paren_count += line.count('(') - line.count(')')

        # Check for obvious syntax errors
        if line.endswith('::') and len(line) == 2:
            errors.append(f"Line {line_num}: Invalid hotkey definition")

        # Check for unmatched quotes (basic check)
        single_quotes = line.count("'")
        double_quotes = line.count('"')
        if single_quotes % 2 != 0 or double_quotes % 2 != 0:
            # Only error if it's not in a comment context
            if not any(line.startswith(prefix) for prefix in [';', '//', '/*']):
                errors.append(f"Line {line_num}: Unmatched quotes")

    # Check final brace/paren balance
    if brace_count != 0:
        errors.append(f"Unbalanced braces: {brace_count} extra {'opening' if brace_count > 0 else 'closing'}")

    if paren_count != 0:
        errors.append(f"Unbalanced parentheses: {paren_count} extra {'opening' if paren_count > 0 else 'closing'}")

    # Look for some positive indicators that this is AHK code
    ahk_indicators = [
        r'#Requires\s+AutoHotkey',
        r'#SingleInstance',
        r'::',  # Hotkeys/hotstrings
        r'MsgBox',
        r'Send',
        r'WinActivate',
        r'Run[,\s]',
        r'Sleep[,\s]',
        r'Click',
        r'ControlSend',
        r'SetTimer',
        r'Gui[,\s\+]',
        r'FormatTime',
        r'FileRead',
        r'RegRead',
        r'SoundGet',
        r'SoundSet',
    ]

    has_ahk_content = any(re.search(pattern, script_text, re.IGNORECASE) for pattern in ahk_indicators)

    if not has_ahk_content and len(script_text.strip()) > 50:
        # Only warn for longer scripts that don't look like AHK
        print("Warning: Script doesn't contain recognizable AHK patterns")

    if errors:
        for error in errors:
            print(f"Validation error: {error}")
        return False

    print("Validation: OK")
    return True

def validate_ahk_script(script_text: str) -> bool:
    """
    Main validation function - uses the simple validator for now.
    Falls back to the simple validator if the complex one fails.
    """
    try:
        # Use the simple validator which is much more permissive
        return validate_ahk_script_simple(script_text)
    except Exception as e:
        print(f"Validation error: {e}")
        return False

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python AHK_Validator_Simple.py <script.ahk>")
        sys.exit(1)

    try:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            script = f.read()
        result = validate_ahk_script(script)
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)
