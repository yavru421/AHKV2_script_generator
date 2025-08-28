import subprocess
import os
import json

def run_cli_tool(args, schema):
    """
    Universal CLI tool executor. Builds a command from args and schema, runs it, and returns output.
    """
    # Extract the CLI program name from schema
    tool_name = schema.get("name")
    if not tool_name:
        return {"error": "Schema missing tool name."}
    cli_prog = tool_name.replace("_tool", "")  # convention: ffmpeg_tool -> ffmpeg
    cmd = [cli_prog]
    # Map JSON args to CLI flags/args
    for key, value in args.items():
        if isinstance(value, bool):
            if value:
                cmd.append(f"--{key.replace('_', '-')}")
        elif isinstance(value, list):
            for v in value:
                cmd.append(f"--{key.replace('_', '-')}")
                cmd.append(str(v))
        else:
            cmd.append(f"--{key.replace('_', '-')}")
            cmd.append(str(value))
    # Run the command
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "cmd": " ".join(cmd)
        }
    except Exception as e:
        return {"error": str(e), "cmd": " ".join(cmd)}
