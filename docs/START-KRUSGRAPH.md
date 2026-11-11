# Start Krusgraph

The first thing to type after connecting Krusgraph: **`start Krusgraph`** (round n219, 11 November 2026).

## Why

Customers who connect Krusgraph in Claude did not know what to type (the founder, 11 November 2026). `start`, `start
Krusgraph`, `help`, `what can you do` or `check my data` as a first message now leads into one guided path, in the order
the home page's replay shows the answers.

## The path

| Step | What happens | Tool | Reads or writes |
| --- | --- | --- | --- |
| 1 | Choose the workspace | `list_workspaces` | reads |
| 2 | Choose the lakehouse, warehouse or mirrored database | `list_sources` | reads |
| 3 | Choose the schema: every schema with tables is listed | `plan_backend` without a schema | reads |
| 4 | The map: keys and links, each with its rule (K0-K5, R0-R5) | `plan_backend` | reads |
| 5 | Check the map against the rows: unique keys, references without a row | `validate_plan` | reads (counts) |
| 6 | Decide: accept or reject what needs a person | `review_plan` with decisions | reads |
| 7 | Doubled totals: an amount summed over joined rows and once per row | `validate_plan` with fixes=true | reads (counts) |
| 8 | Dry run of what would be built: silver and gold notebooks with the pipeline and its check, semantic model, API for GraphQL, ontology, data agent; the report after its model; the data flow | the `create_*` tools as dry runs | reads |
| 9 | Create, only the names you confirmed after the dry run | the `create_*` tools with dry_run=false | writes |

Each step is one of the existing tools, so its answer is the one that tool gives when called directly. The `start` tool
itself reads nothing and changes nothing: it answers where you are, what was chosen and the next step as a call (in
Claude with MCP Apps on, a stepper card with a button; elsewhere the exact sentence to send). The flow is stateless: the
workspace, source, schema, keys, confirmed links and decisions travel in the arguments of the next `start` call.

Writing needs two confirmations: the dry run (step 8) shows the names, and step 9 hands over a writing call only for
names the user said yes to (`create` must list names from the dry run and `confirm` must be true). On the card, Create is
armed by a first click and runs on the second. A report gets its own dry run once its model exists. No step returns row
values; `sample_rows` is never part of the path.

No Fabric data: *Show me on the synthetic shop sample* (`start` with `sample=true`) walks steps 4 to 9 on the synthetic
shop (`fabric_backend/seed.py`, the answers of `fabric_backend/demo.py`), reading and creating nothing in Fabric.

## The prompt

The server also offers the MCP prompt `start`, titled **Start Krusgraph** (argument `sample`: yes for the synthetic shop).
Sources, read 11 November 2026:

- MCP specification, Prompts: prompts are "user-controlled", "for example, as slash commands"; `prompts/list` gives
  name, title, description and arguments; `prompts/get` gives the messages.
  modelcontextprotocol/modelcontextprotocol, `docs/specification/2025-11-25/server/prompts.mdx` at commit
  0b22bfed6e94c0c7751046d2e845fac954cac8a7 (modelcontextprotocol.io itself could not be opened from the round).
- claude.com/docs/connectors/building: "Your server can expose these to Claude: Tools, prompts, and resources".
- code.claude.com/docs/en/mcp, "Use MCP prompts as commands": Claude Code lists a prompt as
  `/servername:promptname (MCP)`, here `/<the name you gave the server>:start`.
- **Unverified:** where Claude on the web, in the desktop app and on mobile shows a connector's prompts. No Anthropic
  page that says so could be opened. That is why the docs say *type start Krusgraph*, which works in every client.

## Text to send to customers

> Connect Krusgraph in Claude: Customize → Connectors → Add → Add custom connector, paste
> https://krusgraph.com/mcp/connect, keep "Register automatically" and sign in with your Microsoft work account (your
> Entra admin approves Krusgraph once: https://krusgraph.com/start). Then type in a new chat: **start Krusgraph**
>
> Claude leads you one step at a time: your workspace, the lakehouse or warehouse, the schema, the map of keys and links
> with the rule behind each, a check against your rows, what needs your decision, where a total doubles, and a dry run of
> what would be built. Up to the dry run everything only reads, and the answers are counts, not row values. Nothing is
> created until you have seen the dry run and said yes to the names. No Fabric data at hand? Type: *Show me on the
> synthetic shop sample*

## Code

`fabric_backend/start_flow.py` (the steps), `fabric_backend/mcp_apps_start.py` (the card, behind KRUSGRAPH_MCP_APPS),
the `start` tool and prompt in `fabric_backend/server.py`, `tests/test_n219_start.py`.
