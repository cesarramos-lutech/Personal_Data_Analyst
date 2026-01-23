# Technical Walkthrough

A deep-dive guide to understand and present this codebase confidently.

---

## TL;DR - What This Is

An AI agent that lets users ask questions about their data in plain English. It connects to:
- Local CSV/Excel files
- Google BigQuery tables

The agent (powered by Gemini) decides which tools to call, executes them, and explains the results.

**Tech stack:** Python 3.11+ | Google ADK | Pandas | BigQuery | Matplotlib

---

## Why Google ADK

### The Problem with Building AI Agents

Building production-ready AI agents is harder than it looks. You need:
- Tool orchestration (calling functions based on LLM decisions)
- Session/state management (remembering context across turns)
- Streaming responses (not waiting for full completion)
- Deployment infrastructure (scaling, monitoring, auth)
- Model abstraction (swapping models without rewriting code)

Most teams cobble this together with LangChain, custom code, and duct tape. It works for demos but becomes painful at scale.

### What Google ADK Provides

**Google Agent Development Kit (ADK)** is Google's framework for building AI agents. It's designed to go from prototype to production on Google Cloud with minimal friction.

#### ADK Core Components

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Google ADK Architecture                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────┐ │
│  │    Agent     │────▶│    Runner    │────▶│    SessionService        │ │
│  │              │     │              │     │                          │ │
│  │ • name       │     │ • Executes   │     │ • InMemorySessionService │ │
│  │ • model      │     │   agent loop │     │ • DatabaseSessionService │ │
│  │ • instruction│     │ • Handles    │     │ • VertexSessionService   │ │
│  │ • tools[]    │     │   tool calls │     │                          │ │
│  └──────────────┘     └──────────────┘     └──────────────────────────┘ │
│         │                                                                │
│         │ tools                                                          │
│         ▼                                                                │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                         Tool Functions                            │   │
│  │                                                                   │   │
│  │  def my_tool(param: str, ctx: ToolContext) -> dict:              │   │
│  │      ctx.state["key"] = value  # Persist across calls            │   │
│  │      return {"status": "success", "data": ...}                   │   │
│  │                                                                   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│         │                                                                │
│         │ ctx.state                                                      │
│         ▼                                                                │
│  ┌──────────────┐                                                        │
│  │ ToolContext  │  Shared state across all tool calls in a session      │
│  │   .state     │  Enables tool chaining: load → query → analyze        │
│  └──────────────┘                                                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

| Component | Purpose | In This Project |
|-----------|---------|-----------------|
| **Agent** | Defines the AI persona, model, and available tools | `data_analyst/agent.py` |
| **Runner** | Executes the agent loop, handles tool calls | `main.py` (lines 44-48) |
| **SessionService** | Manages conversation state persistence | `InMemorySessionService` for local |
| **ToolContext** | Passes state between tools within a session | Used in every tool function |
| **Tools** | Python functions the agent can call | `tools.py`, `bigquery_tools.py` |

#### Why ADK Over Alternatives

| Requirement | LangChain | Custom Code | Google ADK |
|-------------|-----------|-------------|------------|
| **Tool Definition** | Complex chains, callbacks | Manual parsing | Just Python functions + docstrings |
| **State Management** | Manual memory classes | Build from scratch | Built-in `ToolContext.state` |
| **Session Persistence** | External integration | Build from scratch | Pluggable `SessionService` |
| **Streaming** | Callback handlers | Complex async code | Native support |
| **GCP Integration** | Third-party connectors | Manual setup | Native (BigQuery, Vertex, Cloud Run) |
| **Production Deployment** | DIY infrastructure | DIY infrastructure | One-click to Vertex AI Agent Engine |
| **Model Switching** | Code changes | Code changes | Change env variable |

#### The GCP Advantage

ADK is built for the Google Cloud ecosystem:

```
                        Development                    Production
                        ───────────                    ──────────

Local Development       Cloud Run                      Vertex AI Agent Engine
┌─────────────────┐     ┌─────────────────┐           ┌─────────────────────┐
│ python main.py  │ ──▶ │ Containerized   │ ──▶       │ Fully Managed       │
│ adk web         │     │ Auto-scaling    │           │ Enterprise-grade    │
│ adk api_server  │     │ Load balanced   │           │ Built-in monitoring │
└─────────────────┘     └─────────────────┘           └─────────────────────┘
        │                       │                              │
        └───────────────────────┴──────────────────────────────┘
                                │
                    Same code, different deployment targets
```

