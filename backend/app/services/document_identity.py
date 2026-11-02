"""Preserve serial evidence and require explicit review of multiple identities."""
import json
import re

SERIAL_CANDIDATES_FIELD = 'serial_candidates'
# Prefer the complete label; never fall back to treating its word Number as a value.
# Horizontal separators keep an empty field from consuming the next PDF text line.
_SERIAL_PATTERN = re.compile(
    r'(?<!\w)(?:S/N|Serial[ \t]+Number\b|Serial(?![ \t]+Number)|Número[ \t]+de[ \t]+Serie)'
    r'(?:[ \t]*:[ \t]*|[ \t]+)([A-Za-z0-9\-_]+)', re.IGNORECASE,
)


def serial_identity_fields(text):
    candidates = sorted(set(match.group(1).strip() for match in _SERIAL_PATTERN.finditer(text)))
    if len(candidates) > 1:
        return {'serial_number': '', SERIAL_CANDIDATES_FIELD: json.dumps(candidates, ensure_ascii=False)}
    return {'serial_number': candidates[0]} if candidates else {}


def unresolved_serial_ambiguity(fields):
    if SERIAL_CANDIDATES_FIELD not in fields:
        return False
    try:
        candidates = json.loads(fields[SERIAL_CANDIDATES_FIELD])
    except (ValueError, TypeError):
        return True
    if not isinstance(candidates, list) or len(candidates) < 2 or not all(isinstance(value, str) and value for value in candidates):
        return True
    if len(set(candidates)) != len(candidates):
        return True
    return fields.get('serial_number') not in candidates


def guard_merged_identity(merged, deterministic):
    """An LLM cannot resolve textual ambiguity or silently replace a known serial."""
    if not isinstance(merged.get("serial_number", ""), str):
        merged["serial_number"] = deterministic.get("serial_number", "")
    if SERIAL_CANDIDATES_FIELD in deterministic:
        merged.update(serial_number='', serial_candidates=deterministic[SERIAL_CANDIDATES_FIELD])
    elif deterministic.get('serial_number') and merged.get('serial_number') != deterministic['serial_number']:
        candidates = sorted({deterministic['serial_number'], merged['serial_number']})
        merged.update(serial_number='', serial_candidates=json.dumps(candidates, ensure_ascii=False))
    return merged
