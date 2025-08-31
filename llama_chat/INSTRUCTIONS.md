# llama_chat/INSTRUCTIONS.md

## Project Purpose
This folder is for a new Llama Chat Application that will use the AHK v2 generator (from the main project) as a backend tool.

## Instructions for GitHub Copilot (AI Code Writer)


## Chat Application Architecture
The main chat logic is in `chat_app.py`.
The chat supports conversation history and a special `/ahk <prompt>` command to generate AHK v2 code using the backend tool.
The chat can be run with:
	```
	python chat_app.py
	```
The design is modular for future GUI or web upgrades.

## Getting Started
1. Run `python chat_app.py` to start the chat application.
2. Type messages to chat. Use `/ahk <prompt>` to generate AHK code.
3. Type `exit` to quit.
4. Document any additional setup or requirements here.

---

*This file is maintained by GitHub Copilot as the primary code writer for this folder.*
