from __future__ import annotations

from typing import Any


class ConfigError(ValueError):
    pass


def require_dict(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{path} must be an object")
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ConfigError(f"{path} must be a list")
    return value


def require_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{path} must be a non-empty string")
    return value


def validate_pack_config(config: dict[str, Any], *, name: str = "pack", partial: bool = False) -> None:
    require_dict(config, name)
    for section_name, section in config.items():
        if section_name == "message_buses":
            require_list(section, f"{name}.{section_name}")
            continue
        require_dict(section, f"{name}.{section_name}")
    rest = config.get("rest")
    if rest:
        if "controller_annotations" in rest or not partial:
            require_list(rest.get("controller_annotations", []), f"{name}.rest.controller_annotations")
        if "base_mapping_annotation" in rest or not partial:
            require_string(
                rest.get("base_mapping_annotation", "@RequestMapping"), f"{name}.rest.base_mapping_annotation"
            )
        if "method_mappings" in rest or not partial:
            methods = require_dict(rest.get("method_mappings", {}), f"{name}.rest.method_mappings")
            for key, value in methods.items():
                require_string(key, f"{name}.rest.method_mappings key")
                require_string(value, f"{name}.rest.method_mappings.{key}")
    kafka = config.get("kafka")
    if kafka:
        if "listener_annotation" in kafka or not partial:
            require_string(kafka.get("listener_annotation", "@KafkaListener"), f"{name}.kafka.listener_annotation")
        if "producer_methods" in kafka or not partial:
            require_list(kafka.get("producer_methods", []), f"{name}.kafka.producer_methods")
        if "config_annotation" in kafka or not partial:
            require_string(kafka.get("config_annotation", "@Value"), f"{name}.kafka.config_annotation")
    message_buses = config.get("message_buses")
    if message_buses:
        for idx, bus in enumerate(require_list(message_buses, f"{name}.message_buses")):
            bus_path = f"{name}.message_buses[{idx}]"
            require_dict(bus, bus_path)
            require_string(bus.get("name"), f"{bus_path}.name")
            for key in [
                "listener_annotation",
                "config_annotation",
                "producer_label",
                "consumer_label",
                "consumer_class_label",
                "handler_edge",
                "delivery_edge",
                "source",
                "config_source",
            ]:
                if key in bus or not partial:
                    require_string(bus.get(key), f"{bus_path}.{key}")
            if "producer_methods" in bus or not partial:
                require_list(bus.get("producer_methods", []), f"{bus_path}.producer_methods")
    gateway = config.get("gateway")
    if gateway:
        if "uri_prefix" in gateway or not partial:
            require_string(gateway.get("uri_prefix", "lb://"), f"{name}.gateway.uri_prefix")
        if "path_predicate" in gateway or not partial:
            require_string(gateway.get("path_predicate", "Path"), f"{name}.gateway.path_predicate")
        if "strip_prefix_filter" in gateway or not partial:
            require_string(gateway.get("strip_prefix_filter", "StripPrefix"), f"{name}.gateway.strip_prefix_filter")
    http = config.get("http_clients")
    if http:
        if "tokens" in http or not partial:
            require_list(http.get("tokens", []), f"{name}.http_clients.tokens")
        if "webclient_token" in http or (not partial and "rest" in config):
            require_string(http.get("webclient_token", ""), f"{name}.http_clients.webclient_token")
    express = config.get("express")
    if express:
        if "app_tokens" in express or not partial:
            require_list(express.get("app_tokens", []), f"{name}.express.app_tokens")
        if "route_receivers" in express or not partial:
            require_list(express.get("route_receivers", []), f"{name}.express.route_receivers")
        if "methods" in express or not partial:
            require_list(express.get("methods", []), f"{name}.express.methods")
        if "mount_method" in express or not partial:
            require_string(express.get("mount_method", ""), f"{name}.express.mount_method")
    kafkajs = config.get("kafkajs")
    if kafkajs:
        if "producer_token" in kafkajs or not partial:
            require_string(kafkajs.get("producer_token", ""), f"{name}.kafkajs.producer_token")
        if "consumer_token" in kafkajs or not partial:
            require_string(kafkajs.get("consumer_token", ""), f"{name}.kafkajs.consumer_token")
    react = config.get("react")
    if react and ("component_name_pattern" in react or not partial):
        require_string(react.get("component_name_pattern", ""), f"{name}.react.component_name_pattern")
    struts = config.get("struts")
    if struts:
        for key in ("framework", "action_label", "source", "action_extension", "default_http_method"):
            if key in struts or not partial:
                require_string(struts.get(key, ""), f"{name}.struts.{key}")
    j2ee = config.get("j2ee")
    if j2ee:
        for key in ("servlet_label", "source", "default_http_method"):
            if key in j2ee or not partial:
                require_string(j2ee.get(key, ""), f"{name}.j2ee.{key}")
    database = config.get("database")
    if database:
        for key in ("query_label", "mapper_source", "sql_source"):
            if key in database or not partial:
                require_string(database.get(key, ""), f"{name}.database.{key}")


def validate_view_specs(specs: dict[str, Any], *, name: str = "views") -> None:
    require_dict(specs, name)
    for view_name, view in specs.items():
        require_dict(view, f"{name}.{view_name}")
        kind = require_string(view.get("kind"), f"{name}.{view_name}.kind")
        if kind not in {"nodes", "edges", "group_edges"}:
            raise ConfigError(f"{name}.{view_name}.kind must be one of nodes, edges, group_edges")
        if kind == "nodes":
            if "label" in view:
                require_string(view["label"], f"{name}.{view_name}.label")
        if kind in {"edges", "group_edges"} and "edge_type" in view:
            require_string(view["edge_type"], f"{name}.{view_name}.edge_type")
        if "where" in view:
            require_dict(view["where"], f"{name}.{view_name}.where")
        if "sort" in view:
            require_list(view["sort"], f"{name}.{view_name}.sort")
        if kind == "group_edges":
            group_by = require_dict(view.get("group_by"), f"{name}.{view_name}.group_by")
            validate_side_property(group_by, f"{name}.{view_name}.group_by")
            fields = require_dict(view.get("fields"), f"{name}.{view_name}.fields")
            for field_name, spec in fields.items():
                require_dict(spec, f"{name}.{view_name}.fields.{field_name}")
                validate_side_property(spec, f"{name}.{view_name}.fields.{field_name}")


def validate_lens_specs(specs: dict[str, Any], *, name: str = "lenses") -> None:
    require_dict(specs, name)
    for lens_name, spec in specs.items():
        require_dict(spec, f"{name}.{lens_name}")
        kind = require_string(spec.get("kind"), f"{name}.{lens_name}.kind")
        if kind != "query":
            raise ConfigError(f"{name}.{lens_name}.kind must be query")
        query = spec.get("query")
        if isinstance(query, str):
            require_string(query, f"{name}.{lens_name}.query")
        else:
            lines = require_list(query, f"{name}.{lens_name}.query")
            if not lines:
                raise ConfigError(f"{name}.{lens_name}.query must not be empty")
            for idx, line in enumerate(lines):
                require_string(line, f"{name}.{lens_name}.query[{idx}]")
        language = spec.get("language", "kuzu-cypher")
        if language != "kuzu-cypher":
            raise ConfigError(f"{name}.{lens_name}.language must be kuzu-cypher")
        if "returns" in spec:
            returns = require_dict(spec["returns"], f"{name}.{lens_name}.returns")
            for var, type_name in returns.items():
                require_string(var, f"{name}.{lens_name}.returns key")
                require_string(type_name, f"{name}.{lens_name}.returns.{var}")
        if "params" in spec:
            require_dict(spec["params"], f"{name}.{lens_name}.params")


def validate_side_property(spec: dict[str, Any], path: str) -> None:
    side = require_string(spec.get("side"), f"{path}.side")
    if side not in {"from", "to"}:
        raise ConfigError(f"{path}.side must be from or to")
    require_string(spec.get("property"), f"{path}.property")
