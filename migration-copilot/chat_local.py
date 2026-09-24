"""Chat with the Migration Copilot on your laptop using Anthropic (Claude) or OpenAI (GPT).
No Orchestrate server needed. Uses the same tools and instructions as the real agent.

Run:  python chat_local.py --llm anthropic     (needs ANTHROPIC_API_KEY)
      python chat_local.py --llm openai        (needs OPENAI_API_KEY)
Type "exit" to quit.
"""
import argparse, json, logging, os, sys
import yaml

sys.path.insert(0, "tools")
logging.disable(logging.ERROR)  # hide "no connection found" noise; demo mode is expected
import vcenter_tools as vc      # noqa: E402
import openshift_tools as ocp   # noqa: E402

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5", "openai": "gpt-4.1"}
AGENT = yaml.safe_load(open("agents/migration_copilot.yaml"))
TOOLS = {t.__tool_spec__.name: t for t in (
    vc.discover_vms, vc.readiness_summary, ocp.create_migration_plan,
    ocp.start_migration, ocp.migration_status, ocp.list_openshift_vms)}


def load_dotenv(path=".env"):
    """Read KEY=value lines from .env without overwriting variables already set."""
    if os.path.exists(path):
        for line in open(path):
            key, sep, value = line.strip().partition("=")
            if sep and not key.startswith("#"):
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))


def _clean(schema):
    """Drop Orchestrate-only keys so the schema is plain JSON Schema."""
    if isinstance(schema, dict):
        return {k: _clean(v) for k, v in schema.items() if k not in ("wrap_data", "title")}
    if isinstance(schema, list):
        return [_clean(v) for v in schema]
    return schema


def tool_specs():
    for name, t in TOOLS.items():
        spec = t.__tool_spec__
        yield name, spec.description, _clean(spec.input_schema.model_dump(exclude_none=True, mode="json"))


def run_tool(name, args):
    print(f"  [tool] {name}({json.dumps(args)})")
    try:
        return json.dumps(TOOLS[name].fn(**args), default=str)
    except Exception as exc:  # let the model see the error and recover
        return json.dumps({"error": str(exc)})


def anthropic_chat(model):
    import anthropic
    client = anthropic.Anthropic()
    tools = [{"name": n, "description": d, "input_schema": s} for n, d, s in tool_specs()]
    messages = []

    def turn(user_text):
        messages.append({"role": "user", "content": user_text})
        while True:
            resp = client.messages.create(model=model, max_tokens=4096, system=AGENT["instructions"],
                                          tools=tools, messages=messages)
            messages.append({"role": "assistant", "content": resp.content})
            calls = [b for b in resp.content if b.type == "tool_use"]
            if not calls:
                return "".join(b.text for b in resp.content if b.type == "text")
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": c.id, "content": run_tool(c.name, c.input)}
                for c in calls]})
    return turn


def openai_chat(model):
    import openai
    client = openai.OpenAI()
    tools = [{"type": "function", "function": {"name": n, "description": d, "parameters": s}}
             for n, d, s in tool_specs()]
    messages = [{"role": "system", "content": AGENT["instructions"]}]

    def turn(user_text):
        messages.append({"role": "user", "content": user_text})
        while True:
            msg = client.chat.completions.create(model=model, messages=messages, tools=tools).choices[0].message
            messages.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                return msg.content or ""
            for c in msg.tool_calls:
                messages.append({"role": "tool", "tool_call_id": c.id,
                                 "content": run_tool(c.function.name, json.loads(c.function.arguments or "{}"))})
    return turn


def main():
    load_dotenv()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--llm", choices=["anthropic", "openai"], default=os.getenv("LLM_PROVIDER", "anthropic"))
    p.add_argument("--model", help="Model name. Defaults: " + ", ".join(f"{k}={v}" for k, v in DEFAULT_MODELS.items()))
    a = p.parse_args()

    key_var = f"{a.llm.upper()}_API_KEY"
    if not os.getenv(key_var):
        sys.exit(f"{key_var} is not set. Add it to .env or run: export {key_var}=...")
    model = a.model or os.getenv(f"{a.llm.upper()}_MODEL") or DEFAULT_MODELS[a.llm]
    turn = (anthropic_chat if a.llm == "anthropic" else openai_chat)(model)

    print(f"{AGENT['display_name']} — {a.llm} / {model}. Type 'exit' to quit.")
    print('Try: "How ready is the finance cluster to move?"\n')
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in ("exit", "quit"):
            break
        if text:
            print(f"\ncopilot> {turn(text)}\n")


if __name__ == "__main__":
    main()
