import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox, simpledialog
import subprocess
import os
import threading
import queue
import io
import sys
try:
    import psutil  # type: ignore
except ImportError:  # graceful fallback; buttons that need psutil will error otherwise
    psutil = None  # noqa: N816
from AHK_Validator import validate_ahk_script
from llama_client import generate_ahk_code, fix_ahk_code

AHK_EXE = "AutoHotkey.exe"


class FullAHKApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AHK v2 Script Runner, Validator & Batch Manager")
        self.geometry("1000x700")
        self.resizable(False, False)
        self.folder_path = tk.StringVar()
        self.file_path = tk.StringVar()
        self.script_info = {}  # {script_path: {checked, status, proc}}
        self.ahk_proc = None
        self.status_var = tk.StringVar(value="Idle")
        self.last_prompt = ""  # Store the last prompt for fixing
        self.validation_cache = {}  # Cache validation results {file_path: (mtime, is_valid)}
        self.api_status = tk.StringVar(value="Not tested")  # API connection status

        # --- Tabs ---
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # --- Status Bar ---
        status_frame = tk.Frame(self)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(status_frame, text="API Status:").pack(side=tk.LEFT, padx=5)
        tk.Label(status_frame, textvariable=self.api_status, fg="blue").pack(side=tk.LEFT, padx=5)
        tk.Button(status_frame, text="Test API", command=self.test_api_connection).pack(side=tk.LEFT, padx=5)
        tk.Button(status_frame, text="Clear Cache", command=self.clear_validation_cache).pack(side=tk.LEFT, padx=5)

        # --- Batch Tab ---
        batch_tab = tk.Frame(self.notebook)
        self.notebook.add(batch_tab, text="Batch Runner")

        top_frame = tk.Frame(batch_tab)
        top_frame.pack(fill=tk.X, pady=5)
        tk.Label(top_frame, text="Scripts Folder:").pack(side=tk.LEFT, padx=5)
        tk.Entry(top_frame, textvariable=self.folder_path, width=40).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Browse Folder", command=self.browse_folder).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Refresh", command=self.refresh_scripts).pack(side=tk.LEFT, padx=5)

        self.tree = ttk.Treeview(batch_tab, columns=("Status",), show="headings")
        self.tree.heading("Status", text="Status/Result")
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.tree.bind('<Button-1>', self.toggle_check)

        btn_frame = tk.Frame(batch_tab)
        btn_frame.pack(pady=5)
        tk.Button(btn_frame, text="Run Selected", command=self.run_selected).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Validate Selected", command=self.validate_selected).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Quick Validate All", command=self.quick_validate_all).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Kill Selected", command=self.kill_selected).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="List Running AHK", command=self.list_ahk_processes).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Kill All AHK", command=self.kill_all_ahk).pack(side=tk.LEFT, padx=5)
        tk.Label(btn_frame, textvariable=self.status_var, fg="blue").pack(side=tk.LEFT, padx=10)

        self.output_box = scrolledtext.ScrolledText(batch_tab, width=120, height=12, state='normal')
        self.output_box.pack(padx=10, pady=5)

        # --- Code Generator Tab ---
        gen_tab = tk.Frame(self.notebook)
        self.notebook.add(gen_tab, text="Code Generator")

        prompt_frame = tk.Frame(gen_tab)
        prompt_frame.pack(fill=tk.X, pady=5)
        tk.Label(prompt_frame, text="Describe your AHK v2 script:").pack(side=tk.LEFT, padx=5)
        self.prompt_entry = tk.Entry(prompt_frame, width=80)
        self.prompt_entry.pack(side=tk.LEFT, padx=5)
        tk.Button(prompt_frame, text="Generate", command=self.generate_code).pack(side=tk.LEFT, padx=5)

        self.generated_code = scrolledtext.ScrolledText(gen_tab, width=120, height=18, state='normal')
        self.generated_code.pack(padx=10, pady=5)

        gen_btn_frame = tk.Frame(gen_tab)
        gen_btn_frame.pack(pady=5)
        tk.Button(gen_btn_frame, text="Validate", command=self.validate_generated).pack(side=tk.LEFT, padx=5)
        self.fix_button = tk.Button(gen_btn_frame, text="Fix Script", command=self.fix_generated, state='disabled')
        self.fix_button.pack(side=tk.LEFT, padx=5)
        tk.Button(gen_btn_frame, text="Save As .ahk", command=self.save_generated).pack(side=tk.LEFT, padx=5)
        tk.Button(gen_btn_frame, text="Run", command=self.run_generated).pack(side=tk.LEFT, padx=5)
        tk.Button(gen_btn_frame, text="Add to Batch", command=self.add_to_batch).pack(side=tk.LEFT, padx=5)
        self.gen_status = tk.StringVar(value="Idle")
        tk.Label(gen_btn_frame, textvariable=self.gen_status, fg="blue").pack(side=tk.LEFT, padx=10)

        # --- Script Suggestions Tab ---
        suggest_tab = tk.Frame(self.notebook)
        self.notebook.add(suggest_tab, text="Script Suggestions")

        suggest_categories = tk.Frame(suggest_tab)
        suggest_categories.pack(fill=tk.X, pady=5)

        tk.Label(suggest_categories, text="Category:").pack(side=tk.LEFT, padx=5)
        self.category_var = tk.StringVar(value="Productivity")
        categories = ["Productivity", "Gaming", "Media Control", "Window Management", "Text Expansion", "System Utils"]
        category_combo = ttk.Combobox(suggest_categories, textvariable=self.category_var, values=categories, width=20)
        category_combo.pack(side=tk.LEFT, padx=5)
        tk.Button(suggest_categories, text="Get Suggestions", command=self.get_suggestions).pack(side=tk.LEFT, padx=5)

        # Suggestions list
        suggest_list_frame = tk.Frame(suggest_tab)
        suggest_list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.suggestions_tree = ttk.Treeview(suggest_list_frame, columns=("Description",), show="tree headings", height=8)
        self.suggestions_tree.heading("#0", text="Script Name")
        self.suggestions_tree.heading("Description", text="Description")
        self.suggestions_tree.column("#0", width=200)
        self.suggestions_tree.column("Description", width=400)
        self.suggestions_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        suggest_scroll = ttk.Scrollbar(suggest_list_frame, orient=tk.VERTICAL, command=self.suggestions_tree.yview)
        suggest_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.suggestions_tree.configure(yscrollcommand=suggest_scroll.set)

        self.suggestions_tree.bind('<Double-1>', self.generate_suggested_script)

        suggest_btn_frame = tk.Frame(suggest_tab)
        suggest_btn_frame.pack(pady=5)
        tk.Button(suggest_btn_frame, text="Generate Selected", command=self.generate_suggested_script).pack(side=tk.LEFT, padx=5)
        tk.Button(suggest_btn_frame, text="Customize Prompt", command=self.customize_suggestion).pack(side=tk.LEFT, padx=5)

        # --- Advanced Single Script Tab ---
        single_tab = tk.Frame(self.notebook)
        self.notebook.add(single_tab, text="Script Editor")

        # File operations
        file_frame = tk.Frame(single_tab)
        file_frame.pack(fill=tk.X, pady=5)
        tk.Label(file_frame, text="Script File:").pack(side=tk.LEFT, padx=5)
        tk.Entry(file_frame, textvariable=self.file_path, width=50).pack(side=tk.LEFT, padx=5)
        tk.Button(file_frame, text="Browse", command=self.load_script_file).pack(side=tk.LEFT, padx=5)
        tk.Button(file_frame, text="New", command=self.new_script).pack(side=tk.LEFT, padx=5)
        tk.Button(file_frame, text="Save", command=self.save_script).pack(side=tk.LEFT, padx=5)

        # Script editor
        self.script_editor = scrolledtext.ScrolledText(single_tab, width=120, height=15, state='normal')
        self.script_editor.pack(padx=10, pady=5)

        # Control buttons
        control_frame = tk.Frame(single_tab)
        control_frame.pack(pady=5)
        tk.Button(control_frame, text="Validate", command=self.validate_editor_script).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="Run Script", command=self.run_editor_script).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="Kill Script", command=self.kill_script).pack(side=tk.LEFT, padx=5)
        tk.Button(control_frame, text="Format Code", command=self.format_script).pack(side=tk.LEFT, padx=5)

        self.editor_status = tk.StringVar(value="Ready")
        tk.Label(control_frame, textvariable=self.editor_status, fg="blue").pack(side=tk.LEFT, padx=10)

        # Output area
        self.single_output = scrolledtext.ScrolledText(single_tab, width=120, height=8, state='normal')
        self.single_output.pack(padx=10, pady=5)

        self.refresh_scripts()
    def generate_code(self):
        """Spawn a background thread so the UI stays responsive."""
        prompt = self.prompt_entry.get().strip()
        if not prompt:
            messagebox.showerror("Error", "Please enter a prompt.")
            return
        
        # LOCKDOWN: Mandatory user confirmation before code generation
        proceed = messagebox.askyesno(
            "AHK v2 Lockdown Confirmation", 
            f"You are about to generate AutoHotkey v2 code for:\n\n\"{prompt}\"\n\n"
            "This system is locked down to prevent v1/v2 syntax mixing.\n"
            "Only valid AutoHotkey v2 syntax will be generated.\n\n"
            "Do you want to proceed with code generation?",
            icon='question'
        )
        
        if not proceed:
            self.gen_status.set("Generation cancelled by user")
            return
            
        self.last_prompt = prompt  # Store for potential fixing
        self.gen_status.set("Generating...")
        self.generated_code.delete('1.0', tk.END)
        self.fix_button.config(state='disabled')  # Hide fix button during generation
        q: queue.Queue[str] = queue.Queue()

        def worker():
            try:
                result = generate_ahk_code(prompt)
            except Exception as e:  # catch all to avoid silent thread death
                result = f"; ERROR generating code: {e}"
            q.put(result)

        threading.Thread(target=worker, daemon=True).start()
        self.after(150, lambda: self._poll_generation(q))

    def _poll_generation(self, q: 'queue.Queue[str]'):
        try:
            code = q.get_nowait()
        except queue.Empty:
            self.after(150, lambda: self._poll_generation(q))
            return
        self.generated_code.insert(tk.END, code)
        # Auto-scroll to top
        self.generated_code.see('1.0')
        # Auto-validate if short
        if len(code) < 5000:
            valid = validate_ahk_script(code)
            if valid:
                self.gen_status.set("Done (Valid)")
                self.fix_button.config(state='disabled')
            else:
                self.gen_status.set("Done (Invalid)")
                self.fix_button.config(state='normal')  # Enable fix button
        else:
            self.gen_status.set("Done.")
            self.fix_button.config(state='disabled')

    def validate_generated(self):
        code = self.generated_code.get('1.0', tk.END)
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        valid = validate_ahk_script(code)
        sys.stdout = old_stdout
        validation_output = buf.getvalue()
        self.gen_status.set("Valid" if valid else "Invalid")
        self.output_box.insert(tk.END, f"Validation output (generated):\n{validation_output}\n")
        if not valid:
            self.gen_status.set("Invalid - Suggesting Fix...")
            fix = fix_ahk_code(self.last_prompt, code)
            self.output_box.insert(tk.END, f"\nLlama API fix suggestion:\n{fix}\n")
            self.fix_button.config(state='normal')
        else:
            self.fix_button.config(state='disabled')

    def fix_generated(self):
        """Fix the currently generated invalid script."""
        current_code = self.generated_code.get('1.0', tk.END).strip()
        if not current_code:
            messagebox.showerror("Error", "No code to fix.")
            return

        self.gen_status.set("Fixing...")
        self.fix_button.config(state='disabled')
        q: queue.Queue[str] = queue.Queue()

        def worker():
            try:
                result = fix_ahk_code(self.last_prompt, current_code)
            except Exception as e:
                result = f"; ERROR fixing code: {e}"
            q.put(result)

        threading.Thread(target=worker, daemon=True).start()
        self.after(150, lambda: self._poll_fix(q))

    def _poll_fix(self, q: 'queue.Queue[str]'):
        try:
            fixed_code = q.get_nowait()
        except queue.Empty:
            self.after(150, lambda: self._poll_fix(q))
            return

        # Replace the content with the fixed code
        self.generated_code.delete('1.0', tk.END)
        self.generated_code.insert(tk.END, fixed_code)
        self.generated_code.see('1.0')

        # Auto-validate the fix
        if len(fixed_code) < 5000:
            valid = validate_ahk_script(fixed_code)
            if valid:
                self.gen_status.set("Fixed (Valid)")
                self.fix_button.config(state='disabled')
            else:
                self.gen_status.set("Fixed (Still Invalid)")
                self.fix_button.config(state='normal')  # Allow another fix attempt
        else:
            self.gen_status.set("Fixed.")
            self.fix_button.config(state='disabled')

    # --- Script Suggestions Methods ---
    def get_suggestions(self):
        """Generate script suggestions based on selected category."""
        category = self.category_var.get()
        suggestions = self._get_category_suggestions(category)

        # Clear current suggestions
        for item in self.suggestions_tree.get_children():
            self.suggestions_tree.delete(item)

        # Add new suggestions
        for name, description in suggestions:
            self.suggestions_tree.insert('', 'end', text=name, values=(description,))

    def _get_category_suggestions(self, category):
        """Return script suggestions for a given category."""
        suggestions = {
            "Productivity": [
                ("Clipboard Manager", "Store and cycle through clipboard history"),
                ("Window Snapping", "Snap windows to screen edges and corners"),
                ("Auto-Typer", "Type frequently used text with hotkeys"),
                ("File Organizer", "Sort files by type into folders"),
                ("Always On Top Toggle", "Make any window stay on top"),
            ],
            "Gaming": [
                ("Mouse Clicker", "Auto-click at specified intervals"),
                ("WASD to Arrow Keys", "Remap WASD to arrow keys for old games"),
                ("Game Volume Control", "Quick volume adjustment while gaming"),
                ("Screenshot Tool", "Capture and save game screenshots"),
                ("Crosshair Overlay", "Display crosshair on screen"),
            ],
            "Media Control": [
                ("Global Media Keys", "Control media from any app"),
                ("Volume Wheel Control", "Use mouse wheel for volume"),
                ("Spotify Controller", "Control Spotify with hotkeys"),
                ("Audio Device Switcher", "Quick switch between audio devices"),
                ("Mute Toggle", "One-key mute/unmute"),
            ],
            "Window Management": [
                ("Virtual Desktops", "Navigate between virtual desktops"),
                ("Window Transparency", "Make windows semi-transparent"),
                ("Minimize All", "Minimize all windows at once"),
                ("Window Mover", "Move windows with keyboard"),
                ("Screen Ruler", "Measure pixels on screen"),
            ],
            "Text Expansion": [
                ("Email Signatures", "Insert email signatures quickly"),
                ("Date/Time Stamps", "Insert current date/time"),
                ("Address Expander", "Expand abbreviations to full address"),
                ("Code Snippets", "Insert common code patterns"),
                ("Auto-Correct", "Fix common typing mistakes"),
            ],
            "System Utils": [
                ("System Monitor", "Display CPU/RAM usage"),
                ("Battery Alert", "Alert when battery is low"),
                ("Caps Lock Remapper", "Remap Caps Lock to useful function"),
                ("Empty Recycle Bin", "Quick empty recycle bin hotkey"),
                ("Lock Screen", "Instantly lock the computer"),
            ]
        }
        return suggestions.get(category, [])

    def generate_suggested_script(self, event=None):
        """Generate code for the selected suggestion."""
        selection = self.suggestions_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a script suggestion first.")
            return

        item = selection[0]
        script_name = self.suggestions_tree.item(item, 'text')
        description = self.suggestions_tree.item(item, 'values')[0]

        # Create detailed prompt
        prompt = f"Create an AutoHotkey v2 script for {script_name}: {description}"

        # Switch to generator tab and generate
        self.notebook.select(1)  # Switch to Code Generator tab
        self.prompt_entry.delete(0, tk.END)
        self.prompt_entry.insert(0, prompt)
        self.generate_code()

    def customize_suggestion(self):
        """Allow user to customize the selected suggestion prompt."""
        selection = self.suggestions_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a script suggestion first.")
            return

        item = selection[0]
        script_name = self.suggestions_tree.item(item, 'text')
        description = self.suggestions_tree.item(item, 'values')[0]

        # Show input dialog for customization
        custom_prompt = simpledialog.askstring(
            "Customize Script",
            f"Customize the prompt for '{script_name}':",
            initialvalue=f"Create an AutoHotkey v2 script for {script_name}: {description}"
        )

        if custom_prompt:
            self.notebook.select(1)  # Switch to Code Generator tab
            self.prompt_entry.delete(0, tk.END)
            self.prompt_entry.insert(0, custom_prompt)

    # --- Advanced Single Script Methods ---
    def new_script(self):
        """Create a new script."""
        self.file_path.set("")
        self.script_editor.delete('1.0', tk.END)
        self.script_editor.insert('1.0', "#Requires AutoHotkey v2.0\n#SingleInstance Force\n\n; Your script here\n")
        self.editor_status.set("New Script")

    def save_script(self):
        """Save the current script."""
        content = self.script_editor.get('1.0', tk.END)
        file_path = self.file_path.get()

        if not file_path:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".ahk",
                filetypes=[("AHK Scripts", "*.ahk"), ("All Files", "*.*")]
            )
            if not file_path:
                return
            self.file_path.set(file_path)

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.editor_status.set(f"Saved: {os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save file: {e}")

    def validate_editor_script(self):
        content = self.script_editor.get('1.0', tk.END)
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        valid = validate_ahk_script(content)
        sys.stdout = old_stdout
        validation_output = buf.getvalue()
        self.editor_status.set("Valid" if valid else "Invalid")
        self.single_output.insert(tk.END, f"Validation output (editor):\n{validation_output}\n")
        if not valid:
            self.editor_status.set("Invalid - Suggesting Fix...")
            fix = fix_ahk_code("Fix this script", content)
            self.single_output.insert(tk.END, f"\nLlama API fix suggestion:\n{fix}\n")

    def run_editor_script(self):
        """Run the script from the editor."""
        content = self.script_editor.get('1.0', tk.END)
        if not validate_ahk_script(content):
            self.editor_status.set("Invalid - not run")
            return

        # Save to temp file and run
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ahk', mode='w', encoding='utf-8') as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            self.ahk_proc = subprocess.Popen([AHK_EXE, tmp_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.editor_status.set("Running...")
            self.after(1000, self.check_proc_single)
        except Exception as e:
            self.editor_status.set(f"Error: {e}")

    def format_script(self):
        """Basic formatting for the script."""
        content = self.script_editor.get('1.0', tk.END)
        # Simple formatting: ensure proper indentation and spacing
        lines = content.split('\n')
        formatted_lines = []
        indent_level = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                formatted_lines.append('')
                continue

            # Decrease indent for closing braces
            if stripped.startswith('}'):
                indent_level = max(0, indent_level - 1)

            # Add indentation
            formatted_line = '    ' * indent_level + stripped
            formatted_lines.append(formatted_line)

            # Increase indent for opening braces
            if stripped.endswith('{') or stripped.endswith('::'):
                indent_level += 1

        self.script_editor.delete('1.0', tk.END)
        self.script_editor.insert('1.0', '\n'.join(formatted_lines))
        self.editor_status.set("Formatted")

    def add_to_batch(self):
        """Add generated script to batch runner."""
        code = self.generated_code.get('1.0', tk.END).strip()
        if not code:
            messagebox.showwarning("No Code", "Generate some code first.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".ahk",
            filetypes=[("AHK Scripts", "*.ahk")],
            title="Save script to add to batch"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(code)
                # Refresh batch list if folder matches
                if os.path.dirname(file_path) == self.folder_path.get():
                    self.refresh_scripts()
                self.gen_status.set(f"Added to batch: {os.path.basename(file_path)}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Could not save file: {e}")

        self.clear_validation_cache()
        self.refresh_scripts()

    def quick_validate_all(self):
        """Quickly validate all scripts using cache when possible."""
        folder = self.folder_path.get() or os.getcwd()
        self.output_box.insert(tk.END, "=== Quick Validation (using cache) ===\n")

        valid_count = 0
        invalid_count = 0
        cached_count = 0

        for fname in os.listdir(folder):
            if fname.lower().endswith('.ahk'):
                fpath = os.path.join(folder, fname)
                if fpath in self.script_info:
                    # Check if we used cache
                    if fpath in self.validation_cache:
                        try:
                            file_mtime = os.path.getmtime(fpath)
                            cached_mtime, _ = self.validation_cache[fpath]
                            if cached_mtime == file_mtime:
                                cached_count += 1
                        except:
                            pass

                    if self.validate_and_report(fpath):
                        valid_count += 1
                    else:
                        invalid_count += 1

        self.output_box.insert(tk.END, f"Results: {valid_count} valid, {invalid_count} invalid, {cached_count} from cache\n")
        self.status_var.set(f"Validated: {valid_count}✅ {invalid_count}❌ {cached_count}💾")

    def load_script_file(self):
        """Load a script file into the editor."""
        file = filedialog.askopenfilename(filetypes=[("AHK Scripts", "*.ahk")])
        if file:
            self.file_path.set(file)
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.script_editor.delete('1.0', tk.END)
                self.script_editor.insert('1.0', content)
                self.editor_status.set(f"Loaded: {os.path.basename(file)}")
            except Exception as e:
                messagebox.showerror("Load Error", f"Could not load file: {e}")

        self.refresh_scripts()

    def save_generated(self):
        code = self.generated_code.get('1.0', tk.END)
        file = filedialog.asksaveasfilename(defaultextension=".ahk", filetypes=[("AHK Scripts", "*.ahk")])
        if file:
            with open(file, 'w', encoding='utf-8') as f:
                f.write(code)
            self.gen_status.set(f"Saved: {os.path.basename(file)}")

    def run_generated(self):
        code = self.generated_code.get('1.0', tk.END)
        if not validate_ahk_script(code):
            self.gen_status.set("Invalid - not run")
            return
        # Save to temp file and run
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ahk', mode='w', encoding='utf-8') as tmp:
            tmp.write(code)
            tmp_path = tmp.name
        try:
            proc = subprocess.Popen([AHK_EXE, tmp_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.gen_status.set("Running...")
        except Exception as e:
            self.gen_status.set(f"Error: {e}")

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_path.set(folder)
            self.refresh_scripts()

    def browse_file(self):
        file = filedialog.askopenfilename(filetypes=[("AHK Scripts", "*.ahk")])
        if file:
            self.file_path.set(file)

    def refresh_scripts(self):
        folder = self.folder_path.get() or os.getcwd()
        self.tree.delete(*self.tree.get_children())
        self.script_info.clear()
        for fname in os.listdir(folder):
            if fname.lower().endswith('.ahk'):
                fpath = os.path.join(folder, fname)
                self.script_info[fpath] = {'checked': False, 'status': '', 'proc': None}
                self.tree.insert('', 'end', iid=fpath, values=(fname, 'Idle'))

    def toggle_check(self, event):
        region = self.tree.identify('region', event.x, event.y)
        if region == 'cell':
            row = self.tree.identify_row(event.y)
            if row:
                info = self.script_info[row]
                info['checked'] = not info['checked']
                self.tree.item(row, tags=('checked' if info['checked'] else 'unchecked',))
                self.tree.tag_configure('checked', background='#d0ffd0')
                self.tree.tag_configure('unchecked', background='white')

    def get_checked_scripts(self):
        return [path for path, info in self.script_info.items() if info['checked']]

    def run_selected(self):
        for path in self.get_checked_scripts():
            if not self.validate_and_report(path):
                continue
            try:
                proc = subprocess.Popen([AHK_EXE, path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                self.script_info[path]['proc'] = proc
                self.script_info[path]['status'] = 'Running'
                self.tree.set(path, 'Status', 'Running')
                self.after(1000, lambda p=path: self.check_proc(p))
            except Exception as e:
                self.tree.set(path, 'Status', f'Error: {e}')
                self.output_box.insert(tk.END, f"Error running {path}: {e}\n")

    def check_proc(self, path):
        proc = self.script_info[path]['proc']
        if proc is None:
            return
        ret = proc.poll()
        if ret is not None:
            out, err = proc.communicate()
            self.tree.set(path, 'Status', f'Exit {ret}')
            self.output_box.insert(tk.END, f"{os.path.basename(path)} finished. Exit code: {ret}\nSTDOUT:\n{out}\nSTDERR:\n{err}\n\n")
            self.script_info[path]['proc'] = None
        else:
            self.after(1000, lambda p=path: self.check_proc(p))

    def validate_selected(self):
        for path in self.get_checked_scripts():
            self.validate_and_report(path)

    def validate_and_report(self, path):
        try:
            # Check if the item exists in the tree first
            if not self.tree.exists(path):
                self.output_box.insert(tk.END, f"Warning: {os.path.basename(path)} not found in tree\n")
                return False

            # Check cache first
            file_mtime = None
            try:
                file_mtime = os.path.getmtime(path)
                if path in self.validation_cache:
                    cached_mtime, cached_result = self.validation_cache[path]
                    if cached_mtime == file_mtime:
                        # Use cached result
                        status = 'Valid' if cached_result else 'Invalid'
                        self.tree.set(path, 'Status', status)
                        self.output_box.insert(tk.END, f"{os.path.basename(path)}: {status.upper()} (cached)\n")
                        return cached_result
            except OSError:
                pass  # File doesn't exist or can't get mtime

            with open(path, 'r', encoding='utf-8') as f:
                script = f.read()
            valid = validate_ahk_script(script)

            # Cache the result
            if file_mtime is not None:
                try:
                    self.validation_cache[path] = (file_mtime, valid)
                except:
                    pass  # Ignore cache errors

            if valid:
                self.tree.set(path, 'Status', 'Valid')
                self.output_box.insert(tk.END, f"{os.path.basename(path)}: VALID\n")
                return True
            else:
                self.tree.set(path, 'Status', 'Invalid')
                self.output_box.insert(tk.END, f"{os.path.basename(path)}: INVALID\n")
                return False
        except Exception as e:
            # Only try to update tree if item exists
            if self.tree.exists(path):
                self.tree.set(path, 'Status', f'Error: {e}')
            self.output_box.insert(tk.END, f"Error validating {path}: {e}\n")
            return False

    def test_api_connection(self):
        """Test API connection and update status."""
        self.api_status.set("Testing...")
        self.update()

        def test_worker():
            try:
                from llama_client import generate_ahk_code
                result = generate_ahk_code("test connection")
                if result.startswith('[ERROR]'):
                    self.api_status.set(f"❌ Error: {result[:50]}...")
                else:
                    self.api_status.set("✅ Connected")
            except Exception as e:
                self.api_status.set(f"❌ Error: {str(e)[:50]}...")

        # Run in background to avoid blocking UI
        threading.Thread(target=test_worker, daemon=True).start()

    def clear_validation_cache(self):
        """Clear the validation cache."""
        self.validation_cache.clear()
        self.output_box.insert(tk.END, "Validation cache cleared.\n")
        messagebox.showinfo("Cache Cleared", "Validation cache has been cleared. Files will be re-validated on next check.")

    def kill_selected(self):
        for path in self.get_checked_scripts():
            proc = self.script_info[path].get('proc')
            if proc and proc.poll() is None:
                proc.terminate()
                self.tree.set(path, 'Status', 'Killed')
                self.output_box.insert(tk.END, f"Killed {os.path.basename(path)}\n")

    def list_ahk_processes(self):
        if psutil is None:
            messagebox.showerror("Dependency Missing", "psutil not installed; cannot list processes.")
            return
        ahk_procs = [p for p in psutil.process_iter(['pid', 'name', 'cmdline']) if p.info.get('name') and 'autohotkey' in p.info['name'].lower()]
        self.output_box.insert(tk.END, "\n--- Running AutoHotkey Processes ---\n")
        for p in ahk_procs:
            try:
                cmdline = ' '.join(p.info.get('cmdline') or [])
            except Exception:
                cmdline = ''
            self.output_box.insert(tk.END, f"PID: {p.info['pid']} | CMD: {cmdline}\n")
        if not ahk_procs:
            self.output_box.insert(tk.END, "No running AutoHotkey processes found.\n")

    def kill_all_ahk(self):
        if psutil is None:
            messagebox.showerror("Dependency Missing", "psutil not installed; cannot kill processes.")
            return
        ahk_procs = [p for p in psutil.process_iter(['pid', 'name']) if p.info.get('name') and 'autohotkey' in p.info['name'].lower()]
        for p in ahk_procs:
            try:
                p.terminate()
                self.output_box.insert(tk.END, f"Killed AHK process PID: {p.info['pid']}\n")
            except Exception as e:
                self.output_box.insert(tk.END, f"Failed to kill PID {p.info['pid']}: {e}\n")

    # --- Single script controls ---
    def run_script(self):
        script = self.file_path.get()
        if not script or not os.path.isfile(script):
            messagebox.showerror("Error", "Please select a valid .ahk script file.")
            return
        if not self.validate_and_report(script):
            return
        self.output_box.delete('1.0', tk.END)
        self.status_var.set("Running...")
        try:
            self.ahk_proc = subprocess.Popen([AHK_EXE, script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.after(1000, self.check_proc_single)
        except Exception as e:
            self.output_box.insert(tk.END, f"Error running script: {e}\n")
            self.status_var.set("Error")

    def check_proc_single(self):
        if self.ahk_proc is None:
            return
        ret = self.ahk_proc.poll()
        if ret is not None:
            out, err = self.ahk_proc.communicate()
            self.output_box.insert(tk.END, f"STDOUT:\n{out}\n")
            self.output_box.insert(tk.END, f"STDERR:\n{err}\n")
            self.output_box.insert(tk.END, f"Exit code: {ret}\n")
            self.status_var.set("Idle")
            self.ahk_proc = None
        else:
            self.status_var.set("Running (background)...")
            self.after(1000, self.check_proc_single)

    def validate_script(self):
        script = self.file_path.get()
        if not script or not os.path.isfile(script):
            messagebox.showerror("Error", "Please select a valid .ahk script file.")
            return
        self.validate_and_report(script)

    def kill_script(self):
        if self.ahk_proc and self.ahk_proc.poll() is None:
            self.ahk_proc.terminate()
            self.status_var.set("Killed")
            self.output_box.insert(tk.END, "Script killed.\n")
            self.ahk_proc = None
        else:
            self.status_var.set("Idle (no script running)")
            self.output_box.insert(tk.END, "No running script to kill.\n")

if __name__ == "__main__":
    try:
        import psutil
    except ImportError:
        messagebox.showerror("Missing Dependency", "Please install the 'psutil' package: pip install psutil")
        exit(1)
    app = FullAHKApp()
    app.mainloop()
