#!/usr/bin/env python3
"""Fetch public GitHub activity and regenerate the profile SVGs."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
CACHE_PATH = ROOT / "cache" / "loc_cache.txt"
USER = os.getenv("PROFILE_USER", "Vaibhaav-Tiwari")
PANEL_X = 616
PANEL_CHARS = 72

THEMES = {
    "dark": {
        "background": "#0d1117",
        "border": "#30363d",
        "portrait": "#626c76",
        "heading": "#7ee787",
        "key": "#d2a8ff",
        "value": "#79c0ff",
        "muted": "#3d444d",
        "plus": "#3fb950",
        "minus": "#f85149",
    },
    "light": {
        "background": "#ffffff",
        "border": "#d0d7de",
        "portrait": "#57606a",
        "heading": "#1a7f37",
        "key": "#8250df",
        "value": "#0969da",
        "muted": "#afb8c1",
        "plus": "#1a7f37",
        "minus": "#cf222e",
    },
}

LANGUAGE_BLOCKLIST = {
    "html", "css", "scss", "sass", "less", "stylus", "jupyter notebook",
    "tex", "markdown", "dockerfile", "makefile", "shell", "powershell",
    "batchfile", "yaml", "json", "xml", "toml", "csv", "tsv",
}

DETAIL_ROWS = [
    ("currently.building", "Orchestrator.inc"),
    ("identity.role", "student @ does it really matter?"),
    ("identity.location", "delhi, india"),
    ("setup.daily", "macbook air | m5 24gb"),
    ("setup.server", "ryzen 5 4600H + rtx 3050"),
    ("tools.ide", "Agent Orchestrator"),
    ("tools.shell", "ghostty + zsh + herdr"),
]

CONTACT_ROWS = [
    ("email", "vaibhaavtiwari@gmail.com"),
    ("linkedin", "linkedin.com/in/vaibhaavtiwari"),
    ("x", "battarchicken"),
]


def graphql(query: str, **variables: object) -> dict:
    """Call GraphQL through gh, which works locally and in GitHub Actions."""
    command = ["gh", "api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        if value is not None:
            command.extend(["-F", f"{key}={value}"])
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "GitHub GraphQL request failed")
    return json.loads(result.stdout)["data"]


def load_cache() -> dict[str, tuple[str, int, int, int]]:
    cache: dict[str, tuple[str, int, int, int]] = {}
    if not CACHE_PATH.exists():
        return cache
    for line in CACHE_PATH.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) == 5:
            name, sha, additions, deletions, commits = parts
            cache[name] = (sha, int(additions), int(deletions), int(commits))
    return cache


def save_cache(cache: dict[str, tuple[str, int, int, int]]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# repo<TAB>head_sha<TAB>additions<TAB>deletions<TAB>commits"]
    lines.extend(
        f"{name}\t{sha}\t{adds}\t{deletes}\t{commits}"
        for name, (sha, adds, deletes, commits) in sorted(cache.items())
    )
    CACHE_PATH.write_text("\n".join(lines) + "\n")


def fetch_repo_history(owner: str, name: str, user_id: str) -> tuple[int, int, int]:
    query = """
    query($owner: String!, $name: String!, $userId: ID!, $cursor: String) {
      repository(owner: $owner, name: $name) {
        defaultBranchRef {
          target {
            ... on Commit {
              history(author: {id: $userId}, first: 100, after: $cursor) {
                pageInfo { hasNextPage endCursor }
                nodes { additions deletions }
              }
            }
          }
        }
      }
    }
    """
    additions = deletions = commits = 0
    cursor = None
    while True:
        data = graphql(
            query, owner=owner, name=name, userId=user_id, cursor=cursor
        )["repository"]
        ref = data and data["defaultBranchRef"]
        if not ref or not ref["target"]:
            return additions, deletions, commits
        history = ref["target"]["history"]
        additions += sum(node["additions"] for node in history["nodes"])
        deletions += sum(node["deletions"] for node in history["nodes"])
        commits += len(history["nodes"])
        if not history["pageInfo"]["hasNextPage"]:
            return additions, deletions, commits
        cursor = history["pageInfo"]["endCursor"]


def fetch_external_merged_pr_loc() -> tuple[int, int, int]:
    """Sum final diffs for merged PRs into repositories the user does not own.

    Owned repositories are already covered by the authored-commit walk above;
    excluding them here prevents counting the same changes twice. PR-level
    additions/deletions still count when a maintainer squashes or rewrites the
    merge commit and the commit author is no longer the original contributor.
    """
    query = """
    query($login: String!, $cursor: String) {
      user(login: $login) {
        pullRequests(
          first: 100,
          after: $cursor,
          states: MERGED,
          orderBy: {field: UPDATED_AT, direction: DESC}
        ) {
          pageInfo { hasNextPage endCursor }
          nodes {
            additions
            deletions
            repository { owner { login } }
          }
        }
      }
    }
    """
    additions = deletions = merged_prs = 0
    cursor = None
    while True:
        data = graphql(query, login=USER, cursor=cursor)["user"]
        if data is None:
            break
        page = data["pullRequests"]
        for pull_request in page["nodes"]:
            merged_prs += 1
            repository = pull_request.get("repository")
            owner = repository and repository.get("owner")
            if owner and owner["login"].casefold() != USER.casefold():
                additions += pull_request["additions"]
                deletions += pull_request["deletions"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return additions, deletions, merged_prs


def fetch_stats() -> dict[str, object]:
    query = """
    query($login: String!, $cursor: String) {
      user(login: $login) {
        id
        followers { totalCount }
        pullRequests(first: 1, states: MERGED) { totalCount }
        repositoriesContributedTo(
          first: 1,
          contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]
        ) { totalCount }
        contributionsCollection {
          totalCommitContributions
          restrictedContributionsCount
        }
        repositories(
          first: 100,
          after: $cursor,
          ownerAffiliations: OWNER,
          isFork: false,
          privacy: PUBLIC,
          orderBy: {field: UPDATED_AT, direction: DESC}
        ) {
          totalCount
          pageInfo { hasNextPage endCursor }
          nodes {
            nameWithOwner
            stargazerCount
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges { size node { name } }
            }
            defaultBranchRef { target { ... on Commit { oid } } }
          }
        }
      }
    }
    """
    repos: list[dict] = []
    cursor = None
    user = None
    while True:
        user = graphql(query, login=USER, cursor=cursor)["user"]
        if user is None:
            raise RuntimeError(f"GitHub user {USER!r} was not found")
        page = user["repositories"]
        repos.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    language_bytes: dict[str, int] = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            language = edge["node"]["name"]
            if language.lower() not in LANGUAGE_BLOCKLIST:
                language_bytes[language] = language_bytes.get(language, 0) + edge["size"]
    language_total = sum(language_bytes.values())
    top_languages = sorted(language_bytes.items(), key=lambda pair: -pair[1])[:3]
    top_language_text = ", ".join(
        f"{name.lower()} {size / language_total:.0%}"
        for name, size in top_languages
    ) if language_total else "no language data yet"

    old_cache = load_cache()
    new_cache: dict[str, tuple[str, int, int, int]] = {}
    for repo in repos:
        ref = repo["defaultBranchRef"]
        if not ref or not ref["target"]:
            continue
        full_name = repo["nameWithOwner"]
        head_sha = ref["target"]["oid"]
        cached = old_cache.get(full_name)
        if cached and cached[0] == head_sha:
            new_cache[full_name] = cached
            continue
        owner, name = full_name.split("/", 1)
        adds, deletes, commits = fetch_repo_history(owner, name, user["id"])
        new_cache[full_name] = (head_sha, adds, deletes, commits)
    save_cache(new_cache)

    additions = sum(values[1] for values in new_cache.values())
    deletions = sum(values[2] for values in new_cache.values())
    default_branch_commits = sum(values[3] for values in new_cache.values())
    external_pr_additions, external_pr_deletions, merged_prs = fetch_external_merged_pr_loc()
    total_additions = additions + external_pr_additions
    total_deletions = deletions + external_pr_deletions
    contribution_commits = (
        user["contributionsCollection"]["totalCommitContributions"]
        + user["contributionsCollection"]["restrictedContributionsCount"]
    )
    return {
        "repos": user["repositories"]["totalCount"],
        "contributed": user["repositoriesContributedTo"]["totalCount"],
        "stars": sum(repo["stargazerCount"] for repo in repos),
        "followers": user["followers"]["totalCount"],
        "merged_prs": merged_prs,
        "commits_year": contribution_commits,
        "commits_default": default_branch_commits,
        "loc_net": total_additions - total_deletions,
        "loc_add": total_additions,
        "loc_del": total_deletions,
        "loc_direct_add": additions,
        "loc_direct_del": deletions,
        "loc_pr_add": external_pr_additions,
        "loc_pr_del": external_pr_deletions,
        "top_languages": top_language_text,
    }


def compact_number(value: int) -> str:
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,}"


def dot_fill(length: int) -> str:
    return (". " * (max(0, length) // 2 + 1))[:max(0, length)]


def row(key: str, value: str, y: int) -> str:
    prefix = f". {key}: "
    gap = PANEL_CHARS - len(prefix) - len(value) - 1
    return (
        f'<text x="{PANEL_X}" y="{y}" xml:space="preserve">'
        f'<tspan fill="var(--muted)">. </tspan>'
        f'<tspan fill="var(--key)">{html.escape(key)}:</tspan>'
        f'<tspan fill="var(--muted)"> {html.escape(dot_fill(gap))} </tspan>'
        f'<tspan fill="var(--value)">{html.escape(value)}</tspan></text>'
    )


def double_row(
    key_one: str, value_one: str, key_two: str, value_two: str, y: int
) -> str:
    left_width = 36
    left_gap = left_width - len(key_one) - len(value_one) - 5
    right_gap = PANEL_CHARS - left_width - len(key_two) - len(value_two) - 5
    return (
        f'<text x="{PANEL_X}" y="{y}" xml:space="preserve">'
        f'<tspan fill="var(--muted)">. </tspan>'
        f'<tspan fill="var(--key)">{html.escape(key_one)}:</tspan>'
        f'<tspan fill="var(--muted)"> {html.escape(dot_fill(left_gap))} </tspan>'
        f'<tspan fill="var(--value)">{html.escape(value_one)}</tspan>'
        f'<tspan fill="var(--muted)"> | </tspan>'
        f'<tspan fill="var(--key)">{html.escape(key_two)}:</tspan>'
        f'<tspan fill="var(--muted)"> {html.escape(dot_fill(right_gap))} </tspan>'
        f'<tspan fill="var(--value)">{html.escape(value_two)}</tspan></text>'
    )


def section(label: str, y: int) -> str:
    inner = f" {label} "
    left_size = (PANEL_CHARS - len(inner)) // 2
    right_size = PANEL_CHARS - len(inner) - left_size
    return (
        f'<text x="{PANEL_X}" y="{y}" fill="var(--muted)" xml:space="preserve">'
        f'{"─" * left_size}<tspan fill="var(--key)" font-weight="700">'
        f'{html.escape(inner)}</tspan>{"─" * right_size}</text>'
    )


def portrait_markup() -> str:
    lines = (ASSETS / "art.txt").read_text().splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise RuntimeError("assets/art.txt does not contain portrait data")
    line_height = min(11.5, 620 / len(lines))
    return "\n".join(
        f'<tspan x="24" y="{30 + index * line_height:.2f}">{html.escape(line or " ")}</tspan>'
        for index, line in enumerate(lines)
    )


def render(stats: dict[str, object], theme_name: str) -> str:
    theme = THEMES[theme_name]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1416 692" role="img" aria-labelledby="title desc">',
        '<title id="title">Vaibhaav Tiwari — live developer profile</title>',
        '<desc id="desc">Terminal-inspired profile with an ASCII portrait and live GitHub activity.</desc>',
        '<style>',
        ':root {' + " ".join(f'--{key}: {value};' for key, value in theme.items()) + '}',
        'text { font-family: "JetBrains Mono", "SFMono-Regular", Consolas, "Liberation Mono", monospace; font-size: 16px; }',
        '.portrait { font-family: Menlo, Monaco, "Courier New", monospace; font-size: 9px; font-weight: 700; fill: var(--portrait); }',
        '</style>',
        '<rect x="0.5" y="0.5" width="1415" height="691" rx="12" fill="var(--background)" stroke="var(--border)"/>',
        f'<text class="portrait" xml:space="preserve">{portrait_markup()}</text>',
        f'<text x="{PANEL_X}" y="36" fill="var(--heading)" font-weight="700" xml:space="preserve">vaibhaav@github <tspan fill="var(--muted)">─────────────────────────────────────────────────────</tspan></text>',
    ]

    y = 70
    for key, value in DETAIL_ROWS:
        parts.append(row(key, value, y))
        y += 26

    y += 14
    parts.append(row("languages.programming", "python, c++, golang, typescript", y))
    y += 26
    parts.append(row("interests.software", "devtools, research, rl envs, agents, model archs", y))
    y += 26
    parts.append(row("interests.offline", "poker, films, books, stories, homelab tinkering", y))

    y += 38
    parts.append(section("contact", y))
    y += 32
    for key, value in CONTACT_ROWS:
        parts.append(row(key, value, y))
        y += 26

    y += 12
    parts.append(section("github stats · live", y))
    y += 32
    parts.append(double_row(
        "repos", f'{stats["repos"]} {{contributed: {stats["contributed"]}}}',
        "stars", str(stats["stars"]), y
    ))
    y += 26
    parts.append(double_row(
        "commits (year)", str(stats["commits_year"]),
        "followers", str(stats["followers"]), y
    ))
    y += 26
    parts.append(double_row(
        "merged PRs", str(stats["merged_prs"]),
        "default commits", f'{stats["commits_default"]:,}', y
    ))
    y += 26

    net = int(stats["loc_net"])
    additions = int(stats["loc_add"])
    deletions = int(stats["loc_del"])
    net_text = f"{net:,}"
    value_text = f"{net_text} (+{compact_number(additions)}, -{compact_number(deletions)})"
    prefix = ". github LoC: "
    fill = dot_fill(PANEL_CHARS - len(prefix) - len(value_text) - 1)
    parts.append(
        f'<text x="{PANEL_X}" y="{y}" xml:space="preserve">'
        f'<tspan fill="var(--muted)">. </tspan><tspan fill="var(--key)">github LoC:</tspan>'
        f'<tspan fill="var(--muted)"> {html.escape(fill)} </tspan>'
        f'<tspan fill="var(--value)">{net_text} (</tspan>'
        f'<tspan fill="var(--plus)">+{compact_number(additions)}</tspan>'
        f'<tspan fill="var(--value)">, </tspan>'
        f'<tspan fill="var(--minus)">-{compact_number(deletions)}</tspan>'
        f'<tspan fill="var(--value)">)</tspan></text>'
    )
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def write_readme() -> None:
    version = int(dt.datetime.now(dt.timezone.utc).timestamp())
    (ROOT / "README.md").write_text(
        "<picture>\n"
        f'  <source media="(prefers-color-scheme: dark)" srcset="assets/dark_mode.svg?v={version}">\n'
        f'  <source media="(prefers-color-scheme: light)" srcset="assets/light_mode.svg?v={version}">\n'
        f'  <img alt="Vaibhaav Tiwari live developer profile" src="assets/dark_mode.svg?v={version}">\n'
        "</picture>\n"
    )


def write_if_changed(path: Path, content: str) -> bool:
    if path.exists() and path.read_text() == content:
        return False
    path.write_text(content)
    return True


def main() -> None:
    stats = fetch_stats()
    ASSETS.mkdir(parents=True, exist_ok=True)
    visual_changed = False
    for theme_name in THEMES:
        visual_changed |= write_if_changed(
            ASSETS / f"{theme_name}_mode.svg", render(stats, theme_name)
        )
    if visual_changed or not (ROOT / "README.md").exists():
        write_readme()
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
