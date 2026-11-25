#!/usr/bin/env python3
"""Checks the files in entries/. Standard library only.

    python3 tools/validate.py                      every entry; exit 1 on any problem
    python3 tools/validate.py entries/my-tool.json only the files named

The rules are described in README.md, "Fields".
"""
import datetime
import ipaddress
import json
import os
import re
import sys
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRIES = os.path.join(ROOT, "entries")

FIELDS = ("name", "author", "description", "repo", "web_url", "api_url", "api_docs",
          "status", "access", "tags", "last_verified")
REQUIRED = ("name", "author", "description", "status", "last_verified")
LINKS = ("repo", "web_url", "api_url")
URL_FIELDS = ("repo", "web_url", "api_url", "api_docs")
TEXT_LIMITS = {"name": 80, "author": 80, "description": 600, "access": 200}
STATUSES = ("live", "experimental", "retired")
MAX_BYTES = 4096
MAX_TAGS = 8
MAX_URL = 300

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,49}$")
TAG = re.compile(r"^[a-z0-9][a-z0-9-]{0,29}$")
REPO = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(/tree/[A-Za-z0-9_./-]+)?$")
URL_CHARS = re.compile(r"^[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+$")
CREDENTIAL_PARAM = re.compile(r"(?i)(^|[?&;])[^=&;]*(token|secret|passw|api[_-]?key|signature|(?<![a-z])auth(?![a-z]))[^=&;]*=")
PRIVATE_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".ts.net")

# Characters that hide text from a person reading the file: zero-width and
# direction marks, and the invisible "tag" block.
HIDDEN = re.compile("[​-‏‪-‮⁠-⁤﻿\U000e0000-\U000e007f]")

