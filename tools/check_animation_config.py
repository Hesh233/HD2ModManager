"""Fail closed on animation configuration drift before build or packaging."""
from pathlib import Path
import argparse
import hashlib
import json
import tomllib


def check(source_config, bundle_root):
    source_config, bundle_root = Path(source_config), Path(bundle_root)
    raw = source_config.read_bytes()
    bundled = (bundle_root / "config.toml").read_bytes()
    if raw != bundled:
        raise ValueError("Animation config drift: preserve the actual manager-root config; synchronize the bundled copy, never overwrite root with defaults.")
    info = json.loads((bundle_root / "build-info.json").read_text(encoding="utf-8-sig"))
    rows = [row for row in info["files"] if row["name"] == "config.toml"]
    digest = hashlib.sha256(raw).hexdigest()
    if len(rows) != 1 or rows[0]["sha256"].lower() != digest:
        raise ValueError("Animation build-info config.toml hash is missing, duplicated or stale.")
    config = tomllib.loads(raw.decode("utf-8-sig"))
    return {"status": "PASS", "configSha256": digest,
            "singleRotationCompensation": config.get("single_skeleton", {}).get("rotation_compensation"),
            "handTargetMultipliers": {side: config.get("ik_chains", {}).get(side, {}).get("target_multiplier") for side in ("l_hand", "r_hand")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manager-root", type=Path)
    parser.add_argument("--source-config", type=Path)
    parser.add_argument("--bundle-root", type=Path)
    args = parser.parse_args()
    if args.manager_root:
        if args.source_config or args.bundle_root:
            parser.error("Use --manager-root OR --source-config with --bundle-root")
        source, bundle = args.manager_root / "config.toml", args.manager_root / "anim_batch_mod"
    else:
        if not args.source_config or not args.bundle_root:
            parser.error("--source-config and --bundle-root are both required")
        source, bundle = args.source_config, args.bundle_root
    print(json.dumps(check(source, bundle), ensure_ascii=False))


if __name__ == "__main__":
    main()
