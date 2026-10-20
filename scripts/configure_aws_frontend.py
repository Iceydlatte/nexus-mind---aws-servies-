"""Write the public Cognito/API settings into the static frontend after stack creation."""

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack-name", default="nexus-mind")
    parser.add_argument("--region", required=True)
    parser.add_argument("--profile", default="nexus-mind")
    args = parser.parse_args()

    result = subprocess.run(
        [
            "aws", "cloudformation", "describe-stacks",
            "--stack-name", args.stack_name,
            "--region", args.region,
            "--profile", args.profile,
            "--query", "Stacks[0].Outputs",
            "--output", "json",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    outputs = {item["OutputKey"]: item["OutputValue"] for item in json.loads(result.stdout)}
    required = {"ApiUrl", "Region", "UserPoolId", "UserPoolClientId"}
    missing = required - outputs.keys()
    if missing:
        raise SystemExit(f"CloudFormation stack is missing outputs: {', '.join(sorted(missing))}")

    config = {
        "enabled": True,
        "region": outputs["Region"],
        "userPoolId": outputs["UserPoolId"],
        "userPoolClientId": outputs["UserPoolClientId"],
        "apiUrl": outputs["ApiUrl"],
    }
    target = ROOT / "frontend" / "aws-config.js"
    target.write_text(
        "// Public AWS app identifiers. Never add passwords, client secrets, or AWS keys here.\n"
        "window.NEXUS_AWS_CONFIG = " + json.dumps(config, indent=2) + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote public app settings to {target}")


if __name__ == "__main__":
    main()
