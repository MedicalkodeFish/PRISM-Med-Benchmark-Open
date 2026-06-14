import ast
import json
import os
import re
from typing import Any, List, Optional


def _verbose_parse_logs() -> bool:
    return os.getenv("PRISM_VERBOSE_JSON_PARSE", "").strip().lower() in ("1", "true", "yes")


def _log_parse(msg: str) -> None:
    if _verbose_parse_logs():
        print(msg)


def _normalize_smart_quotes(text: str) -> str:
    return (
        text.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )


def _span_of_balanced_brackets(s: str, open_idx: int) -> Optional[tuple[int, int]]:
    """Return (start, end_exclusive) for a [...] segment starting at open_idx."""
    if open_idx < 0 or open_idx >= len(s) or s[open_idx] != "[":
        return None
    depth = 0
    in_string = False
    escape = False
    quote_char = ""

    for j in range(open_idx, len(s)):
        ch = s[j]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote_char:
                in_string = False
            continue
        if ch in ('"', "'"):
            in_string = True
            quote_char = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return (open_idx, j + 1)
    return None


def _extract_array_literal(text: str) -> Optional[str]:
    """Find a JSON/Python array substring using bracket matching (not regex)."""
    text = _normalize_smart_quotes(text)

    for marker in ("```json", "```JSON"):
        pos = text.find(marker)
        if pos >= 0:
            bracket_start = text.find("[", pos + len(marker))
            if bracket_start >= 0:
                span = _span_of_balanced_brackets(text, bracket_start)
                if span:
                    return text[span[0] : span[1]]

    legacy = text.find("<[")
    if legacy >= 0:
        bracket_start = legacy + 1
        span = _span_of_balanced_brackets(text, bracket_start)
        if span:
            return text[span[0] : span[1]]

    stripped = text.strip()
    if stripped.startswith("["):
        span = _span_of_balanced_brackets(stripped, 0)
        if span:
            return stripped[span[0] : span[1]]

    bracket_start = text.find("[")
    if bracket_start >= 0:
        span = _span_of_balanced_brackets(text, bracket_start)
        if span:
            return text[span[0] : span[1]]
    return None


def _wrap_as_array_if_needed(fragment: str) -> str:
    s = fragment.strip()
    if s.startswith("["):
        return s
    return f"[{s}]"


def _loads_array(payload: str) -> Optional[List[Any]]:
    payload = payload.strip()
    if not payload.startswith("["):
        payload = _wrap_as_array_if_needed(payload)

    try:
        data = json.loads(payload)
        return data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        pass

    try:
        data = ast.literal_eval(payload)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except (SyntaxError, ValueError):
        pass
    return None


def parse_json_with_fallbacks(json_str: str) -> Optional[List[Any]]:
    """Parse checker output (array or comma-separated objects) with repair fallbacks."""
    candidates: list[str] = []
    raw = json_str.strip()
    candidates.append(_wrap_as_array_if_needed(raw))

    cleaned = raw.replace("\\n", "\n")
    if cleaned != raw:
        candidates.append(_wrap_as_array_if_needed(cleaned))

    # Do not blanket unescape quotes; it often breaks valid JSON. Try only on failure path below.
    for base in (raw, cleaned):
        inner = base
        if inner.startswith("[") and inner.endswith("]"):
            inner = inner[1:-1].strip()
        candidates.append(_wrap_as_array_if_needed(inner))

    seen: set[str] = set()
    last_err: Optional[Exception] = None

    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)

        parsed = _loads_array(cand)
        if parsed is not None:
            return parsed

        try:
            json.loads(cand)
        except json.JSONDecodeError as e:
            last_err = e

        # Fallback: normalize doubled backslashes before quotes, then nested-quote repair.
        cleaned_str = cand
        try:
            fixed_str = re.sub(
                r'(": ")([^"]*?)("(?:[^"]*?)")([^"]*?)(")',
                r'\1\2\\"\3\\"\4\5',
                cleaned_str,
            )
            parsed = _loads_array(fixed_str)
            if parsed is not None:
                return parsed
        except Exception as e:
            last_err = e

        try:
            pattern = r'": "(.*?)"(?=,|\s*})'

            def escape_inner_quotes(match: re.Match[str]) -> str:
                value = match.group(1)
                escaped = re.sub(r'(?<!\\)"', r'\\"', value)
                return '": "' + escaped + '"'

            aggressive_fix = re.sub(pattern, escape_inner_quotes, cleaned_str, flags=re.DOTALL)
            parsed = _loads_array(aggressive_fix)
            if parsed is not None:
                return parsed
        except Exception as e:
            last_err = e

        # Single-quoted Python-style dicts (common checker mistake).
        if "'" in cand and '"' not in cand[:80]:
            try:
                pyish = cand.replace("true", "True").replace("false", "False").replace("null", "None")
                data = ast.literal_eval(pyish)
                if isinstance(data, list):
                    return data
            except (SyntaxError, ValueError) as e:
                last_err = e

    if last_err is not None:
        preview = json_str[:120].replace("\n", " ")
        print(f"Checker JSON parse failed: {last_err} | preview: {preview!r}…")
    else:
        print("Checker JSON parse failed: unknown format")
    return None


