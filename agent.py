#!/usr/bin/env python3
"""Zero-dependency course matching, topic scouting, drafting, and Bluesky publishing."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / "data" / "catalog.json"
PLAYBOOK_PATH = ROOT / "data" / "playbook.json"
CHANNELS_PATH = ROOT / "data" / "channels.json"
WORK_DIR = ROOT / "work"
MATCH_THRESHOLD = 2.0


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


CATALOG = read_json(CATALOG_PATH)
PLAYBOOK = read_json(PLAYBOOK_PATH)
CHANNELS_DATA = read_json(CHANNELS_PATH)
CHANNELS = CHANNELS_DATA["channels"]
COURSES = CATALOG["courses"]


def normalize(value: str) -> str:
    value = value.lower().replace("&", " and ")
    return re.sub(r"[^a-z0-9+#.\s-]", " ", value).replace("-", " ").strip()


def score_course(need: str, course: dict[str, Any]) -> tuple[float, list[str]]:
    text = f" {normalize(need)} "
    hits: list[str] = []
    score = 0.0
    for raw_keyword in course.get("keywords", []):
        keyword = normalize(raw_keyword)
        if not keyword:
            continue
        if f" {keyword} " in text:
            # Specific phrases carry more evidence than broad single-word matches.
            weight = min(2.5, 0.9 + 0.32 * len(keyword.split()))
            score += weight
            hits.append(raw_keyword)

    # Outcomes contribute a lighter semantic signal for ordinary phrasing.
    terms = {w for w in text.split() if len(w) > 3}
    for outcome in course.get("outcomes", []):
        overlap = terms.intersection(normalize(outcome).split())
        if overlap:
            score += min(0.6, 0.15 * len(overlap))
    return round(score, 2), hits


def recommend(need: str) -> list[dict[str, Any]]:
    ranked = []
    for course in COURSES:
        score, hits = score_course(need, course)
        ranked.append({"course": course, "score": score, "matched_keywords": hits})
    return sorted(ranked, key=lambda row: (row["score"], len(row["matched_keywords"])), reverse=True)


def gemini_course_choice(need: str) -> dict[str, Any] | None:
    """Use the configured free-tier model to semantically route a need into our catalog."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash-lite").strip()
    records = [{key: course[key] for key in ("id", "title", "audience", "outcomes", "prerequisites")}
               for course in COURSES]
    prompt = {
        "learner_need": need,
        "course_catalog": records,
        "routing_examples": PLAYBOOK.get("routing_examples", []),
        "task": (
            "Choose the single best course only if its published outcomes directly address the learner's need. "
            "Otherwise return course_id null and confidence low. Do not infer outcomes beyond the supplied catalog. "
            "A course recommendation is not a guaranteed solution. Return a concise factual reason and only IDs from the catalog."
        ),
        "required_json": {"course_id": "catalog id or null", "confidence": "high, medium, or low",
                          "reason": "short factual fit explanation", "alternative_ids": ["catalog ids only"]},
    }
    endpoint = ("https://generativelanguage.googleapis.com/v1beta/models/" +
                urllib.parse.quote(model, safe="") + ":generateContent?key=" + urllib.parse.quote(api_key, safe=""))
    try:
        response = http_json(endpoint, method="POST", body={
            "contents": [{"parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 250, "responseMimeType": "application/json"},
        })
        raw = response["candidates"][0]["content"]["parts"][0]["text"]
        choice = json.loads(raw)
        valid_ids = {course["id"] for course in COURSES}
        if choice.get("course_id") not in valid_ids and choice.get("course_id") is not None:
            return None
        if choice.get("confidence") not in {"high", "medium", "low"}:
            return None
        choice["alternative_ids"] = [value for value in choice.get("alternative_ids", []) if value in valid_ids]
        return choice
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError, TypeError):
        return None


def selected_course(need: str, *, allow_ai: bool = True) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    ranked = recommend(need)
    if allow_ai:
        choice = gemini_course_choice(need)
        if choice and (choice.get("course_id") is None or choice.get("confidence") == "low"):
            return None, ranked
        if choice and choice.get("course_id") and choice.get("confidence") in {"high", "medium"}:
            by_id = {course["id"]: course for course in COURSES}
            selected = by_id[choice["course_id"]]
            row = next((item for item in ranked if item["course"]["id"] == selected["id"]),
                       {"course": selected, "score": 0.0, "matched_keywords": []})
            row = dict(row)
            row["ai_confidence"] = choice["confidence"]
            row["ai_reason"] = choice.get("reason", "")
            return selected, [row] + [item for item in ranked if item["course"]["id"] != selected["id"]]
    if not ranked or ranked[0]["score"] < MATCH_THRESHOLD:
        return None, ranked
    return ranked[0]["course"], ranked


def score_label(score: float) -> str:
    if score >= 5.0:
        return "high"
    if score >= MATCH_THRESHOLD:
        return "medium"
    return "low"


def rank_channels(need: str) -> list[dict[str, Any]]:
    selected, _ = selected_course(need, allow_ai=False)
    context = normalize(need + " " + (selected["title"] + " " + " ".join(selected.get("audience", []))
                                       + " " + " ".join(selected.get("keywords", [])) if selected else ""))
    ranked = []
    for channel in CHANNELS:
        topics = [topic for topic in channel.get("audience_topics", []) if normalize(topic) in context]
        status = channel["promotion_status"]
        always_relevant = channel["id"] in {
            "bluesky-brand", "udemy-promotional-email", "youtube-educational-video", "udemy-community"
        }
        if not topics and not always_relevant:
            continue
        ranked.append({
            "id": channel["id"], "name": channel["name"], "fit": channel["fit"],
            "promotion_status": status, "automation": channel["automation"],
            "cost": channel["cost"], "limits": channel["limits"],
            "source_url": channel["source_url"], "topic_matches": topics,
            "recommended_for_promotion": status in {
                "allowed_on_own_brand_feed", "allowed_with_rules", "allowed_with_platform_rules"
            },
        })
    ranked.sort(key=lambda item: (
        item["recommended_for_promotion"],
        item["promotion_status"] == "allowed_on_own_brand_feed",
        len(item["topic_matches"]),
    ), reverse=True)
    return ranked


def http_json(url: str, *, method: str = "GET", body: dict[str, Any] | None = None,
              headers: dict[str, str] | None = None, timeout: int = 25) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request_headers = {"User-Agent": "CoursePromotionScout/1.0 (public educational research)",
                       "Accept": "application/json"}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def match_command(args: argparse.Namespace) -> int:
    selected, ranked = selected_course(args.need)
    result = {
        "need": args.need,
        "recommendation": selected,
        "confidence": (ranked[0].get("ai_confidence", score_label(ranked[0]["score"]))
                       if selected else "insufficient-fit"),
        "reason": ((ranked[0].get("ai_reason") or
                    ("Matched terms: " + ", ".join(ranked[0]["matched_keywords"][:5]))) if selected else None),
        "ranked": [
            {"id": item["course"]["id"], "title": item["course"]["title"],
             "url": item["course"]["url"], "score": item["score"],
             "matched_keywords": item["matched_keywords"]}
            for item in ranked[:5]
        ],
        "decision": "recommend" if selected else "do_not_pitch",
        "channel_options": rank_channels(args.need),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def scout_command(args: argparse.Namespace) -> int:
    now = dt.datetime.now(dt.timezone.utc)
    from_date = int((now - dt.timedelta(days=args.days)).timestamp())
    # Pull recent titles across these three expert communities, then match locally.
    # Avoid restrictive full-text queries so questions phrased in ordinary language are not missed.
    sites = ["robotics", "engineering", "physics"]
    questions: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for site in sites:
        params = urllib.parse.urlencode({
            "order": "desc", "sort": "creation", "site": site,
            "fromdate": from_date, "pagesize": 50,
        })
        url = f"https://api.stackexchange.com/2.3/questions?{params}"
        try:
            payload = http_json(url)
            for question in payload.get("items", []):
                questions[str(question["question_id"])] = question
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            errors.append(f"{site}: {type(exc).__name__}")

    items = []
    for question in questions.values():
        title = question.get("title", "")
        tags = question.get("tags", [])
        need = f"{title} {' '.join(tags)}"
        selected, ranked = selected_course(need, allow_ai=False)
        items.append({
            "question_id": question.get("question_id"),
            "title": title,
            "source_url": question.get("link"),
            "source_site": question.get("link", "").split("/")[2] if question.get("link") else "",
            "created_at": dt.datetime.fromtimestamp(question.get("creation_date", 0), dt.timezone.utc).isoformat(),
            "score": question.get("score", 0),
            "answer_count": question.get("answer_count", 0),
            "tags": tags,
            "recommended_course": selected["title"] if selected else None,
            "recommended_course_id": selected["id"] if selected else None,
            "recommended_course_url": selected["url"] if selected else None,
            "match_confidence": score_label(ranked[0]["score"]) if selected else "insufficient-fit",
            "match_score": ranked[0]["score"] if ranked else 0,
            "matched_keywords": ranked[0]["matched_keywords"] if ranked else [],
            "purpose": "topic research only; do not promote in this Q&A source",
            "promotion_allowed_in_source": False,
        })
    items.sort(key=lambda item: (item["match_confidence"] == "high", item["match_score"], item["created_at"]), reverse=True)
    result = {
        "generated_at": now.isoformat(),
        "days": args.days,
        "sources": ["Robotics Stack Exchange", "Engineering Stack Exchange", "Physics Stack Exchange"],
        "note": "Public questions are market/topic signals only. No promotional replies or DMs are drafted for these sites.",
        "errors": errors,
        "opportunities": items,
    }
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(items)} public topic signals to {output}")
    if errors:
        print("Some sources were unavailable: " + ", ".join(errors), file=sys.stderr)
    return 0


def generate_with_gemini(need: str, course: dict[str, Any]) -> str | None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash-lite").strip()
    prompt = {
        "need": need,
        "brand": PLAYBOOK["brand_name"],
        "disclosure": PLAYBOOK["brand_disclosure"],
        "course": {key: course[key] for key in ("title", "url", "audience", "outcomes", "prerequisites")},
        "sales_process": PLAYBOOK.get("sales_process", []),
        "rules": PLAYBOOK.get("rules", []),
        "content_style": PLAYBOOK.get("content_style", "Helpful and factual."),
        "instructions": (
            "Write one short standalone educational Bluesky post in English, no more than 250 characters before URL. "
            "Address the stated need with one concrete, accurate tip, then say the instructor offers the relevant course. "
            "Include the exact course URL and instructor disclosure. Do not invent results, prices, discounts, scarcity, "
            "ratings, credentials, or facts not in the supplied course record. No hashtags required. Return only the post text."
        ),
    }
    endpoint = ("https://generativelanguage.googleapis.com/v1beta/models/" +
                urllib.parse.quote(model, safe="") + ":generateContent?key=" + urllib.parse.quote(api_key, safe=""))
    try:
        response = http_json(endpoint, method="POST", body={
            "contents": [{"parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
            "generationConfig": {"temperature": 0.45, "maxOutputTokens": 220},
        })
        candidates = response.get("candidates", [])
        return candidates[0]["content"]["parts"][0]["text"].strip() if candidates else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError):
        return None


def fallback_draft(need: str, course: dict[str, Any]) -> str:
    outcome = course["outcomes"][0].rstrip(".")
    opening = {
        "applied-physics-1": "For a vibration problem, start with mass, stiffness, and damping; compare the natural frequency with the forcing.",
        "applied-physics-3": "GPS timing depends on relativistic clock corrections; modern physics connects the equations to real technology.",
        "mems-1": "At MEMS scales, surface and electrostatic effects can matter more than the forces you expect from large machines.",
        "mems-2": "In capacitive MEMS sensing, sensitivity, linearity, and pull-in limits must be considered together.",
        "mems-3": "MEMS reliability depends on fabrication, packaging, and testing as well as the device design.",
        "practical-mechanics-1": "Choosing machine parts? Compare load, speed, torque, and precision before selecting a component.",
        "practical-mechanics-2": "A part can be strong enough and still flex too much; check both strength and stiffness in the design.",
        "industry-4-0-1": "A smart factory connects machine data, control systems, and process context so teams can make better decisions.",
        "industry-4-0-2": "Choose a manufacturing process by balancing geometry, material, production volume, and process limits.",
        "industry-4-0-3": "Predictive maintenance starts with a measurable failure mode and useful sensor data.",
        "plastics-2": "Injection-molding defects have causes: check material, mold, and process conditions together.",
        "plastics-1": "For a hot enclosure, compare a polymer's thermal limits and mechanical properties with the operating conditions.",
        "plastics-3": "Polymer processing choices affect part geometry, material properties, production rate, and recycling options.",
        "applied-physics-2": "For a thermal problem, identify the heat-transfer mode first: conduction, convection, or radiation.",
    }.get(course["id"], f"A useful starting point: {outcome[0].lower() + outcome[1:] if outcome else 'define the engineering problem'}.")
    post = f"{opening} I'm Pedro Portugal, the instructor. If you want to learn more: {course['url']}"
    return post


def prepare_draft(need: str, course: dict[str, Any], use_ai: bool = True,
                  confidence: str | None = None) -> dict[str, Any]:
    text = generate_with_gemini(need, course) if use_ai else None
    source = "gemini_free_tier" if text else "factual_template"
    if not text or course["url"] not in text or len(text) > PLAYBOOK["max_post_chars"]:
        text = fallback_draft(need, course)
        source = "factual_template"
    # Only permit the selected course URL in an auto-published draft.
    urls = re.findall(r"https?://\S+", text)
    if any(url.rstrip(".,)") != course["url"] for url in urls):
        text = fallback_draft(need, course)
        source = "factual_template"
    return {
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "need": need,
        "course_id": course["id"],
        "course_title": course["title"],
        "course_url": course["url"],
        "confidence": confidence or score_label(score_course(need, course)[0]),
        "source": source,
        "text": text,
    }


def draft_command(args: argparse.Namespace) -> int:
    course, ranked = selected_course(args.need)
    if not course:
        print(json.dumps({"decision": "do_not_pitch", "need": args.need,
                          "reason": "No course has a sufficiently strong catalog match.",
                          "best_candidates": [
                              {"title": row["course"]["title"], "score": row["score"]}
                              for row in ranked[:3]
                          ]}, ensure_ascii=False, indent=2))
        return 2
    confidence = ranked[0].get("ai_confidence", score_label(ranked[0]["score"]))
    result = prepare_draft(args.need, course, use_ai=not args.template_only, confidence=confidence)
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def channels_command(args: argparse.Namespace) -> int:
    result = {"need": args.need, "channels_checked_at": CHANNELS_DATA.get("checked_at"),
              "reminder": "Recheck the linked official rules before posting; only Bluesky publishing is automated in this MVP.",
              "channels": rank_channels(args.need)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def bsky_session(handle: str, app_password: str) -> tuple[str, str]:
    payload = http_json("https://bsky.social/xrpc/com.atproto.server.createSession", method="POST",
                        body={"identifier": handle, "password": app_password})
    return payload["accessJwt"], payload["did"]


def bsky_author_feed(handle: str, token: str) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"actor": handle, "limit": 30})
    response = http_json("https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?" + params)
    return response.get("feed", [])


def link_facets(text: str) -> list[dict[str, Any]]:
    facets = []
    for match in re.finditer(r"https://\S+", text):
        uri = match.group(0).rstrip(".,)")
        end = match.start() + len(uri)
        facets.append({
            "index": {"byteStart": len(text[:match.start()].encode("utf-8")),
                      "byteEnd": len(text[:end].encode("utf-8"))},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": uri}],
        })
    return facets


def publish_command(args: argparse.Namespace) -> int:
    if os.getenv("AUTO_PUBLISH", "").lower() not in {"true", "1", "yes"}:
        print("Publishing is disabled. Set AUTO_PUBLISH=true only after reviewing drafts and configuring the brand account.", file=sys.stderr)
        return 3
    handle = os.getenv("BSKY_HANDLE", "").strip()
    password = os.getenv("BSKY_APP_PASSWORD", "").strip()
    if not handle or not password:
        print("Missing BSKY_HANDLE or BSKY_APP_PASSWORD; no post was sent.", file=sys.stderr)
        return 3
    if args.need:
        need = args.need
        course, ranked = selected_course(need)
        if not course:
            print(json.dumps({"status": "no_fit_skipped", "need": need,
                              "message": "No course has a sufficiently strong fit; no post was sent."}, indent=2))
            return 4
    elif args.lead_file and Path(args.lead_file).exists():
        # Use public discussions to spot demand, then publish a standalone brand post.
        # Never reply to the question or advertise on its source community.
        lead_data = read_json(Path(args.lead_file))
        candidates = [item for item in lead_data.get("opportunities", [])
                     if item.get("recommended_course_id") and item.get("match_confidence") in {"high", "medium"}]
        candidates.sort(key=lambda item: (item.get("match_confidence") == "high",
                                          item.get("match_score", 0), item.get("created_at", "")), reverse=True)
        if candidates:
            lead = candidates[0]
            signal_need = lead.get("title", "") + " " + " ".join(lead.get("tags", []))
            course, ranked = selected_course(signal_need)
            if not course:
                course = next((entry for entry in COURSES if entry["id"] == lead["recommended_course_id"]), None)
            if course:
                # The source question is only a routing signal. Public post text comes from course facts,
                # not from copying or replying to the community member's content.
                need = (f"Write a standalone educational post for our own brand feed about {course['title']}. "
                        f"Use only this verified course outcome as the topic: {course['outcomes'][0]}. "
                        "Do not quote, identify, reply to, or link to the source discussion.")
        else:
            course = None
        if not course:
            today = dt.datetime.now(dt.timezone.utc).date()
            course = COURSES[today.toordinal() % len(COURSES)]
            need = f"A learner wants a practical introduction to {course['title']}: {course['outcomes'][0]}"
    else:
        # An evergreen topic calendar covers all courses; no external prospect is targeted.
        today = dt.datetime.now(dt.timezone.utc).date()
        course = COURSES[today.toordinal() % len(COURSES)]
        need = f"A learner wants a practical introduction to {course['title']}: {course['outcomes'][0]}"
    draft = prepare_draft(need, course, use_ai=True)
    if len(draft["text"]) > PLAYBOOK["max_post_chars"]:
        draft["text"] = fallback_draft(need, course)

    token, did = bsky_session(handle, password)
    today = dt.datetime.now(dt.timezone.utc).date()
    for item in bsky_author_feed(handle, token):
        record = item.get("post", {}).get("record", {})
        created = record.get("createdAt", "")
        if created.startswith(today.isoformat()):
            print(json.dumps({"status": "daily_limit_reached", "uri": item.get("post", {}).get("uri"),
                              "message": "The brand account already has a post today; skipped to keep the agent to one post per UTC day."}, ensure_ascii=False, indent=2))
            return 0

    record = {"$type": "app.bsky.feed.post", "text": draft["text"],
              "createdAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
              "langs": ["en"]}
    facets = link_facets(record["text"])
    if facets:
        record["facets"] = facets
    response = http_json("https://bsky.social/xrpc/com.atproto.repo.createRecord", method="POST",
                         headers={"Authorization": "Bearer " + token},
                         body={"repo": did, "collection": "app.bsky.feed.post", "record": record})
    result = {"status": "published", "uri": response.get("uri"), "cid": response.get("cid"),
              "course_id": course["id"], "course_title": course["title"], "confidence": draft["confidence"],
              "generation_source": draft["source"], "text": draft["text"]}
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    with (WORK_DIR / "publication-log.jsonl").open("a", encoding="utf-8") as handle_out:
        handle_out.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Context-aware course promotion agent")
    sub = parser.add_subparsers(dest="command", required=True)
    match_parser = sub.add_parser("match", help="Match a learner need to a course")
    match_parser.add_argument("need")
    match_parser.set_defaults(func=match_command)

    scout_parser = sub.add_parser("scout", help="Find public engineering questions as topic signals")
    scout_parser.add_argument("--days", type=int, default=14)
    scout_parser.add_argument("--out", default="work/leads.json")
    scout_parser.set_defaults(func=scout_command)

    draft_parser = sub.add_parser("draft", help="Draft a course-matched educational post")
    draft_parser.add_argument("--need", required=True)
    draft_parser.add_argument("--out", default="work/draft.json")
    draft_parser.add_argument("--template-only", action="store_true", help="Do not call Gemini even if configured")
    draft_parser.set_defaults(func=draft_command)

    channels_parser = sub.add_parser("channels", help="Rank no-cost channel options and show their promotion rules")
    channels_parser.add_argument("--need", required=True)
    channels_parser.set_defaults(func=channels_command)

    publish_parser = sub.add_parser("publish", help="Publish one post to the separate Bluesky brand account")
    publish_parser.add_argument("--need", help="Optional campaign context / learner need")
    publish_parser.add_argument("--lead-file", help="Optional scout JSON: use a public question as a topic signal")
    publish_parser.set_defaults(func=publish_command)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "scout" and not 1 <= args.days <= 90:
        parser.error("--days must be between 1 and 90")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

