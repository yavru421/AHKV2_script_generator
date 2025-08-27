
# AHK Code Generator & Validator

This project is a Python-based AutoHotkey (AHK) code generator, designed to automatically create, improve, and fix AHK scripts. It can generate new scripts from templates or user prompts, validate existing scripts, and auto-fix common issues. The toolkit is ideal for automating repetitive tasks, creating hotkeys, and rapidly prototyping AHK automation.

## Features
- Generate new AHK scripts from templates or user input
- Validate AHK scripts for syntax and logic errors
- Auto-fix common issues in AHK scripts
- Improve or refactor existing scripts
- Batch process multiple scripts
- Example scripts and templates included

## Getting Started

### Prerequisites
- Python 3.10 or higher
- See `requirements.txt` for dependencies

### Installation
```sh
pip install -r requirements.txt
```

### Usage

To generate a new AHK script, validate, or auto-fix an existing script, use one of the main Python scripts:

```sh
python AHK-Python-FullApp.py
```

This is the main entry point for code generation and advanced features.

For validation and auto-fix only:

```sh
python AHK_Validator.py <input_script.ahk>
```

Or for a simpler validation:

```sh
python AHK_Validator_Simple.py <input_script.ahk>
```

Test scripts and sample AHK files are provided for experimentation. See the `test_*.py` and `test_*.ahk` files.

## Folder Structure
- Main scripts: root directory (`.py` and `.ahk` files)
- `Templates/`: AHK script templates
- `Working_Gen_AHK/`: Generated AHK scripts (output)
- `archive/`: Backups and old versions

## License
See the LICENSE file for details.

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss your ideas.

## Authors
- John (Project Owner)

---
For questions or support, open an issue or contact the author.
