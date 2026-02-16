import re

_SHORT_PR_PATTERN = re.compile(r"(?<!\w)#(\d+)\b")
_FULL_PR_PATTERN = re.compile(
    r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)"
)


def extract_github_references(text: str) -> list[dict]:
    refs: list[dict] = []
    seen: set[str] = set()

    for match in _FULL_PR_PATTERN.finditer(text):
        owner, repo, number = match.group(1), match.group(2), match.group(3)
        key = f"{owner}/{repo}#{number}"
        if key not in seen:
            seen.add(key)
            refs.append({
                "owner": owner,
                "repo": repo,
                "number": int(number),
                "url": match.group(0),
            })

    for match in _SHORT_PR_PATTERN.finditer(text):
        number = match.group(1)
        key = f"#{ number}"
        if key not in seen:
            seen.add(key)
            refs.append({
                "owner": None,
                "repo": None,
                "number": int(number),
                "url": None,
            })

    return refs
