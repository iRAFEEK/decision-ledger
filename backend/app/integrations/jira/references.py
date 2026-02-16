import re

_JIRA_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")


def extract_jira_references(text: str) -> list[str]:
    return list(dict.fromkeys(_JIRA_PATTERN.findall(text)))
