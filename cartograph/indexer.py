from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from .graph import Graph
from .lenses import persist_lenses

# --- Re-exported from new modules for backward compatibility ---
from .util import (
    slug,
    first_string,
    join_paths,
    split_url,
    infer_http_method,
    xml_attrs,
    xml_tag_value,
    first_xml_attr,
    line_for_offset,
    sql_operation,
    object_string_value,
    struts_action_path,
    gateway_target_path,
    extract_topics,
    extract_group_id,
    extract_message_send_topic,
    collect_string_fields,
    previous_key,
    normalize_path,
    node,
    edge,
)
from .discovery import (
    discover_service_roots,
    looks_like_service,
    service_name,
    service_config,
    parse_config_file,
    parse_simple_yaml,
    parse_scalar,
)
from .pack_loader import (
    load_pack_config,
    normalize_pack_config,
    deep_merge,
    merge_lists,
    unique_paths,
)
from .linkers import (
    run_linkers,
    dedup_call_sites,
    dedup_edges,
    load_service_registry,
    resolve_topic,
    first_endpoint_for_service,
    find_node,
)

CORE_EXCLUDES = [
    "src/test/**",
    "tests/**",
    "__tests__/**",
    "*Tests.java",
    "*.test.js",
    "*.test.ts",
    "*.test.tsx",
    "*.spec.js",
    "*.spec.ts",
    "*.spec.tsx",
    "node_modules/**",
    "target/**",
    "build/**",
    "dist/**",
]

JAVA_EXTS = {".java"}
JS_EXTS = {".js", ".jsx", ".ts", ".tsx"}
YAML_EXTS = {".yml", ".yaml", ".properties"}
XML_EXTS = {".xml", ".jsp", ".jspx", ".tag", ".tld"}
SQL_EXTS = {".sql"}
SOURCE_EXTS = JAVA_EXTS | JS_EXTS | YAML_EXTS | XML_EXTS | SQL_EXTS | {".json"}


@dataclass
class ServiceContext:
    name: str
    root: Path
    graph: Graph
    application_names: set[str]
    packs: dict[str, Any]
    js_packs: dict[str, Any]
    config: dict[str, Any]


def index_workspace(
    workspace: Path,
    registry_path: Path | None = None,
    include_test_paths: bool = False,
    packs_dir: Path | list[Path] | None = None,
) -> Graph:
    workspace = workspace.resolve()
    service_roots = discover_service_roots(workspace)
    spring_pack = load_pack_config("spring", workspace, packs_dir)
    javascript_pack = load_pack_config("javascript", workspace, packs_dir)
    merged = Graph(meta={"version": 1, "workspace": str(workspace), "m1": True})
    service_graphs: list[ServiceContext] = []

    for root in service_roots:
        service = service_name(root)
        config = service_config(root)
        ctx = ServiceContext(
            name=service,
            root=root,
            graph=Graph(meta={"service": service}),
            application_names=set(),
            packs=spring_pack,
            js_packs=javascript_pack,
            config=config,
        )
        index_service(ctx, include_test_paths=include_test_paths or bool(config.get("include_test_paths")))
        dedup_call_sites(ctx.graph)
        service_graphs.append(ctx)
        merged.nodes.extend(ctx.graph.nodes)
        merged.edges.extend(ctx.graph.edges)

    registry = load_service_registry(registry_path or workspace / "service-registry.yaml")
    run_linkers(merged, service_graphs, registry)
    dedup_edges(merged)
    persist_lenses(merged)
    merged.meta["services"] = sorted(
        {node_item["service"] for node_item in merged.nodes if "service" in node_item and node_item["service"] != "cartograph"}
    )
    merged.meta["node_count"] = len(merged.nodes)
    merged.meta["edge_count"] = len(merged.edges)
    return merged


