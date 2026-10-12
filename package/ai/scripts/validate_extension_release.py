"""Fail before packaging if the Server and its same-version AI disagree."""
import argparse
import ast
import json
import re
import tomllib
from pathlib import Path


def literal_constant(path, name):
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"Missing {name} in {path}")


def validate_versions(root, tag=None):
    def project(path):
        return tomllib.loads((root / path).read_text(encoding="utf-8"))["project"]["version"]
    server = project("package/server/pyproject.toml")
    versions = {
        "AI project": project("package/ai/pyproject.toml"),
        "Server runtime": literal_constant(root / "package/server/app/core/config_manager.py", "VERSION"),
        "Desktop": tomllib.loads((root / "package/desktop/src-tauri/Cargo.toml").read_text(encoding="utf-8"))["package"]["version"],
        "Bundled catalog": json.loads((root / "package/desktop/src-tauri/resources/ai-extensions.json").read_text(encoding="utf-8"))["extensions"][0]["version"],
    }
    app = ast.parse((root / "package/ai/desktop_app.py").read_text(encoding="utf-8"))
    versions["AI runtime"] = next(ast.literal_eval(k.value) for n in ast.walk(app)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "FastAPI"
        for k in n.keywords if k.arg == "version")
    if tag and tag.startswith("v"):
        versions["Release tag"] = tag[1:]
    for name, value in {"Server": server, **versions}.items():
        if not re.fullmatch(r"\d+\.\d+\.\d+", value) or value != server:
            raise ValueError(f"{name} version {value} does not match Server {server}")
    minimum = literal_constant(root / "package/server/app/service/ai_extension_state.py", "MINIMUM_AI_EXTENSION_VERSION")
    if not re.fullmatch(r"\d+\.\d+\.\d+", minimum) or tuple(map(int, minimum.split("."))) > tuple(map(int, server.split("."))):
        raise ValueError("AI minimum version must be a valid version at or below Server")
    return server, minimum


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag")
    parser.add_argument("--github-env", type=Path)
    args = parser.parse_args()
    version, minimum = validate_versions(Path(__file__).resolve().parents[3], args.tag)
    if args.github_env:
        with args.github_env.open("a", encoding="utf-8") as output:
            output.write(f"EXTENSION_VERSION={version}\n")
    print(f"Server/AI {version}; minimum supported AI {minimum}")


if __name__ == "__main__":
    main()