- **BigQuery**: Native client, no translation layer
- **Vertex AI**: Direct model access, fine-tuned models
- **Cloud Run**: Stateless deployment with auto-scaling
- **IAM**: Enterprise auth and permissions
- **Cloud Logging**: Built-in observability

#### ADK in Action (This Project)

**Agent definition is declarative:**
```python
data_analyst_agent = Agent(
    name="personal_data_analyst",
    model="gemini-2.0-flash",           # Swap models via env var
    instruction=get_analyst_instructions(),
    tools=[load_data, run_analysis, ...] # Just list the functions
)
```

**Tools are just functions:**
```python
def load_data(filename: str, ctx: ToolContext) -> dict[str, Any]:
    """Load a CSV or Excel file."""  # Docstring becomes tool description
    df = pd.read_csv(filename)
    ctx.state["current_dataset"] = df   # Share with other tools
    return {"status": "success", "rows": len(df)}
```

**Running is one line:**
```python
response = runner.run(user_id="user", session_id="session", new_message="Analyze my data")
```

ADK handles:
- Sending the message to the LLM
- Parsing tool calls from the response
- Executing tools with proper context
- Feeding results back to the LLM
- Streaming the final response

**Bottom line:** ADK lets you focus on *what* your agent does, not *how* to wire it together.

---

## The 30-Second Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Question                           │
│                "What were total sales by region?"               │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Agent (Gemini 2.0 Flash)                     │
│                                                                 │
│  • Receives question                                            │
│  • Decides which tool(s) to call                                │
│  • Chains tools together automatically                          │
│  • Generates natural language response                          │
└─────────────────────────────┬───────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
     ┌────────────┐   ┌────────────┐   ┌────────────┐
     │ Local File │   │  BigQuery  │   │  Analysis  │
     │   Tools    │   │   Tools    │   │    Tool    │
     └──────┬─────┘   └──────┬─────┘   └──────┬─────┘
            │                │                │
            ▼                ▼                ▼
       CSV/Excel        BigQuery         Python Code
         Files           Tables          Execution
```

**Key insight:** The agent is NOT a hardcoded pipeline. The LLM decides the workflow dynamically based on the user's question.

---

## File-by-File Breakdown

### `main.py` - The Entry Point (95 lines)

**What it does:** Creates an interactive CLI loop where users type questions and get responses.

**Key components:**

```python
# Lines 43-48: Create the runtime
session_service = InMemorySessionService()  # Stores conversation state in memory
runner = Runner(
    agent=data_analyst_agent,               # The agent we defined
    app_name="personal-data-analyst",
    session_service=session_service,
)
```

**The Runner** is ADK's execution engine. It:
1. Takes user input
2. Sends it to the agent
3. Executes tool calls the agent makes
4. Returns the final response

```python
# Lines 71-75: Execute agent
response = runner.run(
    user_id="local_user",
    session_id=session.id,
    new_message=user_input,
)
```

**Why InMemorySessionService?** It's simple for local use. For production, you'd use persistent storage so conversations survive restarts.

---

### `data_analyst/agent.py` - The Agent Definition (43 lines)

**This is the brain configuration:**

```python
data_analyst_agent = Agent(
    name="personal_data_analyst",
    model=os.getenv("ANALYST_MODEL", "gemini-2.0-flash"),  # The LLM
    description="A personal data analyst...",
    instruction=get_analyst_instructions(),                 # System prompt
    tools=[                                                 # Available tools
        list_available_data,
        load_data,
        get_data_info,
        list_bigquery_datasets,
        list_bigquery_tables,
        get_table_schema,
        preview_table,
        run_bigquery_sql,
        run_analysis,
    ],
)
```

**How the agent works:**
1. Receives user message + system instructions
2. LLM sees available tools with their docstrings
3. LLM decides: "I need to call `load_data('sales.csv')`"
4. ADK executes the tool, returns result to LLM
5. LLM may call more tools or generate final response

**The tools list is the agent's capabilities.** Add a function here = agent can use it.

---

### `data_analyst/tools.py` - Local File Operations (255 lines)

Four functions that handle CSV/Excel files:

#### `list_available_data(ctx)` - Lines 23-54

```python
def list_available_data(ctx: ToolContext) -> dict[str, Any]:
```

- Scans `DATA_DIR` for `.csv`, `.xlsx`, `.xls` files
- Returns list with filename, type, size
- **Stores file list in `ctx.state["available_files"]`** for later use

#### `load_data(filename, ctx)` - Lines 57-117

```python
def load_data(filename: str, ctx: ToolContext) -> dict[str, Any]:
```

- Reads file into pandas DataFrame
- **Stores DataFrame in context state** - this is crucial:
  ```python
  ctx.state["current_dataset"] = df
  ctx.state["current_dataset_name"] = filename
  ```
- Returns preview + column types + missing value counts

#### `run_analysis(code, ctx)` - Lines 120-204

**This is the most powerful tool.** It executes arbitrary Python code.

```python
def run_analysis(code: str, ctx: ToolContext) -> dict[str, Any]:
```

**Execution environment setup (lines 137-164):**
```python
local_vars = {
    "pd": pd,
    "np": np,
    "plt": plt,
    "sns": sns,
    "DATA_DIR": DATA_DIR,
}