def index_service(ctx: ServiceContext, include_test_paths: bool) -> None:
    for path in sorted(ctx.root.rglob("*")):
        if not path.is_file() or path.suffix not in SOURCE_EXTS:
            continue
        rel = path.relative_to(ctx.root).as_posix()
        if not include_test_paths and excluded(rel, ctx.config.get("exclude", [])):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        language = language_for(path)
        file_node = node(ctx, "File", rel, 1, "pack:file", "high", path=rel, language=language)
        ctx.graph.add_node(file_node)
        if path.suffix in JAVA_EXTS:
            index_java(ctx, rel, text)
        elif path.suffix in JS_EXTS:
            index_js(ctx, rel, text)
        elif path.suffix in YAML_EXTS:
            index_config(ctx, rel, text)
        elif path.suffix in XML_EXTS:
            index_xml(ctx, rel, text)
        elif path.suffix in SQL_EXTS:
            index_sql(ctx, rel, text)


def excluded(rel: str, extra_patterns: list[str] | None = None) -> bool:
    parts = rel.split("/")
    if any(part in {"node_modules", "target", "build", "dist", "__tests__", "tests"} for part in parts):
        return True
    patterns = [*CORE_EXCLUDES, *(extra_patterns or [])]
    return any(fnmatch(rel, pattern) or fnmatch(Path(rel).name, pattern) for pattern in patterns)


def language_for(path: Path) -> str:
    return {
        ".java": "java",
        ".js": "javascript",
        ".jsx": "tsx",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".properties": "properties",
        ".xml": "xml",
        ".jsp": "jsp",
        ".jspx": "jsp",
        ".tag": "jsp",
        ".tld": "xml",
        ".sql": "sql",
        ".json": "json",
    }.get(path.suffix, path.suffix.lstrip("."))


def index_config(ctx: ServiceContext, rel: str, text: str) -> None:
    lines = text.splitlines()
    route_host: str | None = None
    route_path: str | None = None
    route_line: int | None = None
    strip_prefix = 0

    def flush_route() -> None:
        nonlocal route_host, route_path, route_line, strip_prefix
        if route_host and route_path and route_line is not None:
            ctx.graph.add_node(
                node(
                    ctx,
                    "HttpCall",
                    rel,
                    route_line,
                    "pack:spring-cloud-gateway",
                    "medium",
                    http_method="GET",
                    host=route_host,
                    host_var=route_host,
                    path=gateway_target_path(route_path, strip_prefix),
                    file=rel,
                    line=route_line,
                )
            )
        route_host = None
        route_path = None
        route_line = None
        strip_prefix = 0

    for idx, line in enumerate(lines, 1):
        app_name = re.search(r"spring\.application\.name\s*=\s*(.+)", line)
        if app_name:
            ctx.application_names.add(slug(app_name.group(1).strip()))
        direct = re.match(r"\s*name\s*:\s*['\"]?([^'\"]+)['\"]?\s*$", line)
        if direct and previous_key(lines, idx, "application"):
            ctx.application_names.add(slug(direct.group(1).strip()))
        if re.search(r"^\s*-\s*id\s*:", line):
            flush_route()
        gateway = ctx.packs["gateway"]
        uri = re.search(rf"\buri\s*:\s*{re.escape(gateway['uri_prefix'])}([^#\s]+)", line)
        if uri:
            route_host = uri.group(1).strip()
        path_pred = re.search(rf"-\s*{re.escape(gateway['path_predicate'])}\s*=\s*([^#\s]+)", line)
        if path_pred:
            route_path = path_pred.group(1)
            route_line = idx
        strip = re.search(rf"-\s*{re.escape(gateway['strip_prefix_filter'])}\s*=\s*(\d+)", line)
        if strip:
            strip_prefix = int(strip.group(1))
    flush_route()


def index_xml(ctx: ServiceContext, rel: str, text: str) -> None:
    if "struts" in rel.lower() or "<struts" in text or "<struts-config" in text:
        index_struts_xml(ctx, rel, text)
    if "web.xml" in rel.lower() or "<web-app" in text:
        index_web_xml(ctx, rel, text)
    if "<select" in text or "<insert" in text or "<update" in text or "<delete" in text:
        index_sql_mapper_xml(ctx, rel, text)


