from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .graph import Graph, edge_key
from .lenses import persist_lenses
from .schema import validate_pack_config

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
        {node["service"] for node in merged.nodes if "service" in node and node["service"] != "cartograph"}
    )
    merged.meta["node_count"] = len(merged.nodes)
    merged.meta["edge_count"] = len(merged.edges)
    return merged


def discover_service_roots(workspace: Path) -> list[Path]:
    children = [p for p in sorted(workspace.iterdir()) if p.is_dir() and not p.name.startswith(".")]
    service_children = [p for p in children if looks_like_service(p)]
    if service_children:
        return service_children
    return [workspace]


def load_pack_config(name: str, workspace: Path, packs_dir: Path | list[Path] | None = None) -> dict[str, Any]:
    bundled = json.loads(resources.files("cartograph").joinpath(f"packs/{name}.json").read_text(encoding="utf-8"))
    validate_pack_config(bundled, name=f"bundled:{name}")
    candidates: list[Path] = []
    pack_dirs_value = [packs_dir] if isinstance(packs_dir, Path) else packs_dir or []
    candidates.append(workspace / ".cartograph" / "packs" / f"{name}.json")
    for item in pack_dirs_value:
        candidates.append(item / f"{name}.json")
    candidates = unique_paths(candidates)
    for path in candidates:
        if path.exists():
            overlay = json.loads(path.read_text(encoding="utf-8"))
            validate_pack_config(overlay, name=str(path), partial=True)
            bundled = deep_merge(bundled, overlay)
            validate_pack_config(bundled, name=f"merged:{name}")
    return normalize_pack_config(bundled)


def normalize_pack_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(config)
    if "kafka" in normalized:
        kafka = normalized["kafka"]
        kafka_bus = {
            "name": "kafka",
            "listener_annotation": kafka.get("listener_annotation", "@KafkaListener"),
            "producer_methods": kafka.get("producer_methods", [".send("]),
            "config_annotation": kafka.get("config_annotation", "@Value"),
            "producer_label": "KafkaProducer",
            "consumer_label": "KafkaConsumer",
            "consumer_class_label": "KafkaConsumerClass",
            "handler_edge": "HANDLES_KAFKA",
            "delivery_edge": "KAFKA_DELIVERS",
            "source": "pack:spring-kafka",
            "config_source": "pack:spring-kafka-config",
        }
        buses = [bus for bus in normalized.get("message_buses", []) if bus.get("name") != "kafka"]
        normalized["message_buses"] = [*buses, kafka_bus]
    return normalized


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        elif isinstance(value, list) and isinstance(merged.get(key), list):
            merged[key] = merge_lists(merged[key], value)
        else:
            merged[key] = value
    return merged


def merge_lists(base: list[Any], overlay: list[Any]) -> list[Any]:
    if all(isinstance(item, dict) and "name" in item for item in [*base, *overlay]):
        by_name = {item["name"]: dict(item) for item in base}
        order = [item["name"] for item in base]
        for item in overlay:
            item_name = item["name"]
            if item_name in by_name:
                by_name[item_name] = deep_merge(by_name[item_name], item)
            else:
                order.append(item_name)
                by_name[item_name] = dict(item)
        return [by_name[item_name] for item_name in order]
    merged = list(base)
    for item in overlay:
        if item not in merged:
            merged.append(item)
    return merged


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def looks_like_service(path: Path) -> bool:
    if (path / "cartograph.yaml").exists() or (path / "package.json").exists() or (path / "pom.xml").exists():
        return True
    return any(p.suffix in SOURCE_EXTS for p in path.rglob("*") if p.is_file())


def service_name(root: Path) -> str:
    name = service_config(root).get("name")
    if name:
        return slug(str(name))
    pkg = root / "package.json"
    if pkg.exists():
        try:
            name = json.loads(pkg.read_text(encoding="utf-8")).get("name")
            if name:
                return slug(str(name).split("/")[-1])
        except json.JSONDecodeError:
            pass
    return slug(root.name)


