import httpx
import structlog

log = structlog.get_logger()


class GitHubClient:
    def __init__(self, token: str) -> None:
        self.token = token
        self.base_url = "https://api.github.com"

    async def get_pull_request(
        self, owner: str, repo: str, pr_number: int
    ) -> dict | None:
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                if resp.status_code != 200:
                    log.warning(
                        "github_pr_not_found",
                        owner=owner, repo=repo, pr=pr_number, status=resp.status_code,
                    )
                    return None
                data = resp.json()
                return {
                    "number": data.get("number"),
                    "title": data.get("title"),
                    "state": data.get("state"),
                    "author": (data.get("user") or {}).get("login"),
                    "url": data.get("html_url"),
                    "merged": data.get("merged", False),
                    "base_branch": (data.get("base") or {}).get("ref"),
                }
        except Exception as exc:
            log.error(
                "github_request_error",
                owner=owner, repo=repo, pr=pr_number, error=str(exc),
            )
            return None
