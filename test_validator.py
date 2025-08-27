from AHK_Validator import validate_ahk_script

# Test the validator
test_code = '^!WheelUp::Send "{Volume_Up}"'
result = validate_ahk_script(test_code)
print(f"Validation result: {result}")
