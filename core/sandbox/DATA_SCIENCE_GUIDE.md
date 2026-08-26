# Data Science with Sterna Sandbox

Guide for using the sandbox's data science packages with AI models.

## Quick Start

No additional configuration needed! The models can already use all pre-installed libraries via the `execute_code` tool.

## How It Works

### ✅ What Models Can Do (Already Working)

Models can execute Python code against the packages pinned in
`Dockerfile.sandbox-datascience` — pandas, numpy, and matplotlib for
analysis and visualization, plus openpyxl, python-docx, and reportlab
for document generation. See
[SANDBOX_IMAGES.md](./SANDBOX_IMAGES.md) for the complete, current
list.

```python
# Example user request:
"Analyze this CSV file and create a visualization"

# Model's response (automatically uses execute_code):
execute_code(code="""
import pandas as pd
import matplotlib.pyplot as plt

# Load data
df = pd.read_csv('/workspace/data.csv')

# Basic analysis
print("Dataset shape:", df.shape)
print("\nSummary statistics:")
print(df.describe())

# Correlation heatmap (matplotlib only — no seaborn in the image)
plt.figure(figsize=(10, 8))
plt.imshow(df.corr(), cmap='coolwarm')
plt.colorbar()
plt.title('Correlation Matrix')
plt.savefig('/workspace/correlation_heatmap.png')
print("\nVisualization saved to /workspace/correlation_heatmap.png")
""")
```

The model receives the output and can:
- Read the saved visualization using `read_file`
- Continue the analysis based on results
- Generate reports, more visualizations, etc.

---

## Example Workflows

### 1. Data Analysis

**User:** "Analyze sales_data.csv and identify trends"

**Model automatically:**
1. Reads the CSV with pandas
2. Generates descriptive statistics
3. Creates time series plots
4. Identifies patterns
5. Saves visualizations
6. Provides insights

### 2. Excel Report Generation

**User:** "Turn this CSV into a formatted Excel report"

**Model automatically:**
1. Loads the CSV with pandas
2. Computes summary statistics
3. Writes a styled workbook with openpyxl (fills, fonts, column widths)
4. Provides a summary

### 3. Word/PDF Document Generation

**User:** "Write this analysis up as a report"

**Model automatically:**
1. Runs the analysis with pandas/matplotlib
2. Saves any charts as PNGs
3. Assembles a document with python-docx or reportlab, embedding the
   charts
4. Provides a summary

Machine learning workflows (scikit-learn, XGBoost, LightGBM), image
processing (PIL, opencv), and PDF text/table extraction (pymupdf,
pypdf) are **not available** in the current image — none of those
packages are installed. A model asked to do one of these either runs
`pip install --user <package>` (see [Limitations](#limitations)
below for why `--user` specifically), or the task needs
`Dockerfile.sandbox-datascience` extended and the image rebuilt
first.

---

## Available Libraries

See [SANDBOX_IMAGES.md](./SANDBOX_IMAGES.md) for the complete, current
list of pre-installed packages — a short, pinned list, not a large
stack.

### Key Categories:
- **Data:** pandas, numpy
- **Viz:** matplotlib
- **Files:** openpyxl, python-docx, reportlab
- **Utilities:** requests, pyyaml, python-dotenv, tqdm, pydantic, ipython

---

## Tool Description (What the Model Actually Sees)

The `execute_code` tool's prompt snippet
(`llm/agent_core/tools/execute_code.py`) tells the model:

> Python code execution with pandas, numpy, matplotlib available. Use
> plt.savefig() not plt.show().

That is the model's only advance notice of what is installed — it is
scoped to the three packages actually guaranteed, not to a larger
stack.

---

## Advanced: Custom Tools (Optional)

While not required, you can create specialized tools for common workflows:

### Example: `analyze_dataframe` Tool

```python
@tool
async def analyze_dataframe(
    file_path: str,
    analysis_type: str = "summary"
) -> dict:
    """
    Quick DataFrame analysis tool.

    Args:
        file_path: Path to CSV/Excel file
        analysis_type: One of: summary, correlations, distributions, missing_values
    """
    # Specialized logic for common analyses
    # Returns structured results
```

### Benefits of Custom Tools:
- **Faster:** Pre-optimized for common tasks
- **Structured output:** Returns JSON instead of text
- **Error handling:** Better validation
- **Ergonomic:** Cleaner interface for models

### When to Create Custom Tools:
- ✅ Repeated workflows (e.g., "analyze sales data every week")
- ✅ Domain-specific tasks (e.g., medical image analysis)
- ✅ Multi-step pipelines (e.g., ETL workflows)
- ❌ One-off analyses (just use execute_code)
- ❌ Simple tasks (overkill)

---

## Performance Tips

### 1. Memory Management

For large datasets, raise `SANDBOX_MEMORY_LIMIT` (env var read in
`sandbox_executor.py`; `docker-compose.sandbox.yml` currently sets
`2g`).

### 2. Chunking

For very large files, process in chunks with pandas rather than
loading the whole file:

```python
# Process CSV in chunks
for chunk in pd.read_csv('large.csv', chunksize=10000):
    process(chunk)
```

Faster alternatives to pandas for large-data or SQL-like workloads
(polars, duckdb) are not installed in the current image — they would
need to be added to `Dockerfile.sandbox-datascience`, or `pip
install --user`ed at runtime, before a model could rely on them.

---

## Limitations

### ⚠️ Whitelist-Only Egress, Not Open Internet
- The container's root filesystem is read-only; only `/workspace` and
  `/tmp` are writable tmpfs. `PYTHONUSERBASE=/workspace/.pip-packages`
  redirects `pip install --user` there, so `--user` installs work
  from PyPI (which is on the egress whitelist); a plain `pip install`
  targets the read-only root and fails
- Requests to arbitrary URLs/APIs are blocked unless the domain is on
  `runtime/whitelist.txt` / `allowed-domains.txt`

**Workaround:** pre-install packages the task needs regularly into
`Dockerfile.sandbox-datascience`, or add the domain to the whitelist.

### ❌ No Display
- Cannot show interactive plots
- Cannot open GUI windows

**Workaround:** Save plots to files, models can read them back

### Resource Limits
- CPU: 1 core (hardcoded `cpu_quota`/`cpu_period` in
  `sandbox_executor.py`)
- PIDs: 100 (hardcoded `pids_limit`)
- Memory: set by `SANDBOX_MEMORY_LIMIT` (`2g` in
  `docker-compose.sandbox.yml`)
- Workspace: tmpfs, size set by `SANDBOX_WORKSPACE_SIZE` (default
  `1024M`)

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'X'"

Check if library is installed:
```bash
docker exec sandbox-exec-user1 python -c "import X"
```

If missing, add to `Dockerfile.sandbox-datascience` and rebuild.

### Out of Memory

Raise `SANDBOX_MEMORY_LIMIT` (see [Limitations](#limitations) above).

### Code Timeout

File operations (`_exec_with_timeout` in `sandbox_executor.py`) are
capped at `FILE_OPERATION_TIMEOUT` (30 seconds); a task that needs
longer needs that constant raised, not a per-call parameter.

---

## Next Steps

1. 📚 **Learn** - Check [SANDBOX_IMAGES.md](./SANDBOX_IMAGES.md) for
   the current package list before assuming a library is available
2. 🎨 **Customize** - Add domain-specific libraries to
   `Dockerfile.sandbox-datascience` and rebuild the image
3. 🔧 **Optimize** - Create custom tools for repeated workflows (optional)
