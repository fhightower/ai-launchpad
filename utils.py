import re


def slugify(text: str) -> str:
    """Convert text to a lowercase slug (e.g. 'Hello World!' -> 'hello-world')."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")