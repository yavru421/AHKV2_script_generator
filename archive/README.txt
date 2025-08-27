# AHK v2 Script Validator & Batch Runner

## Setup

1. Create and activate the virtual environment (if not already):
   python -m venv .venv
   .venv\Scripts\activate

2. Install requirements:
   pip install -r requirements.txt

## Running Tests

Use the correct Python interpreter:

   .venv\Scripts\python.exe -m pytest test_ahk_validator.py

## Running the Batch Runner GUI

   .venv\Scripts\python.exe AHK-Python-BatchRunner.py

## Running the Validator Directly

   .venv\Scripts\python.exe AHK_Validator.py yourscript.ahk

---
All code and tests are now compatible with this environment and setup.
