import pytest
import os
from AHK_Validator import validate_ahk_script

def test_valid_hotstring(tmp_path):
    script = '::btw::by the way\n'
    file = tmp_path / "test.ahk"
    file.write_text(script)
    assert validate_ahk_script(script) == True

def test_valid_hotkey(tmp_path):
    script = 'F1::Send("Hello")\n'
    file = tmp_path / "test.ahk"
    file.write_text(script)
    assert validate_ahk_script(script) == True

def test_invalid_syntax(tmp_path):
    script = 'F1::Send("Hello"\n'  # Missing closing parenthesis
    file = tmp_path / "test.ahk"
    file.write_text(script)
    assert validate_ahk_script(script) == False

def test_run_command(tmp_path):
    script = 'F2::Run "notepad.exe"\n'
    file = tmp_path / "test.ahk"
    file.write_text(script)
    assert validate_ahk_script(script) == True
