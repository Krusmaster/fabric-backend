"""The Claude plugin in plugin/krusgraph: manifest, server reference, skill and command frontmatter, README, and that
the tools the skill names exist on the server."""
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugin" / "krusgraph"


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    head, _, body = text[4:].partition("\n---\n")
    assert body.strip(), path
    data = {}
    for line in head.splitlines():                       # the plugin's frontmatter is flat `key: value` lines; no YAML library in CI
        key, sep, value = line.partition(":")
        assert sep and key.strip(), (path, line)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        data[key.strip()] = value
    return data


def test_manifest_is_valid_json_with_the_fields_the_directory_reads():
    m = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert m["name"] == "krusgraph" and re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", m["name"])
    assert not re.match(r"(claude|anthropic|anthropics|cc-plugin)-", m["name"]) and "claude" not in m["name"]
    for key in ("version", "description", "author", "homepage", "license"):
        assert m.get(key), key
    assert m["author"]["name"] == "Kruse Consulting AB" and m["author"]["url"] == "https://krusgraph.com"
    assert urlsplit(m["homepage"]).scheme == "https" and m["homepage"].startswith("https://krusgraph.com")
    assert m["license"] == "MIT" and m["privacyPolicyUrl"] == "https://krusgraph.com/privacy"
    # where a user gets help: the issue tracker, not /support (the page about supporting the project, a concept for now)
    assert m["supportUrl"] == "https://github.com/Krusmaster/fabric-backend/issues"
    assert re.fullmatch(r"\d+\.\d+\.\d+", m["version"])
    assert len(m["description"]) >= 40
    unknown = set(m) - {"$schema", "name", "displayName", "version", "description", "author", "homepage", "repository", "license",
                        "keywords", "metadata", "icon", "documentationUrl", "supportUrl", "privacyPolicyUrl", "termsOfServiceUrl",
                        "defaultEnabled", "dependencies", "settings", "userConfig", "skills", "commands", "agents", "hooks",
                        "mcpServers", "lspServers", "outputStyles", "workflows", "experimental"}
    assert not unknown, unknown


def test_mcp_json_points_at_the_hosted_server_without_secrets():
    cfg = json.loads((PLUGIN / ".mcp.json").read_text(encoding="utf-8"))
    server = cfg["mcpServers"]["krusgraph"]
    assert server == {"type": "http", "url": "https://krusgraph.com/mcp"}
    registry = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert server["url"] == registry["remotes"][0]["url"]                      # one URL: plugin and connector share the tools
    assert "headers" not in server and "env" not in server


def test_skill_and_commands_have_the_frontmatter_claude_reads():
    skill = frontmatter(PLUGIN / "skills" / "fabric-graph-backend" / "SKILL.md")
    assert skill["name"] == "fabric-graph-backend" and len(skill["description"]) > 60 and "Fabric" in skill["description"]
    commands = {p.stem: frontmatter(p) for p in (PLUGIN / "commands").glob("*.md")}
    assert set(commands) == {"plan", "document", "explain-schema"}
    for name, fm in commands.items():
        assert fm["description"] and fm["argument-hint"].startswith("["), name


def test_skill_names_only_tools_the_server_defines_and_says_when_to_confirm():
    from fabric_backend import server
    defined = {m.group(1) for m in re.finditer(r"^def (\w+)\(", open(server.__file__).read(), re.M)}
    text = (PLUGIN / "skills" / "fabric-graph-backend" / "SKILL.md").read_text(encoding="utf-8")
    for p in (PLUGIN / "commands").glob("*.md"):
        text += p.read_text(encoding="utf-8")
    named = set(re.findall(r"`([a-z_]+)\(", text)) | set(re.findall(r"`([a-z_]+)`", text))
    tools = {n for n in named if n in {"list_workspaces", "list_sources", "list_tables", "plan_backend", "sample_rows", "validate_plan",
                                       "create_backend", "describe_backend", "query_graphql", "rayfin_connector", "ontology_draft",
                                       "semantic_model_draft", "join_path", "data_dictionary", "dbt_schema", "plan_drift", "create_semantic_model",
                                       "create_views", "create_data_agent", "app_starter", "app_readiness", "analyze_schema", "suggest_relationships", "create_ontology", "lineage"}}
    assert {"plan_backend", "validate_plan", "sample_rows", "suggest_relationships", "plan_drift", "create_backend", "describe_backend",
            "query_graphql", "semantic_model_draft", "data_dictionary", "dbt_schema", "analyze_schema", "join_path", "app_readiness"} <= tools
    assert tools <= defined
    assert "go-ahead" in text and "confirmed" in text and "dry_run" in text


def test_readme_is_long_enough_for_the_directory_and_the_bundle_has_no_executables():
    words = re.sub(r"```.*?```", "", (PLUGIN / "README.md").read_text(encoding="utf-8"), flags=re.S).split()
    assert len(words) >= 40 and "Microsoft Entra" in " ".join(words)
    assert not (PLUGIN / "bin").exists() and not (PLUGIN / "CLAUDE.md").exists()
    everything = "".join(p.read_text(encoding="utf-8") for p in PLUGIN.rglob("*") if p.is_file())
    assert not re.search(r"(secret|token)\s*[:=]\s*['\"][A-Za-z0-9~._-]{16,}", everything, re.I)
