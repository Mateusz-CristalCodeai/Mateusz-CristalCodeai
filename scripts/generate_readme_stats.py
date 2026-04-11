#!/usr/bin/env python3

from __future__ import annotations

import html
import json
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from urllib import error, parse, request

API_ROOT = "https://api.github.com"
GRAPHQL_URL = f"{API_ROOT}/graphql"
OUTPUT_DIR = Path("assets")
STATS_PATH = OUTPUT_DIR / "profile-github-stats.svg"
LANGS_PATH = OUTPUT_DIR / "profile-top-languages.svg"
CARD_WIDTH = 420
CARD_HEIGHT = 180
TITLE_COLOR = "#00ff41"
TEXT_COLOR = "#7ee787"
MUTED_COLOR = "#8b949e"
BG_COLOR = "#0d1117"
BORDER_COLOR = "#00c853"
GRID_COLOR = "#17301d"
TRACK_COLOR = "#132117"
BAR_COLORS = ["#00ff41", "#32d74b", "#84cc16", "#22c55e", "#10b981"]
LANGUAGE_COLORS = {
    "Python": "#3572A5",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "Shell": "#89e051",
    "Jupyter Notebook": "#DA5B0B",
    "QML": "#44a51c",
    "C++": "#f34b7d",
    "C": "#555555",
    "Dockerfile": "#384d54",
}


def api_headers(token: str) -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "mateusz-readme-stats-generator",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def github_request(url: str, token: str, data: Dict[str, object] | None = None) -> object:
    payload = None
    headers = api_headers(token)
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=payload, headers=headers)
    try:
        with request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API request failed: {exc.code} {body}") from exc


def fetch_user(username: str, token: str) -> Dict[str, object]:
    return github_request(f"{API_ROOT}/users/{parse.quote(username)}", token)


def fetch_repositories(username: str, token: str) -> List[Dict[str, object]]:
    repos: List[Dict[str, object]] = []
    page = 1
    while True:
        url = (
            f"{API_ROOT}/users/{parse.quote(username)}/repos"
            f"?per_page=100&type=owner&sort=updated&page={page}"
        )
        batch = github_request(url, token)
        if not isinstance(batch, list):
            raise RuntimeError("Unexpected repositories payload from GitHub API.")
        if not batch:
            break
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_contribution_count(username: str, token: str) -> int | None:
    if not token:
        return None

    query = {
        "query": """
            query($login: String!) {
              user(login: $login) {
                contributionsCollection {
                  contributionCalendar {
                    totalContributions
                  }
                }
              }
            }
        """,
        "variables": {"login": username},
    }

    try:
        data = github_request(GRAPHQL_URL, token, query)
    except RuntimeError:
        return None

    user = data.get("data", {}).get("user") if isinstance(data, dict) else None
    if not user:
        return None

    collection = user.get("contributionsCollection", {})
    calendar = collection.get("contributionCalendar", {})
    total = calendar.get("totalContributions")
    return int(total) if isinstance(total, int) else None


def fetch_languages(repositories: Iterable[Dict[str, object]], token: str) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for repo in repositories:
        url = repo.get("languages_url")
        if not isinstance(url, str):
            continue
        try:
            payload = github_request(url, token)
        except RuntimeError:
            continue
        if not isinstance(payload, dict):
            continue
        for language, size in payload.items():
            if isinstance(language, str) and isinstance(size, int):
                totals[language] = totals.get(language, 0) + size
    return totals


