# llama_chat/chat_app.py

"""
ChatSession: A simple chat interface with history and AHK code generation as a tool.
"""
import sys
import os
from typing import List, Tuple

# Ensure parent directory is in sys.path for imports
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from llama_client import generate_ahk_code

class ChatSession:
    def __init__(self):
        self.history: List[Tuple[str, str]] = []  # (role, message)

    def add_user_message(self, message: str):
        self.history.append(("user", message))

    def add_assistant_message(self, message: str):
        self.history.append(("assistant", message))

    def display_history(self):
        for role, msg in self.history:
            if role == "user":
                print(f"You: {msg}")
            else:
                print(f"Assistant: {msg}")
        print("\n---\n")

    def handle_input(self, user_input: str):
        if user_input.startswith("/ahk"):
            prompt = user_input[4:].strip()
            if not prompt:
                self.add_assistant_message("Please provide a prompt after /ahk.")
                return
            self.add_assistant_message("Generating AHK v2 code...")
            code = generate_ahk_code(prompt)
            self.add_assistant_message(f"Generated AHK v2 code:\n{code}")
        else:
            # Placeholder for general chat logic
            self.add_assistant_message("I'm a chat assistant. Use /ahk <prompt> to generate AHK code.")


def main():
    print("Welcome to Llama Chat! Type your message. Use /ahk <prompt> to generate AHK v2 code. Type 'exit' to quit.")
    session = ChatSession()
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("exit", "quit"):
            print("Goodbye!")
            break
        if not user_input:
            continue
        session.add_user_message(user_input)
        session.handle_input(user_input)
        session.display_history()

if __name__ == "__main__":
    main()
