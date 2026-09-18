"""
llm_judge.py
------------
Takes the rule-based facts produced by scraper.py and asks an LLM
to turn them into a *judgment*: a 0-100 score, missing features, specific
recommendations, and a priority level.

Supports two providers, picked automatically based on which API key is set
(see judge_site() / _pick_provider()):
  - Google Gemini (free tier)   -> set GEMINI_API_KEY
  - Anthropic Claude            -> set ANTHROPIC_API_KEY

IMPORTANT SEPARATION OF CONCERNS:
  - scraper.py answers "what is objectively true about this page's HTML?"
  - llm_judge.py answers "given those facts, how good is this site and what
    should the business do about it?"
These are kept in separate dict keys in the final report (see report_generator.py)
so a reader always knows which parts are deterministic and which are AI opinion.

Usage:
  export GEMINI_API_KEY=AIza...       # free tier -- get one at https://aistudio.google.com/apikey
  # or: export ANTHROPIC_API_KEY=sk-ant-...
  from llm_judge import judge_site
  judgment = judge_site(facts_dict)

If neither API key is set, judge_site() returns a clearly-labeled MOCK judgment
so the rest of the pipeline (and this demo) still runs end-to-end.

Provider selection:
  - If both keys are set, GEMINI is preferred by default (free tier) unless
    LLM_PROVIDER=anthropic is set.
  - Set LLM_PROVIDER=gemini or LLM_PROVIDER=anthropic to force one explicitly.
"""
import os
import json
import re

ANTHROPIC_MODEL = "claude-sonnet-4-6"
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

SYSTEM_PROMPT = """You are a senior website auditor who specializes in the immigration
consultancy / visa services industry. You will be given a JSON object of
FACTS that were extracted automatically by a script (not by you) from a
business's website. You must NOT invent facts that aren't in the JSON.

Your job: turn these facts into a professional audit judgment.

A professional, business-ready immigration consultancy website typically needs:
- Clear contact info (phone AND email, ideally a real contact form)
- A visible primary call-to-action (free consultation / eligibility check / book a call)
- Trust signals (credentials, licensing/registration info, testimonials, case results)
- An FAQ section (visa processes generate lots of repeat questions)
- Working social proof / social links
- Mobile responsiveness (viewport meta tag as a proxy signal)
- Basic SEO hygiene (title, meta description, alt text on images)
- Reasonable page depth (not just a single page with no service detail)
- Fast enough load time

Respond with ONLY a JSON object (no markdown fences, no preamble) matching
this exact schema:

{
  "score": <integer 0-100>,
  "score_rationale": "<1-2 sentence explanation tied to specific facts>",
  "missing_features": ["<specific missing feature>", ...],
  "problems": ["<specific problem, tied to a fact>", ...],
  "recommendations": [
    {"action": "<specific, concrete action>", "priority": "high|medium|low", "why": "<short reason>"}
  ],
  "overall_priority": "high|medium|low"
}

Be specific and reference the actual facts you were given (e.g. "no contact
form was detected and only 40% of images have alt text") rather than generic
advice like "improve your website." If a fact is missing/unknown, say so
rather than guessing.
"""


def _build_user_prompt(facts: dict) -> str:
    return "FACTS:\n" + json.dumps(facts, indent=2, default=str)


def _mock_judgment(facts: dict) -> dict:
    """
    Deterministic, clearly-labeled placeholder used when no API key is
    configured, so the pipeline can still be demoed/tested offline.
    This is NOT a real AI judgment -- it's a rough heuristic stand-in.
    """
    score = 50
    problems = []
    missing = []
    recs = []

    if not facts.get("contact_form_present"):
        score -= 15
        missing.append("Contact form")
        problems.append("No contact form detected on crawled pages")
        recs.append({"action": "Add a contact/lead form with email + phone fields",
                      "priority": "high", "why": "Forms convert visitors into leads better than a bare email link"})
    if not facts.get("has_meta_description"):
        score -= 5
        missing.append("Meta description")
        problems.append("Homepage has no meta description tag")
        recs.append({"action": "Write a 150-160 character meta description summarizing services",
                      "priority": "medium", "why": "Improves click-through rate from search results"})
    if not facts.get("faq_present"):
        score -= 5
        missing.append("FAQ section")
    if not facts.get("viewport_meta_present"):
        score -= 10
        problems.append("No mobile viewport meta tag found")
        recs.append({"action": "Add a responsive viewport meta tag and test on mobile",
                      "priority": "high", "why": "Most visa/immigration searches happen on mobile"})
    if facts.get("cta_count", 0) == 0:
        score -= 10
        missing.append("Clear call-to-action button")
    if facts.get("alt_text_coverage_pct") is not None and facts["alt_text_coverage_pct"] < 50:
        score -= 5
        problems.append(f"Only {facts['alt_text_coverage_pct']}% of images have alt text")

    score = max(0, min(100, score))
    overall_priority = "high" if score < 50 else "medium" if score < 75 else "low"

    return {
        "score": score,
        "score_rationale": "MOCK JUDGMENT (no ANTHROPIC_API_KEY set) -- heuristic estimate only, not a real LLM opinion.",
        "missing_features": missing,
        "problems": problems,
        "recommendations": recs,
        "overall_priority": overall_priority,
        "_mock": True,
    }


def _parse_llm_json(raw_text: str) -> dict:
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```json\s*|\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
    return json.loads(cleaned)


def _pick_provider():
    """
    Decides which provider to use based on env vars.
    Returns "gemini", "anthropic", or None (-> mock).
    """
    forced = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if forced in ("gemini", "anthropic"):
        return forced

    gemini_key = os.environ.get("GEMINI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if gemini_key:
        return "gemini"
    if anthropic_key:
        return "anthropic"
    return None


def _call_anthropic(facts: dict) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    import anthropic  # raises ImportError if not installed -- caught by caller

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _build_user_prompt(facts)}],
    )
    raw_text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    )
    return _parse_llm_json(raw_text)


def _call_gemini(facts: dict) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    from google import genai  # raises ImportError if not installed -- caught by caller
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=_build_user_prompt(facts),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            max_output_tokens=1500,
        ),
    )
    raw_text = response.text
    return _parse_llm_json(raw_text)


def judge_site(facts: dict) -> dict:
    """
    Returns a dict matching the schema in SYSTEM_PROMPT.
    Falls back to a labeled mock if no API key is available or the call fails.
    """
    provider = _pick_provider()
    if provider is None:
        return _mock_judgment(facts)

    package_hint = {
        "gemini": "google-genai package not installed: pip install google-genai",
        "anthropic": "anthropic package not installed: pip install anthropic",
    }[provider]

    try:
        if provider == "gemini":
            parsed = _call_gemini(facts)
        else:
            parsed = _call_anthropic(facts)
        parsed["_mock"] = False
        parsed["_provider"] = provider
        return parsed
    except ImportError:
        result = _mock_judgment(facts)
        result["score_rationale"] += f" ({package_hint})"
        return result
    except Exception as e:
        result = _mock_judgment(facts)
        result["score_rationale"] += f" (LLM call via {provider} failed: {type(e).__name__}: {e})"
        return result
