# Sandbox Container Images

Sterna provides two sandbox container images for different use cases.

## Images Overview

### 1. `sandbox-base:latest` (Minimal)

**Use case:** General code execution, simple scripts, lightweight tasks

**Included:**
- Python 3.11 (`python:3.11-slim`)
- Node.js 20, opencode CLI (`runtime/Dockerfile.sandbox-base`)
- Basic system tools (curl, git)
- No additional Python packages

**Memory:** set via the `SANDBOX_MEMORY_LIMIT` environment variable
(same variable as `sandbox-datascience`; see below).
**Best for:** Quick scripts, testing, minimal resource usage

---

### 2. `sandbox-datascience:latest` (built on `sandbox-base`)

**Use case:** Data analysis, tabular visualization, document/spreadsheet generation

**Included Python packages** (pinned in
`runtime/Dockerfile.sandbox-datascience`; the source of truth for
this list is that Dockerfile, not this document):

#### 📊 Data Manipulation
- **numpy** (1.26.4) - Numerical arrays and operations
- **pandas** (2.2.0) - DataFrames and data analysis

#### 📈 Visualization
- **matplotlib** (3.8.2) - Static plots (`MPLBACKEND=Agg`, no display)

#### 📄 File Formats
- **openpyxl** (3.1.5) - Excel files (.xlsx)
- **python-docx** (1.1.0) - Word documents
- **reportlab** (4.1.0) - PDF generation

#### 🛠️ Utilities
- **requests** (2.31.0) - HTTP client
- **pyyaml** (6.0.1) - YAML parser
- **python-dotenv** (1.0.1) - Environment variables
- **tqdm** (4.66.2) - Progress bars
- **pydantic** (2.6.1) - Data validation
- **ipython** (8.21.0) - Interactive Python shell

None of scikit-learn, xgboost, lightgbm, scipy, seaborn, plotly,
opencv, beautifulsoup4, or xlsxwriter are installed. A task needing
one of them either adds it to `Dockerfile.sandbox-datascience` and
rebuilds the image, or the model runs `pip install --user <package>`
at runtime — PyPI is on the egress whitelist, and `PYTHONUSERBASE` is
set to `/workspace/.pip-packages`, the one writable path, so a
`--user` install lands somewhere the read-only root filesystem
doesn't block (see
[Limitations](./DATA_SCIENCE_GUIDE.md#limitations)).

**Memory:** set via the `SANDBOX_MEMORY_LIMIT` environment variable
(`orchestrator/sandbox_executor.py`); `docker-compose.sandbox.yml`
sets it to `2g`.
**Best for:** tabular data analysis, matplotlib visualizations,
Excel/Word/PDF document generation.

---

## Configuration

### Image selection

`orchestrator/sandbox_executor.py` runs execution and coding-agent
containers from `sandbox-datascience:latest` — the data-science image
is already the default, not an opt-in switch from `sandbox-base`.

### Memory limits

Set via the `SANDBOX_MEMORY_LIMIT` environment variable, read in
`sandbox_executor.py`; `docker-compose.sandbox.yml` sets it to `2g`.

---

## Building Images

Build all images:
```bash
cd sandbox
./build-images.sh
```

Build only data science image:
```bash
cd sandbox/runtime
docker build -f Dockerfile.sandbox-datascience -t sandbox-datascience:latest .
```

---

## Security Notes

All images run with:
- ✅ **Network isolation** - Docker network is `internal: true`; all
  egress is forced through the mitmproxy whitelist proxy (PyPI, npm,
  GitHub, OpenRouter, and a handful of doc sites — see
  `runtime/whitelist.txt` / `allowed-domains.txt`), not open internet
  access
- ✅ **gVisor runtime** - Enhanced container isolation
- ✅ **Resource limits** - CPU, memory, and process limits
- ✅ **Non-root user** - Runs as `sandboxuser` (UID 1000)
- ✅ **Capability drop** - All Linux capabilities dropped
- ✅ **Read-only root** - Immutable root filesystem (tmpfs for /tmp, /workspace)

The data science libraries are safe to use in the isolated environment.

---

## Example Use Cases

### With `sandbox-base` (Minimal)
```python
# Simple calculations
result = sum([1, 2, 3, 4, 5])
print(result)  # 15

# File operations
with open('/workspace/test.txt', 'w') as f:
    f.write("Hello, World!")
```

### With `sandbox-datascience`
```python
import pandas as pd
import matplotlib.pyplot as plt

# Load data
df = pd.read_csv('/workspace/data.csv')

# Analyze
summary = df.describe()

# Visualize
plt.figure(figsize=(10, 6))
df.plot(kind='box')
plt.savefig('/workspace/plot.png')

# Excel output
df.to_excel('/workspace/summary.xlsx', engine='openpyxl')
```

---

## Image Sizes

Build `sandbox-base` and `sandbox-datascience` with `./build-images.sh`
and check `docker images` for current sizes — they vary with the base
Python image and installed package set, so a number recorded here
would drift out of sync with the Dockerfiles that actually determine
it.
