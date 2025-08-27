import re

code = '''F3::
MsgBox, Hello World
Send, {Escape}
SoundSet, +1, , Mute'''

print('ORIGINAL:')
print(code)

# Test MsgBox fix
print('\nAfter MsgBox fix:')
fixed = re.sub(r'\bMsgBox,\s*([^,\r\n]+)', r'MsgBox("\1")', code, flags=re.MULTILINE)
print(fixed)

# Full processing
from llama_client import fix_ahk_code
print('\nFULL FIX:')
result = fix_ahk_code('F3 hotkey test', code)
print(result)
