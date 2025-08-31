def sequential_thinking_tool(args):
    """
    Accepts a list of thoughts and optional context, returns the next step or a solution.
    Mimics the #mcp_sequentialthi_sequentialthinking logic: step-by-step, chain-of-thought, revision, and branching.
    """
    thoughts = args.get("thoughts", [])
    context = args.get("context", "")
    # For demo: just append a new step
    next_step = f"Step {len(thoughts)+1}: (auto-generated) Continue reasoning..."
    result = {
        "previous_thoughts": thoughts,
        "context": context,
        "next_step": next_step,
        "done": False if len(thoughts) < 5 else True,
        "solution": None
    }
    if result["done"]:
        result["solution"] = f"Final answer after {len(thoughts)} steps."
    return result
