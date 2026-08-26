"""GitHub tool, mock-backed.

Same pattern as everywhere else in this repo: the tool's *interface* is
real — the operations, arguments and result shapes are what a GitHub-backed
implementation would have — while the backing store is an in-memory dict so
everything runs offline. Swapping in the real thing means reimplementing
three handlers against the GitHub REST API; no agent-visible change.
"""

from __future__ import annotations

import itertools
import json

from . import Tool


class MockGitHub:
    def __init__(self, repo: str = "local/demo") -> None:
        self.repo = repo
        self._ids = itertools.count(1)
        self.issues: list[dict] = [
            {"number": next(self._ids), "kind": "issue", "state": "open",
             "title": "stats.py: median crashes on empty input",
             "body": "median([]) raises IndexError; should raise ValueError with a clear message."},
        ]

    def list_issues(self, state: str = "open") -> str:
        rows = [i for i in self.issues if state in ("all", i["state"])]
        return json.dumps(rows, indent=2)

    def create_pr(self, title: str, body: str, branch: str) -> str:
        pr = {"number": next(self._ids), "kind": "pr", "state": "open",
              "title": title, "body": body, "branch": branch}
        self.issues.append(pr)
        return f"Opened PR #{pr['number']} ({branch}) in {self.repo}: {title}"

    def comment(self, number: int, body: str) -> str:
        for item in self.issues:
            if item["number"] == number:
                item.setdefault("comments", []).append(body)
                return f"Commented on #{number}"
        return f"ERROR: #{number} not found"


def make_github_tools(gh: MockGitHub) -> list[Tool]:
    return [
        Tool("github_list_issues", "List issues/PRs in the project repo (mock-backed locally).",
             {"type": "object", "properties": {"state": {"type": "string", "enum": ["open", "closed", "all"]}},
              "required": []},
             gh.list_issues, capability="read"),
        Tool("github_create_pr", "Open a pull request describing the change you made.",
             {"type": "object", "properties": {
                 "title": {"type": "string"}, "body": {"type": "string"}, "branch": {"type": "string"}},
              "required": ["title", "body", "branch"]},
             gh.create_pr, capability="write"),
        Tool("github_comment", "Comment on an issue or PR by number.",
             {"type": "object", "properties": {
                 "number": {"type": "integer"}, "body": {"type": "string"}},
              "required": ["number", "body"]},
             gh.comment, capability="write"),
    ]
