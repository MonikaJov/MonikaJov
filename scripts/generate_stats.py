#!/usr/bin/env python3
"""
Generate neofetch-style SVG cards for the GitHub profile README.
3-section layout: About · Contact · GitHub Stats

Run:    python3 scripts/generate_stats.py
Env:    GITHUB_TOKEN  — contribution counts (auto-provided by GitHub Actions)
        GH_PAT        — personal access token with `repo` scope (enables
                         private repo LOC stats; add as a repo secret)

Output: assets/neofetch-dark.svg
        assets/neofetch-light.svg
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import avatar   # ASCII art panel — edit scripts/avatar.py to customise

# ── Config ────────────────────────────────────────────────────────────────────
USERNAME = "MonikaJov"
LINKEDIN = "linkedin.com/in/MonikaJov"
EMAIL    = "monika.jovevska.23@gmail.com"
LOCATION = "Skopje, North Macedonia"
SPEAKS   = "English, Macedonian"

# Use GH_PAT if set (private repo access), otherwise GITHUB_TOKEN
PAT   = os.environ.get("GH_PAT", "")
TOKEN = PAT or os.environ.get("GITHUB_TOKEN", "")

# Experience thresholds based on years on GitHub
# Intermediate spans 2-7 years — reflects real industry middle-ground
LEVELS = [
    (0,    2.0, "Junior"),
    (2.0,  7.0, "Intermediate"),
    (7.0, 12.0, "Senior"),
    (12.0, 999, "Principal"),
]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, "assets")

# ── API helpers ───────────────────────────────────────────────────────────────

def _headers():
    h = {"User-Agent": "readme-neofetch/2.0", "Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = f"bearer {TOKEN}"
    return h

def api_raw(path):
    """Returns (http_status, parsed_body_or_None). Never raises."""
    url = f"https://api.github.com{path}"
    req = Request(url, headers=_headers())
    try:
        with urlopen(req, timeout=25) as r:
            body = r.read()
            return r.status, (json.loads(body) if body else None)
    except HTTPError as e:
        body = e.read()
        if e.code not in (404, 409, 451):
            print(f"  HTTP {e.code} {path}", file=sys.stderr)
        return e.code, (json.loads(body) if body else None)
    except URLError as e:
        print(f"  URLError {path}: {e.reason}", file=sys.stderr)
        return 0, None

def api(path):
    status, data = api_raw(path)
    return data if status == 200 else None

def graphql(query, variables=None):
    if not TOKEN:
        return None
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    h = _headers()
    h["Content-Type"] = "application/json"
    req = Request("https://api.github.com/graphql", data=payload, headers=h)
    try:
        with urlopen(req, timeout=25) as r:
            return (json.loads(r.read()) or {}).get("data")
    except Exception as e:
        print(f"  GraphQL: {e}", file=sys.stderr)
    return None

# ── Dynamic calculations ──────────────────────────────────────────────────────

def _duration(created_at: str) -> tuple[float, str]:
    """Returns (years_float, human_str) since the given ISO date."""
    joined = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now    = datetime.now(timezone.utc)
    total_days = (now - joined).days
    years  = total_days / 365.25
    y, m   = int(years), int((years % 1) * 12)
    if y == 0:
        dur = f"{m}m"
    elif m == 0:
        dur = f"{y}y"
    else:
        dur = f"{y}y {m}m"
    return years, dur

def experience_level(created_at: str) -> str:
    years, dur = _duration(created_at)
    label = "Developer"
    for lo, hi, name in LEVELS:
        if lo <= years < hi:
            label = name
            break
    return label

def github_age(created_at: str) -> str:
    years, _ = _duration(created_at)
    y = int(years)
    return f"{y} year{'s' if y != 1 else ''} ago"

# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_repos():
    # With GH_PAT: /user/repos includes private repos owned by the user
    # Without PAT: /users/{}/repos returns only public repos
    endpoint_tmpl = (
        "/user/repos?per_page=100&page={page}&type=owner"
        if PAT else
        f"/users/{USERNAME}/repos?per_page=100&page={{page}}&type=owner"
    )
    repos, page = [], 1
    while True:
        chunk = api(endpoint_tmpl.format(page=page)) or []
        repos.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return repos

def fetch_loc(repos):
    """
    Sum lines added/deleted for USERNAME across all repos via stats/contributors.
    GitHub computes stats lazily and may return 202 on first call; we retry.
    Skipped entirely when no token is set (unauthenticated requests hit strict
    rate limits which make the retry loop prohibitively slow).
    """
    if not TOKEN:
        print("  LOC: skipped (no token) — will be filled by GitHub Action")
        return 0, 0

    total_a = total_d = 0
    ok = 0
    for repo in repos:
        rname = repo["name"]
        for attempt in range(4):
            status, data = api_raw(f"/repos/{USERNAME}/{rname}/stats/contributors")
            if status == 200 and isinstance(data, list):
                for c in data:
                    if (c.get("author") or {}).get("login", "").lower() == USERNAME.lower():
                        for w in c.get("weeks", []):
                            total_a += w.get("a", 0)
                            total_d += w.get("d", 0)
                ok += 1
                break
            elif status == 202:
                time.sleep(3 * (attempt + 1))
            else:
                break
    print(f"  LOC: {ok}/{len(repos)} repos counted")
    return total_a, total_d

EXCLUDE_LANGS = {"HTML", "Blade"}
INCLUDE_LANGS = ["SQL"]   # always shown, regardless of GitHub's linguist detection

def fetch_languages(repos):
    lang_sizes: dict = {}
    for repo in repos[:30]:
        if repo.get("fork"):
            continue
        langs = api(f"/repos/{USERNAME}/{repo['name']}/languages") or {}
        for lang, size in langs.items():
            if lang not in EXCLUDE_LANGS:
                lang_sizes[lang] = lang_sizes.get(lang, 0) + size
    top = [l for l, _ in sorted(lang_sizes.items(), key=lambda x: -x[1])[:4]]
    for lang in INCLUDE_LANGS:
        if lang not in top:
            top.append(lang)
    return top

def fetch_search_count(query: str) -> int:
    """Return total_count from GitHub Search API for the given query string."""
    from urllib.parse import quote
    data = api(f"/search/issues?q={quote(query)}&per_page=1")
    return (data or {}).get("total_count", 0)

def fetch_commit_count() -> int:
    """Count commits authored by USERNAME via Search API (public + private with PAT)."""
    from urllib.parse import quote
    h = _headers()
    h["Accept"] = "application/vnd.github.cloak-preview+json"
    url = f"https://api.github.com/search/commits?q={quote(f'author:{USERNAME}')}&per_page=1"
    req = Request(url, headers=h)
    try:
        with urlopen(req, timeout=25) as r:
            data = json.loads(r.read())
            return data.get("total_count", 0)
    except Exception as e:
        print(f"  commit search: {e}", file=sys.stderr)
    return 0

def fetch_contrib_stats(created_at: str) -> tuple:
    """Return (total_contribs, longest_streak_days) via a single GraphQL pass per year."""
    from datetime import date, timedelta
    if not TOKEN:
        return 0, 0

    joined = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    now    = datetime.now(timezone.utc)

    total_contribs = 0
    active_days: set = set()
    year = joined.year

    while year <= now.year:
        y_start = datetime(year,  1,  1,  0,  0,  0, tzinfo=timezone.utc)
        y_end   = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        from_dt = max(y_start, joined)
        to_dt   = min(y_end, now)

        data = graphql(
            """
            query($login: String!, $from: DateTime!, $to: DateTime!) {
              user(login: $login) {
                contributionsCollection(from: $from, to: $to) {
                  contributionCalendar {
                    totalContributions
                    weeks {
                      contributionDays { date contributionCount }
                    }
                  }
                }
              }
            }
            """,
            {
                "login": USERNAME,
                "from":  from_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to":    to_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )
        if data and "user" in data:
            cal = data["user"]["contributionsCollection"]["contributionCalendar"]
            total_contribs += cal["totalContributions"]
            for week in cal["weeks"]:
                for day in week["contributionDays"]:
                    if day["contributionCount"] > 0:
                        active_days.add(day["date"])

        year += 1

    if not active_days:
        return total_contribs, 0

    sorted_days = sorted(
        datetime.strptime(d, "%Y-%m-%d").date() for d in active_days
    )
    longest = current = 1
    for i in range(1, len(sorted_days)):
        if sorted_days[i] - sorted_days[i - 1] == timedelta(days=1):
            current += 1
            longest = max(longest, current)
        else:
            current = 1

    return total_contribs, longest


def fetch_coding_time() -> str:
    """Classify as Night Owl or Early Bird from recent push event hours (UTC)."""
    night = day = 0
    page  = 1
    while page <= 3:
        events = api(f"/users/{USERNAME}/events?per_page=100&page={page}") or []
        if not events:
            break
        for ev in events:
            if ev.get("type") != "PushEvent":
                continue
            ts = ev.get("created_at", "")
            if not ts:
                continue
            h = datetime.fromisoformat(ts.replace("Z", "+00:00")).hour
            if h >= 18 or h < 6:
                night += 1
            else:
                day += 1
        page += 1
    if night + day == 0:
        return "—"
    return "Night Owl" if night >= day else "Early Bird"


def fetch():
    if not TOKEN:
        print("⚠  No GITHUB_TOKEN — stats will show '—'")
    if not PAT:
        print("ℹ  Set GH_PAT secret for private repo LOC stats")
    else:
        print("✓  GH_PAT detected — private repo stats enabled")

    print("• user")
    user = api(f"/users/{USERNAME}") or {}
    created_at = user.get("created_at", "")

    print("• repos")
    repos = fetch_repos()
    originals = [r for r in repos if not r.get("fork")]
    stars = sum(r.get("stargazers_count", 0) for r in originals)

    print("• languages")
    top_langs = fetch_languages(repos)

    print(f"• commits / PRs / contributions / streak — all time ({joined_year(created_at)} → now)")
    commits          = fetch_commit_count()
    prs              = fetch_search_count(f"is:pr author:{USERNAME}")
    contribs, streak = fetch_contrib_stats(created_at)

    print("• coding time (recent events)")
    coding_time = fetch_coding_time()

    print(f"• lines of code ({len(originals)} repos)")
    loc_added, loc_deleted = fetch_loc(originals)

    return {
        "created_at":  created_at,
        "name":        user.get("name") or USERNAME,
        "level":       experience_level(created_at) if created_at else "Developer",
        "gh_age":      github_age(created_at) if created_at else "—",
        "repos":       user.get("public_repos", len(originals)),
        "stars":       stars,
        "followers":   user.get("followers", 0),
        "langs":       top_langs,
        "commits":     commits,
        "prs":         prs,
        "contribs":    contribs,
        "streak":      streak,
        "coding_time": coding_time,
        "loc_added":   loc_added,
        "loc_deleted": loc_deleted,
    }


def joined_year(created_at: str) -> int:
    if not created_at:
        return datetime.now(timezone.utc).year
    return datetime.fromisoformat(created_at.replace("Z", "+00:00")).year

# ── SVG generation ────────────────────────────────────────────────────────────

W      = 460       # stats panel width
FONT   = "'Courier New', Courier, monospace"
IX     = 10        # horizontal padding inside stats panel
LINE_H = 15        # row height
FS     = 14        # info row font size
FS_S   = 13        # section header font size
# Each char in Courier New at FS_S≈13px is ~7.8px wide
CHARS  = int((W - IX * 2) / 7.8)   # ≈ 56

# ASCII art panel settings
ASCII_PAD    = 6    # left padding before art
ASCII_GAP    = 10   # gap between art panel and stats panel
ASCII_CHAR_W = FS * 0.601  # Courier New at FS≈12.5px → ~7.5px/char

THEMES = {
    "dark": dict(
        bg      = "#0d1117",
        border  = "#21262d",
        title   = "#FFFFFF",
        sec_ln  = "#30363d",
        sec_nm  = "#FFFFFF",
        label   = "#F0C060",
        colon   = "#8b949e",
        value   = "#c9d1d9",
        added   = "#3fb950",   # GitHub diff green (dark)
        removed = "#f85149",   # GitHub diff red  (dark)
    ),
    "light": dict(
        bg      = "#ffffff",
        border  = "#d0d7de",
        title   = "#1a1a1a",
        sec_ln  = "#d0d7de",
        sec_nm  = "#1a1a1a",
        label   = "#8B3A10",
        colon   = "#57606a",
        value   = "#24292f",
        added   = "#1a7f37",   # GitHub diff green (light)
        removed = "#cf222e",   # GitHub diff red  (light)
    ),
}

def xe(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )

def section_hdr(name: str, c: dict, y: int) -> str:
    prefix = "── "
    # pad dashes so the full line fills CHARS characters
    n_dashes = max(0, CHARS - len(prefix) - len(name) - 1)
    suffix   = " " + "─" * n_dashes
    return (
        f'<text x="{IX}" y="{y}" font-family="{FONT}" font-size="{FS_S}">'
        f'<tspan fill="{c["sec_ln"]}">{xe(prefix)}</tspan>'
        f'<tspan fill="{c["sec_nm"]}" font-weight="600">{xe(name)}</tspan>'
        f'<tspan fill="{c["sec_ln"]}">{xe(suffix)}</tspan>'
        f'</text>'
    )

def loc_row(label: str, net: int, added: int, deleted: int, c: dict, y: int) -> str:
    """Single row with inline green ++ / red -- coloring."""
    lbl = label.ljust(14)
    return (
        f'<text x="{IX}" y="{y}" font-family="{FONT}" font-size="{FS}">'
        f'<tspan fill="{c["label"]}" font-weight="600">{xe(lbl)}</tspan>'
        f'<tspan fill="{c["colon"]}"> : </tspan>'
        f'<tspan fill="{c["value"]}">{net:,} (</tspan>'
        f'<tspan fill="{c["added"]}">{added:,}++</tspan>'
        f'<tspan fill="{c["value"]}"> , </tspan>'
        f'<tspan fill="{c["removed"]}">{deleted:,}--</tspan>'
        f'<tspan fill="{c["value"]}">)</tspan>'
        f'</text>'
    )

def info_row(label: str, value: str, c: dict, y: int) -> str:
    lbl = label.ljust(14)
    return (
        f'<text x="{IX}" y="{y}" font-family="{FONT}" font-size="{FS}">'
        f'<tspan fill="{c["label"]}" font-weight="600">{xe(lbl)}</tspan>'
        f'<tspan fill="{c["colon"]}"> : </tspan>'
        f'<tspan fill="{c["value"]}">{xe(value)}</tspan>'
        f'</text>'
    )

def hsep(y: int, c: dict) -> str:
    return (
        f'<line x1="{IX}" y1="{y}" x2="{W - IX}" y2="{y}" '
        f'stroke="{c["sec_ln"]}" stroke-width="1"/>'
    )

def make_svg(s: dict, theme: str, ascii_lines: list = None, mobile: bool = False) -> str:
    c = THEMES[theme]

    langs_str   = ", ".join(s["langs"]) if s["langs"] else "—"
    commits_str = f"{s['commits']:,}"  if s["commits"]  else "—"
    prs_str     = f"{s['prs']:,}"      if s["prs"]      else "—"
    cont_str    = f"{s['contribs']:,}" if s["contribs"] else "—"
    has_loc     = bool(s["loc_added"] or s["loc_deleted"])
    loc_net     = s["loc_added"] - s["loc_deleted"]

    ABOUT = [
        ("Role",          "Software Engineer"),
        ("Level",         s["level"]),
        ("Languages",     langs_str),
        ("Education",     "FINKI, UKIM"),
        ("Joined GitHub", s["gh_age"]),
        ("Speaks",        s["speaks"] if "speaks" in s else SPEAKS),
    ]
    CONTACT = [
        ("Email",    s["email"] if "email" in s else EMAIL),
        ("LinkedIn", s["linkedin"] if "linkedin" in s else LINKEDIN),
        ("Location", s["location"] if "location" in s else LOCATION),
    ]
    streak_str = f"{s['streak']} days" if s.get("streak") else "—"
    STATS = [
        ("Total Commits",  commits_str),
        ("Total PRs",      prs_str),
        ("Contributions",  cont_str),
        ("Longest Streak", streak_str),
        ("Coding Hours",   s.get("coding_time", "—")),
        ("Total Stars",    str(s["stars"])),
        ("Followers",      str(s.get("followers", 0))),
        ("Repos",          f"{s['repos']} public"),
        ("__LOC__",        ""),
    ]

    # ── Y layout ──────────────────────────────────────────────────────────────
    GAP      = 8
    PROMPT_H = LINE_H + 10   # prompt strip height at top of card

    def lay(rows, start_y):
        ys = []
        y  = start_y
        for _ in rows:
            y += LINE_H
            ys.append(y)
        return ys, y

    # Stats panel y-coords are relative (inside their own <g> translate)
    y           = 28
    title_y     = y
    y          += 16
    sep1_y      = y

    y          += GAP + LINE_H + 2
    about_hdr_y = y
    about_ys, y = lay(ABOUT, y)

    y            += GAP + LINE_H + 2
    contact_hdr_y = y
    contact_ys, y = lay(CONTACT, y)

    y           += GAP + LINE_H + 2
    stats_hdr_y  = y
    stats_ys, y  = lay(STATS, y)

    ascii_lines = ascii_lines or []
    art_w = int(max((len(l) for l in ascii_lines), default=0) * ASCII_CHAR_W)
    art_h = len(ascii_lines) * LINE_H

    # ── Dimensions (everything shifted down by PROMPT_H) ──────────────────────
    if mobile and ascii_lines:
        fox_pad   = max(ASCII_PAD, (W - art_w) // 2)
        stats_off = PROMPT_H + IX + art_h + 16
        total_w   = W
        total_h   = stats_off + y + 10
    else:
        art_off = (ASCII_PAD + art_w + ASCII_GAP) if ascii_lines else 0
        total_w = art_off + W
        total_h = PROMPT_H + max(y + 10, IX + art_h + 10)

    # ── Render ────────────────────────────────────────────────────────────────
    els = []

    # Prompt strip — full card width, above fox and stats
    prompt_y = PROMPT_H - 4
    els.append(
        f'<text x="{ASCII_PAD}" y="{prompt_y}" font-family="{FONT}" font-size="{FS_S}">'
        f'<tspan fill="{c["label"]}" font-weight="600">monika@jovevska</tspan>'
        f'<tspan fill="{c["colon"]}">:~$ </tspan>'
        f'<tspan fill="{c["value"]}">neofetch --expose-skills --ascii_distro jovka</tspan>'
        f'</text>'
    )
    if mobile and ascii_lines:
        els.append(avatar.render(ascii_lines, theme, c["bg"],
                                 pad=fox_pad, ix=PROMPT_H + IX, line_h=LINE_H,
                                 font_size=FS, font=FONT))
        els.append(f'<g transform="translate(0, {stats_off})">')
    elif ascii_lines:
        els.append(avatar.render(ascii_lines, theme, c["bg"],
                                 pad=ASCII_PAD, ix=PROMPT_H + IX, line_h=LINE_H,
                                 font_size=FS, font=FONT))
        els.append(f'<g transform="translate({art_off}, {PROMPT_H})">')

    # Title + separator
    els.append(
        f'<text x="{IX}" y="{title_y}" font-family="{FONT}" font-size="{FS}" '
        f'font-weight="bold" fill="{c["title"]}">monika@jovevska</text>'
    )
    els.append(hsep(sep1_y, c))

    # About
    els.append(section_hdr("About", c, about_hdr_y))
    for (lbl, val), row_y in zip(ABOUT, about_ys):
        els.append(info_row(lbl, val, c, row_y))

    # Contact
    els.append(section_hdr("Contact", c, contact_hdr_y))
    for (lbl, val), row_y in zip(CONTACT, contact_ys):
        els.append(info_row(lbl, val, c, row_y))

    # Stats
    els.append(section_hdr("GitHub Stats", c, stats_hdr_y))
    for (lbl, val), row_y in zip(STATS, stats_ys):
        if lbl == "__LOC__":
            if has_loc:
                els.append(loc_row("Lines of Code", loc_net, s["loc_added"], s["loc_deleted"], c, row_y))
            else:
                els.append(info_row("Lines of Code", "—", c, row_y))
        else:
            els.append(info_row(lbl, val, c, row_y))

    if ascii_lines:
        els.append('</g>')

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg"\n'
        f'     viewBox="0 0 {total_w} {total_h}" width="{total_w}" height="{total_h}">\n'
        f'  <rect width="{total_w}" height="{total_h}" rx="10" fill="{c["bg"]}"/>\n'
        f'  {"".join(els)}\n'
        f'</svg>'
    )

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    stats = fetch()

    # Merge in static config values not returned by fetch()
    stats.setdefault("email",    EMAIL)
    stats.setdefault("linkedin", LINKEDIN)
    stats.setdefault("location", LOCATION)
    stats.setdefault("speaks",   SPEAKS)

    print("\nStats:")
    for k, v in stats.items():
        if k != "created_at":
            print(f"  {k:<14}: {v}")

    os.makedirs(OUT, exist_ok=True)

    for theme in ("dark", "light"):
        ascii_path = os.path.join(OUT, f"fox-{theme}.txt")
        art        = avatar.load(ascii_path)
        if not art:
            print(f"  ⚠ {ascii_path} not found — SVG will be stats-only")

        for mobile in (False, True):
            suffix = f"{'mobile-' if mobile else ''}{theme}"
            path   = os.path.join(OUT, f"neofetch-{suffix}.svg")
            with open(path, "w", encoding="utf-8") as f:
                f.write(make_svg(stats, theme, art, mobile=mobile))
            print(f"✓ {os.path.relpath(path, ROOT)}")

if __name__ == "__main__":
    main()
