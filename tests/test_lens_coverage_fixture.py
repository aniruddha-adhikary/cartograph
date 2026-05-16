"""End-to-end coverage check for newly-added / migrated lenses.

Indexes `fixtures/lens-coverage-workspace/` and asserts that at least one node
has been emitted by each of the 41 lens-file prefixes listed in PREFIXES. This
is a smoke test: if a lens regresses (regex breaks, receiver-type inference
flips, import_gate is wrong, etc.), this test goes red and names the offender.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest

from cartograph.indexer import index_workspace


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures" / "lens-coverage-workspace"


# The 41 lens-file basenames (without .json) the fixture is designed to exercise.
# Each entry corresponds to a "lens:<prefix>..." source string on at least one
# emitted node.
PREFIXES = [
    # --- Java messaging ---
    "activemq-java-direct",
    "ibmmq-java-direct",
    "rabbitmq-java-direct",
    "redis-pubsub-java",
    "aws-sdk-java",
    "gcp-pubsub-java",
    "azure-servicebus-java",
    # --- Java data ---
    "cassandra-java",
    "elasticsearch-java",
    "solr-java",
    "hibernate-search",
    "jdbc-stored-procedure",
    "spring-data-redis",
    "spring-kafka",
    "axon",
    # --- Java frameworks ---
    "spring-webflux-functional",
    "spring-batch",
    "spring-integration",
    "vertx",
    "play-framework",
    "dropwizard",
    "quarkus-rest",
    # --- JS/TS web ---
    "fastify",
    "koa",
    "hapi",
    "graphql-server",
    "trpc",
    "socketio",
    "vue-component",
    "angular-component",
    # --- JS/TS messaging ---
    "amqplib",
    "ioredis",
    "bullmq",
    "gcp-pubsub-js",
    "azure-servicebus-js",
    "aws-sdk-js",
    "mqtt",
    # --- JS/TS data ---
    "mongoose",
    "prisma",
    "typeorm",
    "sequelize",
]


# Lenses kept deliberately xfailed. Empty for now — play-framework was the
# only entry and it was fixed in Phase 4 by extending SOURCE_EXTS /
# SOURCE_BASENAMES in indexer.py. Add a corresponding note in
# cast-research/PHASE3_FIXTURE_COVERAGE.md if you ever populate this.
XFAIL_PREFIXES: set[str] = set()


@pytest.fixture(scope="module")
def coverage_graph():
    try:
        import tree_sitter  # noqa: F401
    except ImportError:
        pytest.skip("tree-sitter not available; many lenses depend on it")
    return index_workspace(FIXTURE).to_dict()


@pytest.fixture(scope="module")
def nodes_by_lens(coverage_graph):
    by_prefix: dict[str, list] = defaultdict(list)
    for node in coverage_graph.get("nodes", []):
        src = node.get("source", "")
        if src.startswith("lens:"):
            # Map full lens-entry name back to the lens-file prefix it belongs to.
            # Lens entries can be named "<file>" or "<file>-<variant>"; the
            # file prefix is the longest known prefix that's a member of
            # PREFIXES.
            name = src[len("lens:"):]
            for prefix in PREFIXES:
                if name == prefix or name.startswith(prefix + "-"):
                    by_prefix[prefix].append(node)
                    break
    return by_prefix


@pytest.mark.parametrize("prefix", PREFIXES)
def test_lens_fires_at_least_once(prefix, nodes_by_lens):
    if prefix in XFAIL_PREFIXES:
        pytest.xfail(f"lens {prefix} known-broken under fixture; see PHASE3_FIXTURE_COVERAGE.md")
    nodes = nodes_by_lens.get(prefix, [])
    assert nodes, (
        f"lens '{prefix}' did not emit any node when indexing "
        f"fixtures/lens-coverage-workspace. Check the lens regex/strategy "
        f"against the fixture source for that framework."
    )
