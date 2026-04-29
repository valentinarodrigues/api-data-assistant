#!/usr/bin/env python3
"""
API Data Assistant — answers "is this data available in the API?" questions
using a local LLM via Ollama.

Usage:
    python assistant.py                                      # interactive mode
    python assistant.py --question "Is customer email available?"
    python assistant.py --schema my_schema.json --dict data.csv
    python assistant.py --dict data.xlsx
    python assistant.py --dict data.pdf
"""

import argparse
import csv
import json
import sys
from io import StringIO
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_SCHEMA = "schema.json"
DEFAULT_DICT = "data_dictionary.csv"
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.2"  # change to mistral, phi3, etc. if preferred

SYSTEM_PROMPT = """\
You are an API documentation assistant. Your job is to help users understand \
what data is available in an API response.

You have been given two sources of truth:
1. A JSON Schema — defines the structure and types of every field in the API response.
2. A Data Dictionary — describes each field in plain English including its meaning, \
data type, example value, whether it's required, and any important notes.

When a user asks whether certain data is available, you must:
- Answer YES or NO clearly at the start.
- Cite the exact field path (e.g. `customer.email` or `items[].unit_price`).
- Quote the description from the data dictionary.
- Mention whether the field is required or optional (may be null/absent).
- If the data is NOT available, suggest the closest alternative if one exists.
- Keep your answer concise and practical.
"""


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def load_schema(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Schema file not found: {path}")
    with open(p) as f:
        data = json.load(f)
    return json.dumps(data, indent=2)


def load_dict_csv(path: Path) -> str:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    lines = ["Data Dictionary:"]
    for row in rows:
        parts = [f"{k}: {v}" for k, v in row.items() if v]
        lines.append("  • " + " | ".join(parts))
    return "\n".join(lines)


def load_dict_excel(path: Path) -> str:
    try:
        import openpyxl
    except ImportError:
        sys.exit("openpyxl is required for Excel files: pip install openpyxl")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return ""
    headers = [str(h) for h in rows[0]]
    lines = ["Data Dictionary:"]
    for row in rows[1:]:
        parts = [f"{h}: {v}" for h, v in zip(headers, row) if v is not None]
        if parts:
            lines.append("  • " + " | ".join(str(p) for p in parts))
    return "\n".join(lines)


def load_dict_pdf(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError:
        sys.exit("pdfplumber is required for PDF files: pip install pdfplumber")
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "Data Dictionary:\n" + "\n".join(pages)


def load_data_dictionary(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Data dictionary not found: {path}")
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return load_dict_csv(p)
    elif suffix in (".xlsx", ".xls", ".xlsm"):
        return load_dict_excel(p)
    elif suffix == ".pdf":
        return load_dict_pdf(p)
    else:
        # Treat as plain text
        return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Ollama integration
# ---------------------------------------------------------------------------

def check_ollama(model: str) -> None:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        r.raise_for_status()
        names = [m["name"] for m in r.json().get("models", [])]
        # Check if any installed model name starts with the requested model
        if not any(n.startswith(model) for n in names):
            print(f"\n[!] Model '{model}' not found in Ollama.")
            print(f"    Run:  ollama pull {model}")
            print(f"    Installed models: {names or 'none'}\n")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("\n[!] Ollama is not running.")
        print("    Install:  https://ollama.com")
        print("    Start:    ollama serve")
        print(f"    Pull:     ollama pull {model}\n")
        sys.exit(1)


def ask_ollama(model: str, context: str, question: str) -> str:
    prompt = f"""{context}

User question: {question}"""

    payload = {
        "model": model,
        "prompt": prompt,
        "system": SYSTEM_PROMPT,
        "stream": True,
    }

    response = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=120)
    response.raise_for_status()

    answer_parts = []
    print("\nAssistant: ", end="", flush=True)
    for line in response.iter_lines():
        if not line:
            continue
        chunk = json.loads(line)
        token = chunk.get("response", "")
        print(token, end="", flush=True)
        answer_parts.append(token)
        if chunk.get("done"):
            break
    print()
    return "".join(answer_parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_context(schema_text: str, dict_text: str) -> str:
    return f"""=== JSON SCHEMA ===
{schema_text}

=== DATA DICTIONARY ===
{dict_text}
"""


def interactive_loop(model: str, context: str) -> None:
    print("\nAPI Data Assistant (type 'quit' or Ctrl+C to exit)")
    print("Ask anything about what data is available in the API.\n")
    while True:
        try:
            question = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break
        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            print("Bye!")
            break
        ask_ollama(model, context, question)
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="API Data Assistant (local AI)")
    parser.add_argument("--schema", default=DEFAULT_SCHEMA, help="Path to JSON schema file")
    parser.add_argument("--dict",   default=DEFAULT_DICT,   help="Path to data dictionary (CSV/XLSX/PDF)")
    parser.add_argument("--model",  default=DEFAULT_MODEL,  help="Ollama model name")
    parser.add_argument("--question", "-q", default=None,   help="Single question (non-interactive)")
    args = parser.parse_args()

    print(f"Loading schema:     {args.schema}")
    schema_text = load_schema(args.schema)

    print(f"Loading dictionary: {args.dict}")
    dict_text = load_data_dictionary(args.dict)

    print(f"Checking Ollama ({args.model})...")
    check_ollama(args.model)
    print("Ready.\n")

    context = build_context(schema_text, dict_text)

    if args.question:
        ask_ollama(args.model, context, args.question)
    else:
        interactive_loop(args.model, context)


if __name__ == "__main__":
    main()
