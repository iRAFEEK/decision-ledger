import httpx
import structlog

log = structlog.get_logger()


class JiraClient:
    def __init__(self, domain: str, email: str, api_token: str) -> None:
        self.base_url = f"https://{domain}/rest/api/3"
        self.auth = (email, api_token)

    async def get_issue(self, issue_key: str) -> dict | None:
        url = f"{self.base_url}/issue/{issue_key}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url, auth=self.auth)
                if resp.status_code != 200:
                    log.warning("jira_issue_not_found", key=issue_key, status=resp.status_code)
                    return None
                data = resp.json()
                fields = data.get("fields", {})
                assignee = fields.get("assignee") or {}
                return {
                    "key": data.get("key"),
                    "title": fields.get("summary"),
                    "status": (fields.get("status") or {}).get("name"),
                    "assignee": assignee.get("displayName"),
                    "project": (fields.get("project") or {}).get("key"),
                    "type": (fields.get("issuetype") or {}).get("name"),
                    "url": f"https://{self.base_url.split('/rest')[0].split('//')[1]}/browse/{issue_key}",
                }
        except Exception as exc:
            log.error("jira_request_error", key=issue_key, error=str(exc))
            return None
