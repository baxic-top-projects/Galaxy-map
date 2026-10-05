#!/usr/bin/env python3
"""Migrate all running Docker containers on this host into k3s Deployments.

One namespace per compose project (keeps short DNS names like redis/kafka).
Published ports become hostPort. Bind/named volumes become hostPath.

  sudo python3 migrate_all_docker.py --node-name worker-146 --import-images --stop-docker --apply
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def run(cmd, check=True):
    return subprocess.run(cmd, check=check, text=True, capture_output=True)


def sh(cmd: str) -> str:
    return run(["bash", "-lc", cmd]).stdout.strip()


def sanitize(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return (name[:63] or "app")


def volume_mountpoint(name: str) -> str | None:
    try:
        return sh(f"docker volume inspect -f '{{{{.Mountpoint}}}}' {name}")
    except Exception:
        return None


def resolve_image(cid: str) -> str:
    img = sh(f"docker inspect -f '{{{{.Config.Image}}}}' {cid}")
    if not img.startswith("sha256:"):
        return img
    try:
        tagged = sh(
            "docker image inspect --format '{{index .RepoTags 0}}' "
            f"$(docker inspect -f '{{{{.Image}}}}' {cid})"
        )
        if tagged and tagged != "<no value>":
            return tagged
    except Exception:
        pass
    return img


def container_objs(cid: str, node_name: str):
    info = json.loads(run(["docker", "inspect", cid]).stdout)[0]
    name = info["Name"].lstrip("/")
    labels = info["Config"].get("Labels") or {}
    project = labels.get("com.docker.compose.project") or "standalone"
    service = labels.get("com.docker.compose.service") or name
    ns = sanitize(project)
    dep = sanitize(f"{service}")
    image = resolve_image(cid)

    env = []
    for e in info["Config"].get("Env") or []:
        if "=" not in e:
            continue
        k, v = e.split("=", 1)
        if k in {"PATH", "HOSTNAME", "HOME"}:
            continue
        env.append({"name": k, "value": v})

    mounts, volumes = [], []
    for i, m in enumerate(info.get("Mounts") or []):
        src, dst = m.get("Source"), m.get("Destination")
        if not src or not dst:
            continue
        if m.get("Type") == "volume":
            mp = volume_mountpoint(m.get("Name") or "")
            if not mp:
                continue
            src = mp
        vname = f"m{i}"
        volumes.append({"name": vname, "hostPath": {"path": src, "type": "DirectoryOrCreate"}})
        mounts.append({"name": vname, "mountPath": dst})

    ports = []
    used_host = set()
    exposed = info.get("NetworkSettings", {}).get("Ports") or {}
    for key, vals in exposed.items():
        cont_port = int(key.split("/")[0])
        if not vals:
            ports.append({"containerPort": cont_port})
            continue
        for b in vals:
            entry = {"containerPort": cont_port}
            hp = int(b.get("HostPort") or 0)
            if hp and hp not in used_host:
                entry["hostPort"] = hp
                used_host.add(hp)
            ports.append(entry)
    if not ports:
        for key in (info["Config"].get("ExposedPorts") or {}):
            ports.append({"containerPort": int(key.split("/")[0])})

    container = {
        "name": "main",
        "image": image,
        "imagePullPolicy": "Never",
        "env": env,
    }
    if ports:
        container["ports"] = ports
    if mounts:
        container["volumeMounts"] = mounts
    entrypoint = info["Config"].get("Entrypoint")
    cmd = info["Config"].get("Cmd")
    if entrypoint:
        container["command"] = entrypoint if isinstance(entrypoint, list) else [entrypoint]
    if cmd:
        container["args"] = cmd if isinstance(cmd, list) else [cmd]

    labels_out = {
        "app": dep,
        "compose.project": ns,
        "compose.service": sanitize(service),
        "migrate.from": "docker",
    }
    pod_spec = {
        "nodeSelector": {"kubernetes.io/hostname": node_name},
        "containers": [container],
    }
    if volumes:
        pod_spec["volumes"] = volumes

    objs = [
        {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": ns},
        },
        {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": dep, "namespace": ns, "labels": labels_out},
            "spec": {
                "replicas": 1,
                "selector": {"matchLabels": {"app": dep}},
                "template": {"metadata": {"labels": labels_out}, "spec": pod_spec},
            },
        },
    ]
    if ports:
        objs.append(
            {
                "apiVersion": "v1",
                "kind": "Service",
                "metadata": {"name": sanitize(service), "namespace": ns, "labels": labels_out},
                "spec": {
                    "selector": {"app": dep},
                    "ports": [
                        {"name": f"p{p['containerPort']}", "port": p["containerPort"], "targetPort": p["containerPort"]}
                        for p in {p["containerPort"]: p for p in ports}.values()
                    ],
                },
            }
        )
    return objs, image, name, ns, dep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--node-name", required=True)
    ap.add_argument("--out", default="/tmp/k3s-migrate-all.yaml")
    ap.add_argument("--kubeconfig", default="")
    ap.add_argument("--import-images", action="store_true")
    ap.add_argument("--stop-docker", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--exclude-regex", default="")
    args = ap.parse_args()

    ids = [x for x in sh("docker ps -q").split() if x]
    if not ids:
        print("no running containers")
        return 0

    try:
        import yaml
    except ImportError:
        run(["apt-get", "update"], check=False)
        run(["apt-get", "install", "-y", "python3-yaml"], check=False)
        import yaml

    all_objs, images, seen_ns = [], [], set()
    # Deduplicate Namespace objects
    final_objs = []
    ns_emitted = set()

    for cid in ids:
        cname = sh(f"docker inspect -f '{{{{.Name}}}}' {cid}").lstrip("/")
        if args.exclude_regex and re.search(args.exclude_regex, cname):
            print(f"skip {cname}")
            continue
        try:
            objs, image, name, ns, dep = container_objs(cid, args.node_name)
        except Exception as exc:
            print(f"FAIL {cname}: {exc}", file=sys.stderr)
            continue
        print(f"map {name} -> {ns}/{dep} image={image}")
        for obj in objs:
            if obj["kind"] == "Namespace":
                if obj["metadata"]["name"] in ns_emitted:
                    continue
                ns_emitted.add(obj["metadata"]["name"])
            final_objs.append(obj)
        if image:
            images.append(image)

    out = Path(args.out)
    with out.open("w", encoding="utf-8") as f:
        for obj in final_objs:
            f.write("---\n")
            yaml.safe_dump(obj, f, sort_keys=False)
    print(f"wrote {out} objects={len(final_objs)}")

    if args.import_images:
        for img in sorted(set(images)):
            print(f"import {img}")
            subprocess.run(f"docker save {img} | k3s ctr images import -", shell=True, check=False)

    if args.stop_docker:
        print("stopping docker containers")
        subprocess.run("docker stop $(docker ps -q)", shell=True, check=False)

    if args.apply:
        env = os.environ.copy()
        kube = args.kubeconfig or "/etc/rancher/k3s/k3s.yaml"
        if Path(kube).exists():
            env["KUBECONFIG"] = kube
        r = subprocess.run(["kubectl", "apply", "-f", str(out)], env=env, text=True, capture_output=True)
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        return r.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