def format_number(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def escape(text: str) -> str:
    return html.escape(text, quote=True)


def render_card_shell(inner: str) -> str:
    return f"""<svg width="{CARD_WIDTH}" height="{CARD_HEIGHT}" viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-hidden="true">
  <rect x="1" y="1" width="{CARD_WIDTH - 2}" height="{CARD_HEIGHT - 2}" rx="14" fill="{BG_COLOR}" stroke="{BORDER_COLOR}" stroke-width="2"/>
  <path d="M24 58H396" stroke="{GRID_COLOR}" stroke-width="1"/>
  <style>
    .title {{ fill: {TITLE_COLOR}; font: 700 20px 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }}
    .metric-label {{ fill: {MUTED_COLOR}; font: 600 11px 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; letter-spacing: .08em; text-transform: uppercase; }}
    .metric-value {{ fill: {TEXT_COLOR}; font: 700 26px 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }}
    .body {{ fill: {TEXT_COLOR}; font: 600 13px 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }}
    .footer {{ fill: {MUTED_COLOR}; font: 500 11px 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }}
  </style>
  {inner}
</svg>
"""


def render_stats_svg(username: str, user: Dict[str, object], repositories: List[Dict[str, object]], contributions: int | None) -> str:
    public_repos = int(user.get("public_repos", 0))
    followers = int(user.get("followers", 0))
    non_fork_repos = [repo for repo in repositories if not repo.get("fork")]
    stars = sum(int(repo.get("stargazers_count", 0)) for repo in non_fork_repos)
    forks = sum(int(repo.get("forks_count", 0)) for repo in non_fork_repos)
    fourth_label = "Contributions" if contributions is not None else "Forks"
    fourth_value = contributions if contributions is not None else forks

    inner = f"""
  <text class="title" x="24" y="38">{escape(username)} // profile stats</text>

  <text class="metric-label" x="24" y="82">Public repos</text>
  <text class="metric-value" x="24" y="112">{format_number(public_repos)}</text>

  <text class="metric-label" x="220" y="82">Followers</text>
  <text class="metric-value" x="220" y="112">{format_number(followers)}</text>

  <text class="metric-label" x="24" y="132">Stars</text>
  <text class="metric-value" x="24" y="162">{format_number(stars)}</text>

  <text class="metric-label" x="220" y="132">{escape(fourth_label)}</text>
  <text class="metric-value" x="220" y="162">{format_number(int(fourth_value))}</text>
  <text class="footer" x="24" y="172">public profile data // refreshed in-repo</text>
"""
    return render_card_shell(inner)


def render_languages_svg(username: str, languages: Dict[str, int]) -> str:
    total = sum(languages.values())
    rows = []
    sorted_languages: List[Tuple[str, int]] = sorted(
        languages.items(),
        key=lambda item: (-item[1], item[0].lower()),
    )[:5]

    if total == 0 or not sorted_languages:
        inner = f"""
  <text class="title" x="24" y="38">{escape(username)} // top languages</text>
  <text class="body" x="24" y="94">No language data available yet.</text>
  <text class="footer" x="24" y="154">run the workflow after the first push on main</text>
"""
        return render_card_shell(inner)

    y = 70
    for index, (language, size) in enumerate(sorted_languages):
        percent = (size / total) * 100
        fill = LANGUAGE_COLORS.get(language, BAR_COLORS[index % len(BAR_COLORS)])
        bar_width = max(8, round((size / total) * 220))
        row = f"""
  <text class="body" x="24" y="{y}">{escape(language)}</text>
  <text class="footer" x="362" y="{y}" text-anchor="end">{percent:.1f}%</text>
  <rect x="24" y="{y + 8}" width="220" height="8" rx="4" fill="{TRACK_COLOR}"/>
  <rect x="24" y="{y + 8}" width="{bar_width}" height="8" rx="4" fill="{fill}"/>
"""
        rows.append(row)
        y += 22

    inner = f"""
  <text class="title" x="24" y="38">{escape(username)} // top languages</text>
  {''.join(rows)}
  <text class="footer" x="24" y="174">aggregated from public, non-fork repositories</text>
"""
    return render_card_shell(inner)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> int:
    username = os.getenv("PROFILE_USERNAME", "Mateusz-CristalCodeai").strip()
    token = os.getenv("PROFILE_STATS_TOKEN", "").strip() or os.getenv("GITHUB_TOKEN", "").strip()

    try:
        user = fetch_user(username, token)
        repositories = fetch_repositories(username, token)
        languages = fetch_languages([repo for repo in repositories if not repo.get("fork")], token)
        contributions = fetch_contribution_count(username, token)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    write_text(STATS_PATH, render_stats_svg(username, user, repositories, contributions))
    write_text(LANGS_PATH, render_languages_svg(username, languages))
    print(f"Wrote {STATS_PATH} and {LANGS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
