"""
robots_check.py
----------------
Tiny helper to respect robots.txt before we scrape anything.
Not bulletproof, but it's the minimum politeness bar for an "authorized sites only" tool.
"""
import urllib.robotparser as robotparser
from urllib.parse import urlparse


def is_allowed(url: str, user_agent: str = "ImmigrationSiteAuditBot/1.0") -> bool:
    """
    Returns True if robots.txt allows this user-agent to fetch the URL.
    If robots.txt is missing or unreadable, we default to True (allowed) --
    but this tool is meant for sites you already have permission to audit,
    so robots.txt is a secondary/backup check, not the primary permission gate.
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    rp = robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:
        # Could not fetch/parse robots.txt -- don't block the audit on that alone,
        # but flag it upstream so it shows up in the report.
        return True

    try:
        return rp.can_fetch(user_agent, url)
    except Exception:
        return True
