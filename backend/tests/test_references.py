from app.integrations.jira.references import extract_jira_references
from app.integrations.github.references import extract_github_references


class TestJiraReferences:
    def test_single_ticket(self):
        refs = extract_jira_references("Fixed in PROJ-123")
        assert refs == ["PROJ-123"]

    def test_multiple_tickets(self):
        refs = extract_jira_references("See PROJ-123 and DATA-456 for context")
        assert refs == ["PROJ-123", "DATA-456"]

    def test_no_tickets(self):
        refs = extract_jira_references("No tickets here")
        assert refs == []

    def test_deduplication(self):
        refs = extract_jira_references("PROJ-123 is related to PROJ-123")
        assert refs == ["PROJ-123"]

    def test_various_formats(self):
        refs = extract_jira_references("ABC-1 XY-99999 Z1-42")
        assert "ABC-1" in refs
        assert "XY-99999" in refs
        assert "Z1-42" in refs

    def test_lowercase_not_matched(self):
        refs = extract_jira_references("proj-123 is not valid")
        assert refs == []


class TestGitHubReferences:
    def test_full_pr_url(self):
        refs = extract_github_references(
            "See https://github.com/acme/repo/pull/42 for details"
        )
        assert len(refs) == 1
        assert refs[0]["owner"] == "acme"
        assert refs[0]["repo"] == "repo"
        assert refs[0]["number"] == 42
        assert refs[0]["url"] == "https://github.com/acme/repo/pull/42"

    def test_short_reference(self):
        refs = extract_github_references("Fixed in #123")
        assert len(refs) == 1
        assert refs[0]["number"] == 123
        assert refs[0]["owner"] is None
        assert refs[0]["repo"] is None
        assert refs[0]["url"] is None

    def test_multiple_references(self):
        text = "See #10 and https://github.com/org/lib/pull/99"
        refs = extract_github_references(text)
        assert len(refs) == 2
        numbers = {r["number"] for r in refs}
        assert numbers == {10, 99}

    def test_no_references(self):
        refs = extract_github_references("No PR references here")
        assert refs == []

    def test_deduplication_full_url(self):
        text = "https://github.com/a/b/pull/1 and https://github.com/a/b/pull/1"
        refs = extract_github_references(text)
        assert len(refs) == 1
