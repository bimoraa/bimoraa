from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import quote


__display_limit = 8
__login = "bimoraa"
__language_colors = {
    "astro": "#ff5a03",
    "css": "#563d7c",
    "dockerfile": "#384d54",
    "html": "#e34c26",
    "javascript": "#f1e05a",
    "lua": "#000080",
    "luau": "#00a2ff",
    "python": "#3572a5",
    "shell": "#89e051",
    "swift": "#f05138",
    "typescript": "#3178c6",
}


def __request(path, token):
    environment = os.environ.copy()
    if token:
        environment["GH_TOKEN"] = token
    result = subprocess.run(
        ["gh", "api", path],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
        env=environment,
    )
    return json.loads(result.stdout)


def __repositories(token):
    try:
        repositories = __request(
            "/user/repos?affiliation=owner&per_page=100&sort=updated", token
        )
        owned = [
            repository
            for repository in repositories
            if repository.get("owner", {}).get("login", "").lower() == __login
        ]
        if owned:
            return owned
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return __request(
        f"/users/{__login}/repos?type=owner&per_page=100&sort=updated", token
    )


def __language_totals(token):
    totals = {}
    repositories = []
    for repository in __repositories(token):
        if repository.get("fork"):
            continue
        full_name = repository.get("full_name")
        if not full_name:
            continue
        repositories.append(full_name)

    def load_languages(full_name):
        try:
            languages = __request(f"/repos/{quote(full_name, safe='/')}/languages", token)
        except (OSError, subprocess.SubprocessError, ValueError):
            return {}
        return languages

    with ThreadPoolExecutor(max_workers=8) as executor:
        requests = [executor.submit(load_languages, full_name) for full_name in repositories]
        for request in as_completed(requests):
            languages = request.result()
            for name, size in languages.items():
                if isinstance(size, int) and size > 0:
                    totals[name] = totals.get(name, 0) + size
    if not totals:
        raise RuntimeError("GitHub returned no language data for bimoraa repositories")
    return totals


def __color(name):
    return __language_colors.get(name.lower(), "#959da5")


def __render(totals):
    total_bytes = sum(totals.values())
    languages = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    visible = languages[:__display_limit]
    bar_width = 460
    row_height = 24
    height = 86 + row_height * len(visible)
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="480" height="{height}" role="img">',
        "  <title>Most used programming languages</title>",
        "  <style>svg{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;color:#777}.heading{fill:#0366d6;font-size:16px}.label{fill:#777;font-size:14px}.detail{fill:#666;font-size:12px}</style>",
        f'  <text class="heading" x="8" y="22">{len(totals)} Languages</text>',
        '  <text class="label" x="8" y="45">Most used languages</text>',
        f'  <rect x="10" y="54" width="{bar_width}" height="8" rx="5" fill="#ebedf0"/>',
    ]
    offset = 10
    for name, size in visible:
        width = bar_width * size / total_bytes
        lines.append(
            f'  <rect x="{offset:.2f}" y="54" width="{width:.2f}" height="8" fill="{__color(name)}"/>'
        )
        offset += width
    for index, (name, size) in enumerate(visible):
        y = 84 + row_height * index
        percentage = 100 * size / total_bytes
        escaped_name = html.escape(name)
        lines.extend(
            [
                f'  <circle cx="16" cy="{y - 4}" r="4" fill="{__color(name)}"/>',
                f'  <text class="label" x="28" y="{y}">{escaped_name}</text>',
                f'  <text class="detail" x="470" y="{y}" text-anchor="end">{percentage:.2f}%</text>',
            ]
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def main():
    token = os.environ.get("GH_TOKEN", "")
    output = Path(__file__).resolve().parents[2] / "metrics.plugin.languages.svg"
    output.write_text(__render(__language_totals(token)), encoding="utf-8")
    print(f"Generated {output.name}")


if __name__ == "__main__":
    main()