def service_config(root: Path) -> dict[str, Any]:
    cfg = root / "cartograph.yaml"
    result: dict[str, Any] = {"exclude": []}
    if cfg.exists():
        parsed = parse_config_file(cfg)
        result.update(parsed)
        excludes: list[str] = []
        for key in ("exclude", "excludes", "additional_excludes"):
            value = parsed.get(key)
            if isinstance(value, list):
                excludes.extend(str(item) for item in value)
            elif isinstance(value, str):
                excludes.append(value)
        result["exclude"] = excludes
    return result


def parse_config_file(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    return parse_simple_yaml(text)


def parse_simple_yaml(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any] | list[Any], dict[str, Any] | None, str | None]] = [(-1, root, None, None)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1]
        if line.startswith("- "):
            if not isinstance(container, list):
                parent = stack[-1][2]
                key = stack[-1][3]
                if isinstance(parent, dict) and key:
                    parent[key] = []
                    container = parent[key]
                    stack[-1] = (stack[-1][0], container, parent, key)
            if isinstance(container, list):
                container.append(parse_scalar(line[2:].strip()))
            continue
        if ":" not in line or not isinstance(container, dict):
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value:
            container[key] = parse_scalar(value)
            continue
        container[key] = {}
        stack.append((indent, container[key], container, key))
    return root


def parse_scalar(value: str) -> Any:
    value = value.strip().strip("'\"")
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.startswith("[") and value.endswith("]"):
        return [parse_scalar(item.strip()) for item in value[1:-1].split(",") if item.strip()]
    return value


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
        ):
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
        if mapping and rest_controller:
            method = rest["method_mappings"][mapping.group(1)]
            path = first_string(mapping.group(2) or line) or ""
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


def run_linkers(graph: Graph, services: list[ServiceContext], registry: dict[str, str]) -> None:
    endpoint_by_service_path: dict[tuple[str, str], dict[str, Any]] = {}
    app_name_to_service: dict[str, str] = {}
    topic_consumers: dict[tuple[str, str], list[dict[str, Any]]] = {}
    config_defaults: dict[tuple[str, str], str] = {}

    for ctx in services:
        app_name_to_service[slug(ctx.name)] = ctx.name
        for app_name in ctx.application_names:
            app_name_to_service[slug(app_name)] = ctx.name

    for node_item in graph.nodes:
        if node_item["label"] == "Endpoint":
            endpoint_by_service_path[(node_item["service"], normalize_path(node_item.get("path", "")))] = node_item
        elif node_item.get("message_role") == "consumer":
            for topic in node_item.get("topics", []):
                topic_consumers.setdefault((node_item.get("bus", "default"), topic), []).append(node_item)
        elif node_item["label"] == "ConfigProperty" and node_item.get("default_value"):
            config_defaults[(node_item["service"], node_item["key"])] = node_item["default_value"]

    for producer in [n for n in graph.nodes if n.get("message_role") == "producer"]:
        topic = resolve_topic(producer, config_defaults)
        for consumer in topic_consumers.get((producer.get("bus", "default"), topic), []):
            if producer["service"] != consumer["service"]:
                graph.add_edge(
                    edge(
                        producer.get("delivery_edge", "MESSAGE_DELIVERS"),
                        producer,
                        consumer,
                        "high" if not producer.get("topic_var") else "medium",
                    )
                )

    for call in [n for n in graph.nodes if n["label"] == "HttpCall"]:
        host = slug(str(call.get("host") or call.get("host_var") or ""))
        target_service = registry.get(host) or app_name_to_service.get(host)
        if not target_service:
            continue
        endpoint = endpoint_by_service_path.get((target_service, normalize_path(call.get("path", ""))))
        if not endpoint:
            endpoint = first_endpoint_for_service(graph, target_service)
        if endpoint and call["service"] != endpoint["service"]:
            confidence = "high" if host in registry else "medium"
            graph.add_edge(edge("CROSSES_TIER", call, endpoint, confidence))


def dedup_call_sites(graph: Graph) -> None:
    seen: dict[tuple[Any, ...], dict[str, Any]] = {}
    kept: list[dict[str, Any]] = []
    removed_ids: set[str] = set()
    for n in graph.nodes:
        if n.get("message_role") == "producer" or n["label"] == "HttpCall":
            key = (
                n["label"],
                n["service"],
                n.get("file"),
                n.get("line"),
                n.get("topic") or n.get("topic_var") or n.get("path"),
            )
            if key in seen:
                seen[key]["duplicate_count"] = seen[key].get("duplicate_count", 1) + 1
                removed_ids.add(n["id"])
                continue
            seen[key] = n
        kept.append(n)
    graph.nodes = kept
    graph.edges = [e for e in graph.edges if e["from"] not in removed_ids and e["to"] not in removed_ids]


