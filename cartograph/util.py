"""Shared utility functions used across cartograph modules."""

from __future__ import annotations

import hashlib
import re
from typing import Any, TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from .indexer import ServiceContext


def slug(value: str) -> str:
    value = value.strip().strip("'\"")
    value = value.replace("_", "-").lower()
    value = re.sub(r"^https?://", "", value)
    value = value.split("/")[0]
    return value


def first_string(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r'"([^"]+)"|\'([^\']+)\'', text)
    return next((g for g in m.groups() if g), None) if m else None


def join_paths(base: str, child: str) -> str:
    if not base and not child:
        return "/"
    return "/" + "/".join(part.strip("/") for part in (base, child) if part and part != "/")


def split_url(url: str) -> tuple[str, str]:
    if "${" in url:
        host_match = re.search(r"\$\{([^}]+)}", url)
        host = host_match.group(1) if host_match else ""
        tail = url.split("}", 1)[-1] if "}" in url else ""
        return host, tail or "/"
    if url.startswith("/"):
        return "", url
    parsed = urlparse(url)
    return parsed.netloc, parsed.path or "/"


def infer_http_method(line: str) -> str:
    lowered = line.lower()
    for method in ("get", "post", "put", "delete", "patch"):
        if method in lowered:
            return method.upper()
    return "GET"


def xml_attrs(text: str) -> dict[str, str]:
    return {
        match.group(1): match.group(2) or match.group(3)
        for match in re.finditer(r"([\w:-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", text)
    }


def xml_tag_value(text: str, tag: str) -> str | None:
    match = re.search(rf"<{re.escape(tag)}\b[^>]*>(.*?)</{re.escape(tag)}>", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()


def first_xml_attr(text: str, tag: str, attr: str) -> str | None:
    match = re.search(rf"<{re.escape(tag)}\b([^>]*)>", text, flags=re.IGNORECASE)
    if not match:
        return None
    return xml_attrs(match.group(1)).get(attr)


def line_for_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def sql_operation(line: str) -> str | None:
    stripped = line.strip().lower()
    for operation in ("select", "insert", "update", "delete", "merge", "call"):
        if (
            stripped.startswith(operation + " ")
            or stripped.startswith(operation + "\t")
            or stripped.startswith(operation + "(")
        ):
            return operation.upper()
    return None


def object_string_value(line: str, key: str) -> str | None:
    m = re.search(rf"{key}\s*:\s*['\"]([^'\"]+)['\"]", line)
    return m.group(1) if m else None


def struts_action_path(namespace: str, name: str, extension: str) -> str:
    action = name.strip()
    if action.startswith("/"):
        base = action
    else:
        base = join_paths(namespace, action)
    if extension and not base.endswith(extension):
        base += extension
    return base


def gateway_target_path(path_pattern: str, strip_prefix: int = 0) -> str:
    path = path_pattern.split(",", 1)[0].strip()
    path = re.sub(r"\*\*$", "", path).rstrip("/")
    parts = [part for part in path.split("/") if part]
    if strip_prefix:
        parts = parts[strip_prefix:]
    return "/" + "/".join(parts) if parts else "/"


def extract_topics(text: str) -> list[str]:
    values = []
    list_match = re.search(r"topics\s*=\s*\{([^}]+)}", text)
    if list_match:
        values.extend(re.findall(r'"([^"]+)"', list_match.group(1)))
    single = re.search(r"topics\s*=\s*\"([^\"]+)\"", text)
    if single:
        values.append(single.group(1))
    if not values:
        values.extend(re.findall(r'"([^"]+)"', text))
    return values or ["{unknown}"]


def extract_group_id(text: str) -> str | None:
    m = re.search(r"groupId\s*=\s*\"([^\"]+)\"", text)
    return m.group(1) if m else None


def extract_message_send_topic(line: str, producer_methods: list[str]) -> tuple[str | None, str | None]:
    for token in sorted(producer_methods, key=len, reverse=True):
        index = line.find(token)
        if index < 0:
            continue
        tail = line[index + len(token) :]
        literal = re.match(r'\s*"([^"]+)"', tail)
        if literal:
            return literal.group(1), None
        variable = re.match(r"\s*(\w+)", tail)
        if variable:
            return None, variable.group(1)
    return None, None


def collect_string_fields(lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        m = re.search(r"\b(?:private|protected|public)?\s*(?:final\s+)?String\s+(\w+)\s*=\s*\"([^\"]+)\"", line)
        if m:
            fields[m.group(1)] = m.group(2)
    return fields


def previous_key(lines: list[str], idx: int, key: str) -> bool:
    start = max(0, idx - 4)
    return any(re.match(rf"\s*{re.escape(key)}\s*:", line) for line in lines[start:idx])


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    path = re.sub(r"\{[^}]+}", "{}", path)
    return "/" + path.strip("/")


def node(
    ctx: ServiceContext, label: str, rel: str, line_no: int, source: str, confidence: str, **props: Any
) -> dict[str, Any]:
    digest = hashlib.sha1(f"{ctx.name}:{rel}:{line_no}:{label}:{source}:{props}".encode()).hexdigest()[:10]
    base = {
        "id": f"{ctx.name}:{rel}:{line_no}:{digest}",
        "label": label,
        "service": ctx.name,
        "source": source,
        "confidence": confidence,
    }
    base.update(props)
    return base


def edge(kind: str, from_node: dict[str, Any], to_node: dict[str, Any], confidence: str) -> dict[str, Any]:
    return {
        "type": kind,
        "from": from_node["id"],
        "to": to_node["id"],
        "from_service": from_node["service"],
        "to_service": to_node["service"],
        "cross_repo": from_node["service"] != to_node["service"],
        "confidence": confidence,
    }
