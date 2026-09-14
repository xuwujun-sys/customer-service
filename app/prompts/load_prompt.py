from pathlib import Path

def load_prompt(file_name: str) -> str:
    prompt_path = Path(__file__).parent / f"{file_name}.jinjia2"
    return prompt_path.read_text(encoding="utf-8")
