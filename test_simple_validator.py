from AHK_Validator_Simple import validate_ahk_script

# Test with problematic characters from the log
test_script = """
; This is a comment
#Requires AutoHotkey v2.0
^j::MsgBox("Hello")
~LButton::Send("{Escape}")
"""

result = validate_ahk_script(test_script)
print(f"Validation result: {result}")