# Inject loaded data
if "current_dataset" in ctx.state:
    local_vars["df"] = ctx.state["current_dataset"]

if "bigquery_query_result" in ctx.state:
    local_vars["bq_result"] = ctx.state["bigquery_query_result"]
```

**Code execution (line 176):**
```python
exec(code, local_vars)
```

**Auto-save visualizations (lines 179-185):**
```python
fig_nums = plt.get_fignums()
for i, num in enumerate(fig_nums):
    fig = plt.figure(num)
    output_path = DATA_DIR / f"analysis_output_{i+1}.png"
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
```

**Why exec()?** It lets the agent write and run Python code dynamically. The agent can generate analysis code based on user questions.

#### `get_data_info(ctx)` - Lines 207-254

Returns detailed column statistics: dtype, null counts, min/max/mean for numeric columns, sample values for text.

---

### `data_analyst/bigquery_tools.py` - BigQuery Operations (264 lines)

Five functions for BigQuery access:

#### Lazy Client Pattern (lines 16-24)

```python
_bq_client = None

def _get_bq_client() -> bigquery.Client:
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(project=PROJECT_ID, location=LOCATION)
    return _bq_client
```

**Why lazy?** Don't create connection until needed. Avoids errors if BigQuery isn't configured but user only uses local files.

#### `run_bigquery_sql(sql, ctx)` - Lines 163-243

**The main query executor.** Key safety features:

```python
# Lines 181-186: Only allow SELECT
sql_upper = sql.strip().upper()
if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
    return {"status": "error", "message": "Only SELECT queries are allowed..."}

# Lines 189-195: Block dangerous keywords
dangerous_keywords = ["DELETE", "DROP", "INSERT", "UPDATE", "TRUNCATE", "ALTER", "CREATE"]
for keyword in dangerous_keywords:
    if keyword in sql_upper:
        return {"status": "error", "message": f"Query contains forbidden keyword: {keyword}"}
```

```python
# Lines 201-203: Billing limit
job_config = bigquery.QueryJobConfig(
    maximum_bytes_billed=10 * 1024 * 1024 * 1024,  # 10 GB limit
)
```

**Results stored for chaining (lines 220-222):**
```python
ctx.state["last_query"] = sql
ctx.state["last_query_result"] = df
ctx.state["bigquery_query_result"] = df  # Used by run_analysis()
```

---

### `data_analyst/prompts.py` - System Instructions (89 lines)

The `get_analyst_instructions()` function returns the system prompt that shapes agent behavior.

**Key sections:**

1. **Capability list** - Tells the agent what tools exist
2. **Guidelines** - Behavioral rules (ask user intent, explore schema first, etc.)
3. **BigQuery Workflow** - Step-by-step process for querying
4. **Code execution context** - What variables are available in `run_analysis()`

**Why this matters:** The prompt is how you "program" LLM behavior. Change this to change how the agent acts.

---

## How Data Flows Through the System

### Example: "Show me sales by region from my CSV"

```
1. User: "Show me sales by region from my CSV"
         │
2. Agent thinks: "I need to find available files first"
         │
3. Agent calls: list_available_data(ctx)
         │
         ├─── Scans ./data/ for CSV/Excel
         ├─── Finds: sample_sales.csv
         └─── Stores: ctx.state["available_files"] = ["sample_sales.csv"]
         │
4. Agent calls: load_data("sample_sales.csv", ctx)
         │
         ├─── pd.read_csv("./data/sample_sales.csv")
         ├─── Stores: ctx.state["current_dataset"] = DataFrame
         └─── Returns: shape, columns, preview
         │
5. Agent calls: run_analysis("""
   sales_by_region = df.groupby('region')['revenue'].sum()
   print(sales_by_region)
   """, ctx)
         │
         ├─── local_vars["df"] = ctx.state["current_dataset"]
         ├─── exec(code, local_vars)
         └─── Returns: printed output
         │