def index_struts_xml(ctx: ServiceContext, rel: str, text: str) -> None:
    struts = ctx.packs.get("struts", {})
    namespace = first_xml_attr(text, "package", "namespace") or ""
    for match in re.finditer(r"<action\b([^>]*)>", text, flags=re.IGNORECASE):
        attrs = xml_attrs(match.group(1))
        name_value = attrs.get("name") or attrs.get("path")
        if not name_value:
            continue
        path = struts_action_path(namespace, name_value, struts.get("action_extension", ".action"))
        action = node(
            ctx,
            struts.get("action_label", "Action"),
            rel,
            line_for_offset(text, match.start()),
            struts.get("source", "pack:struts-action"),
            "high",
            framework=struts.get("framework", "struts"),
            name=name_value.strip("/"),
            class_name=attrs.get("class") or attrs.get("type"),
            method=attrs.get("method") or attrs.get("parameter"),
            file=rel,
            line=line_for_offset(text, match.start()),
        )
        endpoint = node(
            ctx,
            "Endpoint",
            rel,
            line_for_offset(text, match.start()),
            struts.get("source", "pack:struts-action"),
            "high",
            http_method=struts.get("default_http_method", "GET"),
            path=path,
            handler=action.get("class_name") or action["name"],
            framework=struts.get("framework", "struts"),
            file=rel,
            line=line_for_offset(text, match.start()),
        )
        ctx.graph.add_node(action)
        ctx.graph.add_node(endpoint)
        ctx.graph.add_edge(edge("HANDLES", action, endpoint, "high"))


def index_web_xml(ctx: ServiceContext, rel: str, text: str) -> None:
    j2ee = ctx.packs.get("j2ee", {})
    servlets: dict[str, tuple[str, int]] = {}
    for block in re.finditer(r"<servlet\b.*?</servlet>", text, flags=re.IGNORECASE | re.DOTALL):
        servlet_name = xml_tag_value(block.group(0), "servlet-name")
        servlet_class = xml_tag_value(block.group(0), "servlet-class")
        if servlet_name and servlet_class:
            servlets[servlet_name] = (servlet_class, line_for_offset(text, block.start()))
            ctx.graph.add_node(
                node(
                    ctx,
                    j2ee.get("servlet_label", "Servlet"),
                    rel,
                    line_for_offset(text, block.start()),
                    j2ee.get("source", "pack:j2ee-web"),
                    "high",
                    name=servlet_name,
                    class_name=servlet_class,
                    file=rel,
                    line=line_for_offset(text, block.start()),
                )
            )
    for block in re.finditer(r"<servlet-mapping\b.*?</servlet-mapping>", text, flags=re.IGNORECASE | re.DOTALL):
        servlet_name = xml_tag_value(block.group(0), "servlet-name")
        url_pattern = xml_tag_value(block.group(0), "url-pattern")
        if servlet_name and url_pattern:
            servlet_class, _ = servlets.get(servlet_name, (servlet_name, line_for_offset(text, block.start())))
            endpoint = node(
                ctx,
                "Endpoint",
                rel,
                line_for_offset(text, block.start()),
                j2ee.get("source", "pack:j2ee-web"),
                "high",
                http_method=j2ee.get("default_http_method", "GET"),
                path=url_pattern,
                handler=servlet_class,
                framework="j2ee",
                file=rel,
                line=line_for_offset(text, block.start()),
            )
            ctx.graph.add_node(endpoint)


