from __future__ import annotations

import json
from pathlib import Path

from cartograph.java_lens_index import build_java_evidence_index, collect_java_lens_claims, stitch_lens_index


def test_collect_java_lens_claims_extracts_symbols_from_lens_json(tmp_path: Path) -> None:
    lens_dir = tmp_path / "lens_defs"
    lens_dir.mkdir()
    (lens_dir / "sample.json").write_text(
        json.dumps([
            {
                "name": "sample-rest",
                "scope": "source",
                "match": {
                    "files": ["*.java"],
                    "strategy": "tree-sitter",
                    "tree_sitter": {
                        "language": "java",
                        "extractor": "query",
                        "query": '(annotation name: (identifier) @ann (#eq? @ann "RestController"))',
                    },
                },
                "emit": {"label": "Service", "schema": {}, "values": {}, "source": "lens:x"},
            },
            {
                "name": "sample-call",
                "scope": "source",
                "match": {
                    "files": ["*.java"],
                    "strategy": "tree-sitter",
                    "tree_sitter": {
                        "language": "java",
                        "extractor": "method-call",
                        "method_name": "send",
                        "receiver_type": "KafkaTemplate",
                    },
                },
                "emit": {"label": "Producer", "schema": {}, "values": {}, "source": "lens:x"},
            },
        ]),
        encoding="utf-8",
    )

    claims = collect_java_lens_claims(lens_dir)

    assert {(claim.symbol, claim.kind) for claim in claims} == {
        ("KafkaTemplate", "type"),
        ("RestController", "annotation-or-type"),
        ("send", "method"),
    }


def test_build_java_evidence_index_reads_source_javadoc_and_javap(tmp_path: Path) -> None:
    root = tmp_path / "root"
    src = root / "src/main/java/example"
    docs = root / "docs"
    src.mkdir(parents=True)
    docs.mkdir()
    (src / "RestController.java").write_text(
        """
        package org.springframework.web.bind.annotation;
        public @interface RestController {}
        """,
        encoding="utf-8",
    )
    (src / "OrderController.java").write_text(
        """
        package example;
        import org.springframework.web.bind.annotation.RestController;
        @RestController
        class OrderController {
          void run(KafkaTemplate template) { template.send("orders"); }
        }
        """,
        encoding="utf-8",
    )
    (docs / "KafkaTemplate.html").write_text(
        "<html><title>Class KafkaTemplate</title><body>Class KafkaTemplate</body></html>",
        encoding="utf-8",
    )
    (root / "Client.javap").write_text(
        "public class example.Client { public void send(java.lang.String); }",
        encoding="utf-8",
    )

    index = build_java_evidence_index([root])
    data = index.to_dict()

    assert data["declarations"]["RestController"][0]["fqn"] == "org.springframework.web.bind.annotation.RestController"
    assert data["annotation_usages"]["RestController"]
    assert data["imports"]["RestController"][0]["fqn"] == "org.springframework.web.bind.annotation.RestController"
    assert data["method_calls"]["send"]
    assert data["javadocs"]["KafkaTemplate"]
    assert data["bytecode"]["Client"][0]["fqn"] == "example.Client"


def test_stitch_lens_index_links_claims_to_evidence(tmp_path: Path) -> None:
    lens_dir = tmp_path / "lens_defs"
    root = tmp_path / "root"
    lens_dir.mkdir()
    root.mkdir()
    (lens_dir / "sample.json").write_text(
        json.dumps({
            "name": "sample",
            "scope": "source",
            "match": {
                "files": ["*.java"],
                "strategy": "annotation-method",
                "class_annotations": ["@RestController"],
                "method_annotations": {"Post": "POST"},
            },
            "emit": {"label": "Endpoint", "schema": {}, "values": {}, "source": "lens:x"},
        }),
        encoding="utf-8",
    )
    (root / "Annotations.java").write_text(
        """
        package x;
        public @interface RestController {}
        public @interface PostMapping {}
        """,
        encoding="utf-8",
    )

    stitched = stitch_lens_index(collect_java_lens_claims(lens_dir), build_java_evidence_index([root]))

    assert stitched["symbols"]["RestController"]["status"] == "indexed"
    assert stitched["symbols"]["PostMapping"]["status"] == "indexed"
    assert stitched["summary"]["missing_symbols"] == 0