6. Agent: "Here are the sales by region: North: $X, South: $Y..."
```

### Example: BigQuery Query

```
1. User: "What tables are in my analytics dataset?"
         │
2. Agent calls: list_bigquery_tables("analytics", ctx)
         │
         └─── Returns: table names, row counts, sizes
         │
3. User: "Show me top 10 customers by spend"
         │
4. Agent calls: get_table_schema("analytics", "customers", ctx)
         │
         └─── Returns: column names and types (so agent knows what to query)
         │
5. Agent calls: run_bigquery_sql("""
   SELECT customer_name, SUM(amount) as total_spend
   FROM `project.analytics.orders`
   GROUP BY customer_name
   ORDER BY total_spend DESC
   LIMIT 10
   """, ctx)
         │
         ├─── Validates SQL (SELECT only, no dangerous keywords)
         ├─── Executes with 10GB billing limit
         ├─── Stores: ctx.state["bigquery_query_result"] = DataFrame
         └─── Returns: preview of results
         │
6. Agent: "Here are your top 10 customers..."
```

---

## The ToolContext State Machine

`ctx.state` is a dictionary that persists across tool calls within a session. It's how tools share data:

| Key | Set By | Used By |
|-----|--------|---------|
| `available_files` | `list_available_data()` | Agent (for decision making) |
| `current_dataset` | `load_data()` | `run_analysis()`, `get_data_info()` |
| `current_dataset_name` | `load_data()` | `get_data_info()` |
| `bigquery_query_result` | `run_bigquery_sql()` | `run_analysis()` |
| `last_query` | `run_bigquery_sql()` | Agent (context) |
| `current_table_schema` | `get_table_schema()` | Agent (for SQL generation) |

**This enables chaining:** Load data → Analyze → Visualize, all using the same DataFrame.

---

## Security Model

| Risk | Mitigation | Code Location |
|------|------------|---------------|
| SQL injection / data mutation | Only SELECT/WITH allowed, keyword blocklist | `bigquery_tools.py:181-195` |
| Runaway queries | 10GB billing limit | `bigquery_tools.py:201-203` |
| Memory exhaustion | 10,000 row limit | `bigquery_tools.py:213-217` |
| Code execution | Sandboxed exec() with limited namespace | `tools.py:137-164` |
| Credential exposure | Uses gcloud ADC, no hardcoded keys | `.env.example` |

**Note on exec():** It's not fully sandboxed - a malicious user could potentially import modules. For production, consider a proper sandbox or code review step.

---

## Tough Questions You Might Get

### "Why Google ADK instead of LangChain?"

- Native GCP integration (Vertex AI, BigQuery, Cloud Run deployment)
- Simpler tool definition (just functions with docstrings)
- Built-in session management
- Direct path to production on Google Cloud

### "How does the LLM know which tool to call?"

The agent sees:
1. System instructions (from `prompts.py`)
2. Tool function signatures and docstrings
3. User question
4. Previous tool results (in conversation)

It generates a response that may include tool calls. ADK parses these and executes them.

### "What happens if BigQuery isn't configured?"

Tools check `PROJECT_ID` and return informative errors:
```python
if not PROJECT_ID:
    return {"status": "error", "message": "GOOGLE_CLOUD_PROJECT environment variable not set"}
```

Local file features work without any GCP setup.

### "Is the code execution safe?"

Partially. Current mitigations:
- Limited namespace (only pd, np, plt, sns, data)
- No file system access outside DATA_DIR
- Stdout capture

Not safe against determined attackers. For production:
- Use subprocess with resource limits
- Container isolation
- Code review step before execution

### "How would you scale this?"

1. **Multiple users:** Replace `InMemorySessionService` with database-backed sessions
2. **High volume:** Deploy to Cloud Run (stateless, auto-scaling)
3. **Enterprise:** Deploy to Vertex AI Agent Engine (managed infrastructure)

### "What's the latency like?"

- Local file operations: <100ms
- BigQuery queries: 2-10s depending on data size
- LLM calls: 1-3s per turn

Total conversation turn: typically 3-10s.

### "How do you add new data sources?"

1. Create new tools file (e.g., `postgres_tools.py`)
2. Define functions following the same pattern:
   - Accept `ctx: ToolContext` as last parameter
   - Return `dict[str, Any]` with status field
   - Store results in `ctx.state` for chaining
3. Import and add to `agent.py` tools list

---

## Demo Script

### Setup (before demo)
```bash
# Make sure you have sample data
ls data/
# Should show: sample_sales.csv