def index_sql_mapper_xml(ctx: ServiceContext, rel: str, text: str) -> None:
    db = ctx.packs.get("database", {})
    for match in re.finditer(r"<(select|insert|update|delete)\b([^>]*)>", text, flags=re.IGNORECASE):
        attrs = xml_attrs(match.group(2))
        ctx.graph.add_node(
            node(
                ctx,
                db.get("query_label", "DatabaseQuery"),
                rel,
                line_for_offset(text, match.start()),
                db.get("mapper_source", "pack:sql-mapper"),
                "high",
                operation=match.group(1).upper(),
                query_id=attrs.get("id"),
                file=rel,
                line=line_for_offset(text, match.start()),
            )
        )


def index_sql(ctx: ServiceContext, rel: str, text: str) -> None:
    db = ctx.packs.get("database", {})
    for idx, line in enumerate(text.splitlines(), 1):
        operation = sql_operation(line)
        if operation:
            ctx.graph.add_node(
                node(
                    ctx,
                    db.get("query_label", "DatabaseQuery"),
                    rel,
                    idx,
                    db.get("sql_source", "pack:sql"),
                    "medium",
                    operation=operation,
                    file=rel,
                    line=idx,
                )
            )


def index_java(ctx: ServiceContext, rel: str, text: str) -> None:
    lines = text.splitlines()
    class_name = Path(rel).stem
    rest = ctx.packs["rest"]
    rest_controller = any(any(annotation in line for annotation in rest["controller_annotations"]) for line in lines)
    base_path = ""
    string_fields = collect_string_fields(lines)

    for idx, line in enumerate(lines, 1):
        if rest["base_mapping_annotation"] in line and not re.search(
            r"(" + "|".join(rest["method_mappings"]) + r")Mapping", line
        ) and "RequestMethod." not in line and "method =" not in line:
            base_path = first_string(line) or base_path
        class_match = re.search(r"\bclass\s+(\w+)", line)
        if class_match:
            class_name = class_match.group(1)
            if rest_controller:
                ctx.graph.add_node(
                    node(
                        ctx,
                        "Service",
                        rel,
                        idx,
                        "pack:spring-rest-controller",
                        "high",
                        kind="rest-controller",
                        framework="spring",
                        name=class_name,
                        file=rel,
                        line=idx,
                    )
                )

    for idx, line in enumerate(lines, 1):
        mapping = re.search(r"@(" + "|".join(rest["method_mappings"]) + r")Mapping\s*(?:\((.*)\))?", line)
        rm_mapping = None
        if not mapping:
            rm_mapping = re.search(
                r"@RequestMapping\s*\(([^)]*method\s*=\s*RequestMethod\.(\w+)[^)]*)\)", line
            )
        if (mapping or rm_mapping) and rest_controller:
            if mapping:
                method = rest["method_mappings"][mapping.group(1)]
                path = first_string(mapping.group(2) or line) or ""
            else:
                method = rm_mapping.group(2).upper()
                path = first_string(rm_mapping.group(1)) or ""
            handler = next_java_method(lines, idx) or f"{class_name}.handler"
            endpoint = node(
                ctx,
                "Endpoint",
                rel,
                idx,
                "pack:spring-rest-controller",
                "high",
                http_method=method,
                path=join_paths(base_path, path),
                handler=f"{class_name}.{handler}",
                file=rel,
                line=idx,
            )
            ctx.graph.add_node(endpoint)
            service_nodes = [n for n in ctx.graph.nodes if n["label"] == "Service" and n.get("file") == rel]
            if service_nodes:
                ctx.graph.add_edge(edge("HANDLES", service_nodes[-1], endpoint, "high"))

        for bus in ctx.packs.get("message_buses", []):
            value = re.search(rf"{re.escape(bus['config_annotation'])}\s*\(\s*\"\$\{{([^}}:]+)(?::([^}}]+))?}}", line)
            if value:
                ctx.graph.add_node(
                    node(
                        ctx,
                        "ConfigProperty",
                        rel,
                        idx,
                        bus["config_source"],
                        "high",
                        key=value.group(1),
                        default_value=value.group(2),
                        bus=bus["name"],
                        file=rel,
                        line=idx,
                    )
                )

            listener = re.search(rf"{re.escape(bus['listener_annotation'])}\s*\((.*)\)", line)
            if listener:
                topics = extract_topics(listener.group(1))
                consumer_class = node(
                    ctx,
                    bus["consumer_class_label"],
                    rel,
                    idx,
                    bus["source"],
                    "high",
                    name=class_name,
                    bus=bus["name"],
                    file=rel,
                    line=idx,
                )
                consumer = node(
                    ctx,
                    bus["consumer_label"],
                    rel,
                    idx,
                    bus["source"],
                    "high",
                    message_role="consumer",
                    bus=bus["name"],
                    topics=topics,
                    group_id=extract_group_id(listener.group(1)),
                    delivery_edge=bus["delivery_edge"],
                    file=rel,
                    line=idx,
                )
                ctx.graph.add_node(consumer_class)
                ctx.graph.add_node(consumer)
                ctx.graph.add_edge(edge(bus["handler_edge"], consumer_class, consumer, "high"))

            if any(token in line for token in bus["producer_methods"]):
                topic, topic_var = extract_message_send_topic(line, bus["producer_methods"])
                if topic or topic_var:
                    ctx.graph.add_node(
                        node(
                            ctx,
                            bus["producer_label"],
                            rel,
                            idx,
                            bus["source"],
                            "high" if topic else "medium",
                            message_role="producer",
                            bus=bus["name"],
                            topic=topic or f"{{{topic_var}}}",
                            topic_var=topic_var,
                            delivery_edge=bus["delivery_edge"],
                            file=rel,
                            line=idx,
                        )
                    )

        if any(token in line for token in ctx.packs["http_clients"]["tokens"]):
            for url in re.findall(r'"(https?://[^"]+|/[A-Za-z0-9_./{}-]+)"', line):
                host, path = split_url(url)
                source = (
                    "pack:spring-webclient"
                    if ctx.packs["http_clients"]["webclient_token"] in line
                    else "pack:spring-rest-template"
                )
                confidence = "high" if "{" not in url else "medium"
                ctx.graph.add_node(
                    node(
                        ctx,
                        "HttpCall",
                        rel,
                        idx,
                        source,
                        confidence,
                        http_method=infer_http_method(line),
                        host=host,
                        host_var=host,
                        path=path,
                        file=rel,
                        line=idx,
                    )
                )
            concat = re.search(
                rf"{re.escape(ctx.packs['http_clients']['webclient_token'])}\s*(\w+)\s*\+\s*\"([^\"]+)\"", line
            )
            if concat and concat.group(1) in string_fields:
                host, base = split_url(string_fields[concat.group(1)])
                path = join_paths(base, concat.group(2).split("?", 1)[0])
                ctx.graph.add_node(
                    node(
                        ctx,
                        "HttpCall",
                        rel,
                        idx,
                        "pack:spring-webclient",
                        "medium",
                        http_method=infer_http_method(line),
                        host=host,
                        host_var=host,
                        path=path,
                        file=rel,
                        line=idx,
                    )
                )

        operation = sql_operation(first_string(line) or line)
        if operation:
            db = ctx.packs.get("database", {})
            ctx.graph.add_node(
                node(
                    ctx,
                    db.get("query_label", "DatabaseQuery"),
                    rel,
                    idx,
                    db.get("sql_source", "pack:sql"),
                    "medium",
                    operation=operation,
                    file=rel,
                    line=idx,
                )
            )


