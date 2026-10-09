"""Relocate nested evidence references when promoting a saved analysis."""
import json


def relocate_evidence(directory, destination, source=None):
    """Promotion must preserve every image/JSON evidence link, including nested OCR."""
    prefix = str((source or directory).resolve()) + "/"
    replacement = str(destination.resolve()) + "/"
    def relocate(value):
        if isinstance(value, str):
            return replacement + value[len(prefix):] if value.startswith(prefix) else value
        if isinstance(value, list):
            return [relocate(item) for item in value]
        if isinstance(value, dict):
            return {key: relocate(item) for key, item in value.items()}
        return value
    for path in directory.rglob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(relocate(value), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