def dedup_edges(graph: Graph) -> None:
    seen: set[tuple[str, str, str]] = set()
    kept: list[dict[str, Any]] = []
    for item in graph.edges:
        key = edge_key(item)
        if key not in seen:
            seen.add(key)
            kept.append(item)
    graph.edges = kept


def load_service_registry(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    registry: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*([^:#]+)\s*:\s*([^#]+)", line)
        if m:
            registry[slug(m.group(1).strip())] = slug(m.group(2).strip())
    return registry


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


def first_string(text: str | None) -> str | None:
    if not text:
        return None
    m = re.search(r'"([^"]+)"|\'([^\']+)\'', text)
    return next((g for g in m.groups() if g), None) if m else None


def next_java_method(lines: list[str], start: int) -> str | None:
    for line in lines[start : min(start + 8, len(lines))]:
        m = re.search(r"\b(?:public|private|protected)?\s*(?:[\w<>?,\s]+)\s+(\w+)\s*\(", line)
        if m and m.group(1) not in {"if", "for", "while", "switch"}:
            return m.group(1)
    return None


def join_paths(base: str, child: str) -> str:
    if not base and not child:
        return "/"
    return "/" + "/".join(part.strip("/") for part in (base, child) if part and part != "/")


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    path = re.sub(r"\{[^}]+}", "{}", path)
    return "/" + path.strip("/")


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


def first_xml_attr(text: str, tag: str, attr: str) -> str | None:
    match = re.search(rf"<{re.escape(tag)}\b([^>]*)>", text, flags=re.IGNORECASE)
    if not match:
        return None
    return xml_attrs(match.group(1)).get(attr)


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


def struts_action_path(namespace: str, name: str, extension: str) -> str:
    action = name.strip()
    if action.startswith("/"):
        base = action
    else:
        base = join_paths(namespace, action)
    if extension and not base.endswith(extension):
        base += extension
    return base


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


def previous_key(lines: list[str], idx: int, key: str) -> bool:
    start = max(0, idx - 4)
    return any(re.match(rf"\s*{re.escape(key)}\s*:", line) for line in lines[start:idx])


def collect_string_fields(lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in lines:
        m = re.search(r"\b(?:private|protected|public)?\s*(?:final\s+)?String\s+(\w+)\s*=\s*\"([^\"]+)\"", line)
        if m:
            fields[m.group(1)] = m.group(2)
    return fields


def gateway_target_path(path_pattern: str, strip_prefix: int = 0) -> str:
    path = path_pattern.split(",", 1)[0].strip()
    path = re.sub(r"\*\*$", "", path).rstrip("/")
    parts = [part for part in path.split("/") if part]
    if strip_prefix:
        parts = parts[strip_prefix:]
    return "/" + "/".join(parts) if parts else "/"


def resolve_topic(producer: dict[str, Any], config_defaults: dict[tuple[str, str], str]) -> str:
    topic = producer.get("topic")
    if topic and not (topic.startswith("{") and topic.endswith("}")):
        return topic
    topic_var = producer.get("topic_var")
    if topic_var:
        for (service, key), value in config_defaults.items():
            if service == producer["service"] and key.endswith(topic_var):
                return value
    return topic or "{unknown}"


def first_endpoint_for_service(graph: Graph, service: str) -> dict[str, Any] | None:
    for item in graph.nodes:
        if item["label"] == "Endpoint" and item["service"] == service:
            return item
    return None


def find_node(graph: Graph, node_id: str | None) -> dict[str, Any] | None:
    if not node_id:
        return None
    for item in graph.nodes:
        if item["id"] == node_id:
            return item
    return None


def slug(value: str) -> str:
    value = value.strip().strip("'\"")
    value = value.replace("_", "-").lower()
    value = re.sub(r"^https?://", "", value)
    value = value.split("/")[0]
    return value