def index_js(ctx: ServiceContext, rel: str, text: str) -> None:
    lines = text.splitlines()
    express_service_id: str | None = None
    express = ctx.js_packs["express"]
    for idx, line in enumerate(lines, 1):
        if any(token in line for token in express["app_tokens"]):
            kind = "express-app" if express["app_tokens"][0] in line else "express-router"
            service = node(
                ctx,
                "Service",
                rel,
                idx,
                "pack:express-routes",
                "high",
                kind=kind,
                framework="express",
                name=Path(rel).stem,
                file=rel,
                line=idx,
            )
            ctx.graph.add_node(service)
            express_service_id = service["id"]

        route = re.search(
            r"\b("
            + "|".join(express["route_receivers"])
            + r")\.("
            + "|".join(express["methods"])
            + r")\s*\(\s*['\"]([^'\"]+)['\"]",
            line,
        )
        if route:
            endpoint = node(
                ctx,
                "Endpoint",
                rel,
                idx,
                "pack:express-routes",
                "high",
                http_method=route.group(2).upper(),
                path=route.group(3),
                handler=f"{Path(rel).stem}:line{idx}",
                file=rel,
                line=idx,
            )
            ctx.graph.add_node(endpoint)
            service_node = find_node(ctx.graph, express_service_id) if express_service_id else None
            if service_node:
                ctx.graph.add_edge(edge("HANDLES", service_node, endpoint, "high"))

        mount = re.search(
            rf"\bapp\.{re.escape(express['mount_method'])}\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*(\w+|require\([^)]*\))",
            line,
        )
        if mount:
            ctx.graph.add_node(
                node(
                    ctx,
                    "RouterMount",
                    rel,
                    idx,
                    "pack:express-routes",
                    "high",
                    prefix=mount.group(1),
                    router_var=mount.group(2),
                    file=rel,
                    line=idx,
                )
            )

        if ctx.js_packs["kafkajs"]["producer_token"] in line:
            topic = object_string_value(line, "topic")
            if topic:
                ctx.graph.add_node(
                    node(
                        ctx,
                        "KafkaProducer",
                        rel,
                        idx,
                        "pack:kafkajs",
                        "high",
                        message_role="producer",
                        bus="kafka",
                        topic=topic,
                        topic_var=None,
                        delivery_edge="KAFKA_DELIVERS",
                        file=rel,
                        line=idx,
                    )
                )
        if ctx.js_packs["kafkajs"]["consumer_token"] in line:
            topic = object_string_value(line, "topic")
            if topic:
                ctx.graph.add_node(
                    node(
                        ctx,
                        "KafkaConsumer",
                        rel,
                        idx,
                        "pack:kafkajs",
                        "high",
                        message_role="consumer",
                        bus="kafka",
                        topics=[topic],
                        group_id=None,
                        delivery_edge="KAFKA_DELIVERS",
                        file=rel,
                        line=idx,
                    )
                )

        if any(token in line for token in ctx.js_packs["http_clients"]["tokens"]):
            for url in re.findall(r"[`'\"]([^`'\"]+)['\"`]", line):
                if url.startswith(("http", "/")) or "${" in url:
                    host, path = split_url(url)
                    ctx.graph.add_node(
                        node(
                            ctx,
                            "HttpCall",
                            rel,
                            idx,
                            "pack:js-fetch-hosted",
                            "high" if host else "medium",
                            http_method=infer_http_method(line),
                            host=host,
                            host_var=host,
                            path=path,
                            file=rel,
                            line=idx,
                        )
                    )

        component = re.search(
            r"(?:function\s+([A-Z]\w+)|const\s+([A-Z]\w+)\s*=|class\s+([A-Z]\w+)\s+extends\s+React\.Component)", line
        )
        if component:
            name = next(g for g in component.groups() if g)
            ctx.graph.add_node(
                node(
                    ctx,
                    "Component",
                    rel,
                    idx,
                    "pack:react-components",
                    "high",
                    name=name,
                    kind="react-component",
                    file=rel,
                    line=idx,
                )
            )


def next_java_method(lines: list[str], start: int) -> str | None:
    for line in lines[start : min(start + 8, len(lines))]:
        m = re.search(r"\b(?:public|private|protected)?\s*(?:[\w<>?,\s]+)\s+(\w+)\s*\(", line)
        if m and m.group(1) not in {"if", "for", "while", "switch"}:
            return m.group(1)
    return None
