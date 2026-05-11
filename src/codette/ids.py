import hashlib


def stable_node_id(rule_id: str, file_relpath: str, canonical_text: str, line_start: int) -> str:
    norm = " ".join(canonical_text.split())
    payload = f"{rule_id}::{file_relpath}::{norm}::{line_start}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:16]