SECRETS = (
    ("a GitHub token", re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")),
    ("an API key", re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9_-]{20,}")),
    ("a Slack token", re.compile(r"\bxox[abeoprs]-[A-Za-z0-9-]{10,}")),
    ("an AWS access key", re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY")),
    ("a bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}")),
    ("a status console token", re.compile(r"\bdst_[A-Za-z0-9_-]{12,}")),
)
OPAQUE = re.compile(r"[A-Za-z0-9+_=-]{48,}")


def text_problems(field, value, limit):
    out = []
    if not isinstance(value, str):
        return ["%s must be a string" % field]
    if not value.strip():
        return ["%s is empty" % field]
    if value != value.strip():
        out.append("%s has leading or trailing spaces" % field)
    if len(value) > limit:
        out.append("%s is %d characters; the limit is %d" % (field, len(value), limit))
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        out.append("%s must be one line without control characters" % field)
    if HIDDEN.search(value):
        out.append("%s contains invisible characters" % field)
    return out


def secret_problems(field, value, opaque=True):
    out = ["%s looks like it contains %s; never put a credential here" % (field, what)
           for what, pattern in SECRETS if pattern.search(value)]
    if opaque and not out and OPAQUE.search(value):
        out.append("%s contains a long unbroken string that looks like a credential" % field)
    return out


def host_problem(host):
    h = (host or "").rstrip(".")
    if not h:
        return "has no host"
    if h == "localhost" or h.endswith(PRIVATE_SUFFIXES):
        return "points at a private name; this directory is public"
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return None if "." in h else "points at a host name that is not public"
    return None if ip.is_global else "points at a private or reserved address; this directory is public"


def url_problems(field, value):
    if not isinstance(value, str):
        return ["%s must be a string" % field]
    if len(value) > MAX_URL:
        return ["%s is longer than %d characters" % (field, MAX_URL)]
    if not URL_CHARS.match(value):
        return ["%s contains characters that are not allowed in a URL" % field]
    try:
        parts = urlsplit(value)
        host = parts.hostname
        parts.port
    except ValueError:
        return ["%s is not a valid URL" % field]
    out = []
    if parts.scheme != "https":
        out.append("%s must start with https://" % field)
    if parts.username is not None or parts.password is not None:
        out.append("%s must not contain a user name or password" % field)
    problem = host_problem(host)
    if problem:
        out.append("%s %s" % (field, problem))
    if CREDENTIAL_PARAM.search("?" + parts.query) or CREDENTIAL_PARAM.search("?" + parts.fragment):
        out.append("%s carries what looks like a credential in its query" % field)
    if field == "repo" and not REPO.match(value):
        out.append("repo must look like https://github.com/<owner>/<name>, optionally followed by /tree/<branch>/<path>")
    return out + secret_problems(field, value, opaque=False)


def validate_entry(slug, data, today=None):
    """Problems with one entry, as a list of sentences. Empty means valid."""
    out = []
    if not SLUG.match(slug or ""):
        out.append("the file name must be 2 to 50 characters of a-z, 0-9 and '-', starting with a letter or digit, plus .json")
    if not isinstance(data, dict):
        return out + ["the file must hold one JSON object"]
    for key in data:
        if key not in FIELDS:
            out.append("unknown field %r (known: %s)" % (key, ", ".join(FIELDS)))
    for key in REQUIRED:
        if key not in data:
            out.append("%s is required" % key)
    for key, limit in TEXT_LIMITS.items():
        if key in data:
            problems = text_problems(key, data[key], limit)
            out += problems
            if not problems:
                out += secret_problems(key, data[key])
    for key in URL_FIELDS:
        if key in data:
            out += url_problems(key, data[key])
    if not any(key in data for key in LINKS):
        out.append("give at least one of %s" % ", ".join(LINKS))
    if "status" in data and data["status"] not in STATUSES:
        out.append("status must be one of %s" % ", ".join(STATUSES))
    if "tags" in data:
        tags = data["tags"]
        if not isinstance(tags, list) or len(tags) > MAX_TAGS or not all(isinstance(t, str) and TAG.match(t) for t in tags):
            out.append("tags must be a list of at most %d short lower-case words (a-z, 0-9, '-')" % MAX_TAGS)
        elif len(set(tags)) != len(tags):
            out.append("tags repeats a word")
    if "last_verified" in data:
        today = today or datetime.datetime.now(datetime.timezone.utc).date()
        try:
            if not isinstance(data["last_verified"], str) or len(data["last_verified"]) != 10:
                raise ValueError
            day = datetime.date.fromisoformat(data["last_verified"])
        except ValueError:
            out.append("last_verified must be a date written YYYY-MM-DD")
        else:
            if day > today + datetime.timedelta(days=1):
                out.append("last_verified is in the future")
            elif day.year < 2024:
                out.append("last_verified is implausibly old")
    return out


def _no_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("the field %r appears twice" % key)
        seen[key] = value
    return seen


def check_bytes(slug, raw, today=None):
    """Parse and validate the bytes of one entry file. Returns (data or None, problems)."""
    if len(raw) > MAX_BYTES:
        return None, ["the file is %d bytes; the limit is %d" % (len(raw), MAX_BYTES)]
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except UnicodeDecodeError:
        return None, ["the file is not UTF-8"]
    except ValueError as e:
        return None, ["the file is not valid JSON: %s" % e]
    problems = validate_entry(slug, data, today)
    return (data if isinstance(data, dict) else None), problems


def load_entries(directory=ENTRIES, only=None):
    """Read entries from a folder. Returns ({slug: data}, [problem, ...])."""
    entries, problems = {}, []
    wanted = None if only is None else {os.path.abspath(p) for p in only}
    for name in sorted(os.listdir(directory)):
        path = os.path.join(directory, name)
        shown = "entries/" + name
        if os.path.isdir(path) or not name.endswith(".json"):
            problems.append("%s: entries/ holds only <slug>.json files" % shown)
            continue
        if wanted is not None and os.path.abspath(path) not in wanted:
            continue
        with open(path, "rb") as f:
            data, found = check_bytes(name[:-5], f.read())
        problems += ["%s: %s" % (shown, p) for p in found]
        if data is not None:
            entries[name[:-5]] = data
    names = {}
    for slug, data in entries.items():
        key = str(data.get("name", "")).strip().lower()
        if key and key in names:
            problems.append("entries/%s.json: the name %r is already used by entries/%s.json" % (slug, data["name"], names[key]))
        names.setdefault(key, slug)
    return entries, problems


def main(argv):
    only = argv or None
    if only:
        missing = [p for p in only if not os.path.isfile(p)]
        if missing:
            print("no such file: " + ", ".join(missing))
            return 1
    entries, problems = load_entries(only=only)
    for p in problems:
        print(p)
    print("%d entr%s checked, %d problem%s" % (len(entries), "y" if len(entries) == 1 else "ies",
                                               len(problems), "" if len(problems) == 1 else "s"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
