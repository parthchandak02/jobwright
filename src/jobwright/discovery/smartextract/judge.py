"""LLM calls: JSON parsing, API-response judge, strategy briefing."""

import json
import logging
import re
import time

from jobwright.discovery.smartextract.prompts import JUDGE_PROMPT
from jobwright.llm import get_client, llm_purpose

# Same logger name as the old single module, so log output is unchanged.
log = logging.getLogger("jobwright.discovery.smartextract")



# -- LLM helpers -------------------------------------------------------------

@llm_purpose("smartextract")
def ask_llm(prompt: str) -> tuple[str, float, dict]:
    """Send prompt to LLM. Returns (response_text, seconds_taken, metadata)."""
    client = get_client()
    t0 = time.time()
    text = client.ask(prompt, temperature=0.0, max_tokens=4096)
    elapsed = time.time() - t0
    meta = {
        "finish_reason": "stop",
        "prompt_chars": len(prompt),
        "response_chars": len(text),
    }
    return text, elapsed, meta


def extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling think tags and code fences."""
    if "<think>" in text:
        after = text.split("</think>")[-1].strip()
        if after:
            text = after
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    text = text.strip()
    text = re.sub(r'\\([^"\\\/bfnrtu])', r'\1', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    while text.endswith("}") or text.endswith("]"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            text = text[:-1].rstrip()
    raise json.JSONDecodeError("Could not parse JSON", text, 0)


# -- Judge: filter API responses ---------------------------------------------


@llm_purpose("smartextract")
def judge_api_responses(api_responses: list[dict]) -> list[dict]:
    """Use the LLM to filter API responses, keeping only job-relevant ones."""
    if not api_responses:
        return []

    client = get_client()
    relevant: list[dict] = []

    for resp in api_responses:
        fields = ""
        sample = ""
        resp_type = resp.get("type", "unknown")
        if "first_item_keys" in resp:
            fields = str(resp["first_item_keys"])
            sample = json.dumps(resp.get("first_item_sample", {}), indent=2)[:500]
        elif "keys" in resp:
            fields = str(resp["keys"])
            for k, v in resp.items():
                if k.startswith("nested_"):
                    fields += f"\n  .{k.replace('nested_', '')}: {v.get('count', '?')} items, keys={v.get('first_item_keys', '?')}"
                    sample = json.dumps(v.get("first_item_sample", {}), indent=2)[:500]
        else:
            fields = "no structured data"

        prompt = JUDGE_PROMPT.format(
            url=resp.get("url", "?")[:200],
            status=resp.get("status", "?"),
            size=resp.get("size", "?"),
            type=resp_type,
            fields=fields,
            sample=sample or "n/a",
        )

        try:
            raw = client.ask(prompt, temperature=0.0, max_tokens=1024)
            verdict = extract_json(raw)
            is_relevant = verdict.get("relevant", False)
            reason = verdict.get("reason", "?")
            log.info("Judge: %s -> %s (%s)", resp.get("url", "?")[:80],
                     "KEEP" if is_relevant else "DROP", reason)
            if is_relevant:
                relevant.append(resp)
        except Exception as e:
            log.warning("Judge ERROR for %s: %s -- keeping", resp.get("url", "?")[:80], e)
            relevant.append(resp)

    return relevant


# -- Phase 1: strategy selection ---------------------------------------------

def format_strategy_briefing(intel: dict) -> str:
    """Lightweight briefing for strategy selection. No raw DOM."""
    sections: list[str] = []
    sections.append(f"PAGE: {intel['url']}")
    sections.append(f"TITLE: {intel['page_title']}")

    # JSON-LD
    if intel["json_ld"]:
        job_postings = [j for j in intel["json_ld"] if isinstance(j, dict) and j.get("@type") == "JobPosting"]
        other = [j for j in intel["json_ld"] if not (isinstance(j, dict) and j.get("@type") == "JobPosting")]
        if job_postings:
            sections.append(f"\nJSON-LD: {len(job_postings)} JobPosting entries found (usable!)")
            sections.append(f"First JobPosting:\n{json.dumps(job_postings[0], indent=2)[:3000]}")
        else:
            sections.append("\nJSON-LD: NO JobPosting entries (json_ld strategy will NOT work)")
        if other:
            types = [j.get("@type", "?") if isinstance(j, dict) else "?" for j in other]
            sections.append(f"Other JSON-LD types (NOT job data): {types}")
    else:
        sections.append("\nJSON-LD: none")

    # API responses
    if intel["api_responses"]:
        sections.append(f"\nAPI RESPONSES INTERCEPTED: {len(intel['api_responses'])} calls")
        for resp in intel["api_responses"]:
            sections.append(f"\n  URL: {resp['url']}")
            sections.append(f"  Status: {resp['status']} | Size: {resp['size']:,} chars | Type: {resp.get('type', '?')}")
            if "first_item_keys" in resp:
                sections.append(f"  Item keys: {resp['first_item_keys']}")
                sections.append(f"  Sample: {json.dumps(resp.get('first_item_sample', {}), indent=2)[:1000]}")
            if "keys" in resp:
                sections.append(f"  Object keys: {resp['keys']}")
            for k, v in resp.items():
                if k.startswith("nested_"):
                    arr_name = k.replace("nested_", "")
                    sections.append(f"  .{arr_name}: array of {v['count']} items")
                    sections.append(f"    Item keys: {v['first_item_keys']}")
                    sections.append(f"    Sample: {json.dumps(v.get('first_item_sample', {}), indent=2)[:1000]}")
                    for sk, sv in v.items():
                        if sk.startswith("first_item.") and isinstance(sv, dict):
                            sub_name = sk.replace("first_item.", "")
                            if "count" in sv:
                                sections.append(f"    .{arr_name}[0].{sub_name}: array of {sv['count']} items")
                                sections.append(f"      Item keys: {sv['first_item_keys']}")
                                sections.append(f"      Sample: {json.dumps(sv.get('first_item_sample', {}), indent=2)[:1500]}")
                            elif "keys" in sv:
                                sections.append(f"    .{arr_name}[0].{sub_name}: object with keys {sv['keys']}")
                                sections.append(f"      Sample: {json.dumps(sv.get('sample', {}), indent=2)[:1500]}")
    else:
        sections.append("\nAPI RESPONSES: none intercepted")

    # data-testid
    if intel["data_testids"]:
        sections.append(f"\nDATA-TESTID ATTRIBUTES: {len(intel['data_testids'])} elements")
        for dt in intel["data_testids"][:15]:
            text_preview = dt['text'].replace('\n', ' ')[:60]
            sections.append(f"  <{dt['tag']} data-testid=\"{dt['testid']}\"> {text_preview}")
    else:
        sections.append("\nDATA-TESTID: none found")

    # DOM stats
    stats = intel.get("dom_stats", {})
    sections.append(f"\nDOM STATS: {stats.get('total_elements', '?')} elements, "
                    f"{stats.get('links', '?')} links, {stats.get('headings', '?')} headings, "
                    f"{stats.get('tables', '?')} tables, {stats.get('articles', '?')} articles, "
                    f"{stats.get('has_data_ids', '?')} data-id elements")

    # Card candidates
    if intel["card_candidates"]:
        sections.append(f"\nREPEATING ELEMENTS DETECTED: {len(intel['card_candidates'])} candidate groups")
        for i, cand in enumerate(intel["card_candidates"]):
            sections.append(f"  [{i}] parent={cand['parent_selector']} child={cand['child_selector']} "
                          f"count={cand['total_children']} with_text={cand['with_text']} with_links={cand['with_links']}")
    else:
        sections.append("\nREPEATING ELEMENTS: none detected")

    return "\n".join(sections)
