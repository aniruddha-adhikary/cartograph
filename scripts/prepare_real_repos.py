from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default="fixtures/real-repos.json")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    workspace = Path(manifest["workspace"])
    source_root = workspace.parent / "sources"
    if args.force and workspace.parent.exists():
        shutil.rmtree(workspace.parent)
    workspace.mkdir(parents=True, exist_ok=True)
    source_root.mkdir(parents=True, exist_ok=True)

    for repo in manifest["repos"]:
        checkout = source_root / repo["name"]
        if not checkout.exists():
            subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", repo["ref"], repo["url"], str(checkout)], check=True
            )
        service_paths = []
        for service in repo.get("services", []):
            service_paths.append(checkout / service)
        for pattern in repo.get("service_globs", []):
            service_paths.extend(sorted(checkout.glob(pattern)))
        for service_path in service_paths:
            if not service_path.exists():
                raise FileNotFoundError(f"missing service path {service_path}")
            dest = workspace / service_path.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(
                service_path, dest, ignore=shutil.ignore_patterns(".git", "target", "build", "node_modules")
            )
            cfg = dest / "cartograph.yaml"
            if not cfg.exists():
                cfg.write_text(f"name: {service_path.name}\n", encoding="utf-8")
            print(f"prepared {dest}")

    print(f"workspace ready: {workspace}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