# Set up environment
cp .env.example .env
# Edit .env with your GCP project if showing BigQuery

# Run it
python main.py
```

### Demo Flow

**1. Start simple - show local analysis:**
```
You: What data files do I have?
You: Load the sales data
You: What are the total sales by region?
You: Create a bar chart of sales by product category
```

**2. Show BigQuery (if configured):**
```
You: What BigQuery datasets do I have access to?
You: What tables are in the [dataset] dataset?
You: Show me the schema for [table]
You: Write a query to find the top 10 [something relevant]
```

**3. Show chaining:**
```
You: Take those query results and create a visualization
```

---

## Quick Reference - All Tools

| Tool | Purpose | Key Parameters |
|------|---------|----------------|
| `list_available_data()` | Find CSV/Excel files | None |
| `load_data(filename)` | Load file to memory | filename |
| `get_data_info()` | Column statistics | None (uses current dataset) |
| `list_bigquery_datasets()` | List BQ datasets | None |
| `list_bigquery_tables(dataset_id)` | List tables in dataset | dataset_id |
| `get_table_schema(dataset_id, table_id)` | Get column definitions | dataset_id, table_id |
| `preview_table(dataset_id, table_id, limit)` | Sample rows | dataset_id, table_id, limit (max 100) |
| `run_bigquery_sql(sql)` | Execute SELECT query | sql string |
| `run_analysis(code)` | Run Python code | Python code string |

---

## Potential Enhancements

### Near-Term (Low Effort, High Value)

| Enhancement | Description | Implementation |
|-------------|-------------|----------------|
| **Multi-file analysis** | Compare/join multiple CSVs in a single query | Extend `run_analysis()` to accept multiple dataset names |
| **Export results** | Save analysis results to CSV/Excel | Add `export_results(filename, format)` tool |
| **Query history** | Show recent queries and re-run them | Store in `ctx.state["query_history"]`, add `show_history()` tool |
| **Natural language to SQL** | Let agent explain generated SQL before running | Add `explain_sql(sql)` tool that describes query intent |

### Medium-Term (Enterprise Features)

| Enhancement | Description | Implementation |
|-------------|-------------|----------------|
| **Database session persistence** | Survive restarts, share sessions across instances | Replace `InMemorySessionService` with `DatabaseSessionService` (Firestore, Cloud SQL) |
| **Multi-user support** | Isolated sessions per user with auth | Integrate with Firebase Auth or Cloud Identity |
| **Scheduled reports** | Automated recurring analyses | Cloud Scheduler + Cloud Functions trigger |
| **Data catalog integration** | Auto-discover datasets from Data Catalog | Add `search_data_catalog(query)` tool |
| **Audit logging** | Track all queries and who ran them | Emit structured logs to Cloud Logging |

### Long-Term (Advanced Capabilities)

| Enhancement | Description | Implementation |
|-------------|-------------|----------------|
| **Multi-agent orchestration** | Specialized agents (SQL expert, viz expert, stats expert) | ADK supports agent-to-agent delegation |
| **Streaming SQL results** | Handle billion-row queries | Use BigQuery Storage Read API with pagination |
| **ML model integration** | Run predictions on data | Add Vertex AI AutoML or custom model tools |
| **Real-time data** | Connect to Pub/Sub streams | Add streaming data source tools |
| **Voice interface** | Talk to your data | Integrate Speech-to-Text + Text-to-Speech |

### Infrastructure Improvements

| Enhancement | Description | Benefit |
|-------------|-------------|---------|
| **Cloud Run deployment** | Containerized, auto-scaling API | Handle multiple concurrent users |
| **Vertex AI Agent Engine** | Fully managed agent hosting | Zero-ops, enterprise SLAs |
| **VPC Service Controls** | Network isolation for sensitive data | Compliance (HIPAA, SOC2) |
| **Customer-managed encryption** | CMEK for data at rest | Enterprise security requirements |

### Code Quality

| Enhancement | Description |
|-------------|-------------|
| **Proper sandboxing** | Use subprocess with seccomp or gVisor for code execution |
| **Input validation** | Pydantic models for tool parameters |
| **Unit tests** | pytest suite for all tools |
| **Integration tests** | End-to-end tests with mock BigQuery |
| **Type checking** | mypy strict mode |

---

## Final Tips

1. **Don't memorize code** - understand the patterns
2. **The agent is the orchestrator** - tools are capabilities
3. **ctx.state is the glue** - it connects tool outputs to inputs
4. **Prompts shape behavior** - change `prompts.py` to change the agent
5. **Safety is layered** - SQL validation + billing limits + row limits