def extract_content(text: str) -> Optional[List[Any]]:
    if not text or not str(text).strip():
        print("No supported JSON content format found (empty checker response)")
        return None

    text = _normalize_smart_quotes(text)

    if re.search(r"(?i)^\s*no\s+diagnosis\s*$", text.strip()):
        return None

    array_literal = _extract_array_literal(text)
    if array_literal:
        parsed = _loads_array(array_literal)
        if parsed is not None:
            return parsed
        inner = array_literal[1:-1].strip() if array_literal.startswith("[") else array_literal
        return parse_json_with_fallbacks(inner)

    # Legacy regex paths (kept for very short responses).
    for pattern in (
        r"```json\s*(\[[\s\S]*\])\s*```",
        r"<\[([\s\S]*)\]>",
        r"^\s*(\[[\s\S]*\])\s*$",
    ):
        match = re.search(pattern, text, re.DOTALL)
        if match:
            blob = match.group(1).strip()
            if blob.startswith("["):
                parsed = _loads_array(blob)
                if parsed is not None:
                    return parsed
            return parse_json_with_fallbacks(blob)

    _log_parse("No supported JSON content format found")
    print("No supported JSON content format found")
    return None


def extract_diagnoses(dict_result):
    if dict_result is None:
        return [], "Not found"

    potential_diagnoses = []
    mostlikely_diag = "Not found"

    try:
        if isinstance(dict_result, list):
            for item in dict_result:
                if not isinstance(item, dict):
                    continue

                for key in item.keys():
                    if "potential" in key.lower() and "diagnos" in key.lower():
                        if isinstance(item[key], dict):
                            potential_diagnoses = list(item[key].keys())
                            break

                for key in item.keys():
                    if "most likely" in key.lower() and "diagnos" in key.lower():
                        val = item[key]
                        if isinstance(val, dict):
                            mostlikely_diag = val.get("your answer") or val.get("answer") or next(
                                iter(val.values()), "Not found"
                            )
                        else:
                            mostlikely_diag = val
                        break

        elif isinstance(dict_result, dict):
            for key in dict_result.keys():
                if "potential" in key.lower() and "diagnos" in key.lower():
                    if isinstance(dict_result[key], dict):
                        potential_diagnoses = list(dict_result[key].keys())
                        break

            for key in dict_result.keys():
                if "most likely" in key.lower() and "diagnos" in key.lower():
                    val = dict_result[key]
                    if isinstance(val, dict):
                        mostlikely_diag = val.get("your answer") or val.get("answer") or next(
                            iter(val.values()), "Not found"
                        )
                    else:
                        mostlikely_diag = val
                    break

        if isinstance(mostlikely_diag, str):
            mostlikely_diag = re.sub(r"^\d+\.\s*", "", mostlikely_diag).strip()

        return potential_diagnoses, mostlikely_diag
    except Exception as e:
        print(f"Error extracting diagnoses: {e}")
        return [], "Error"
