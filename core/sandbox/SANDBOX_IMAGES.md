# Sandbox Container Images

Sterna provides two sandbox container images for different use cases.

## Images Overview

### 1. `sandbox-base:latest` (Minimal - ~500MB)

**Use case:** General code execution, simple scripts, lightweight tasks

**Included:**
- Python 3.11
- Basic system tools (curl, git)
- No additional Python packages

**Memory:** 512MB limit
**Best for:** Quick scripts, testing, minimal resource usage

---

### 2. `sandbox-datascience:latest` (Full-Featured - ~3GB)

**Use case:** Data analysis, machine learning, visualization, scientific computing

**Included Python packages:**

#### 📊 Data Manipulation
- **numpy** (1.26.4) - Numerical arrays and operations
- **pandas** (2.2.0) - DataFrames and data analysis
- **polars** (0.20.7) - High-performance DataFrames
- **pyarrow** (15.0.0) - Apache Arrow format
- **duckdb** (0.10.0) - In-process SQL OLAP database

#### 🤖 Machine Learning
- **scikit-learn** (1.4.0) - ML algorithms (classification, regression, clustering)
- **xgboost** (2.0.3) - Gradient boosting
- **lightgbm** (4.3.0) - Light gradient boosting
- **catboost** (1.2.2) - Categorical boosting
- **statsmodels** (0.14.1) - Statistical models

#### 📈 Visualization
- **matplotlib** (3.8.2) - Static plots
- **seaborn** (0.13.2) - Statistical visualizations
- **plotly** (5.18.0) - Interactive plots (offline mode)
- **bokeh** (3.3.4) - Interactive visualizations
- **altair** (5.2.0) - Declarative visualizations (offline)

#### 🖼️ Image Processing
- **pillow** (10.2.0) - Image manipulation
- **imageio** (2.34.0) - Image I/O
- **opencv-python-headless** (4.9.0) - Computer vision (no GUI)
- **scikit-image** (0.22.0) - Image processing algorithms

#### 🔢 Scientific Computing
- **scipy** (1.12.0) - Scientific algorithms
- **sympy** (1.12) - Symbolic mathematics
- **numba** (0.59.0) - JIT compiler for numerical code
- **numexpr** (2.9.0) - Fast numerical expressions

#### 📄 File Formats
- **openpyxl** (3.1.2) - Excel files (.xlsx)
- **xlrd** (2.0.1) - Excel files (.xls)
- **xlsxwriter** (3.2.0) - Excel file creation
- **pyxlsb** (1.0.10) - Excel binary format
- **python-docx** (1.1.0) - Word documents
- **python-pptx** (0.6.23) - PowerPoint files
- **pdfminer.six** (20231228) - PDF text extraction
- **pymupdf** (1.23.22) - PDF manipulation
- **pypdf** (4.0.1) - PDF toolkit

#### 🗃️ Database & SQL
- **sqlite-utils** (3.36) - SQLite utilities
- **sqlalchemy** (2.0.27) - SQL toolkit and ORM

#### 🕸️ Web & Parsing
- **beautifulsoup4** (4.12.3) - HTML/XML parsing
- **lxml** (5.1.0) - Fast XML/HTML processing
- **html5lib** (1.1) - HTML5 parser
- **pydantic** (2.6.1) - Data validation
- **fastapi** (0.109.2) - Web framework (for local testing)
- **uvicorn** (0.27.1) - ASGI server

#### 📊 Graph & Network Analysis
- **networkx** (3.2.1) - Network graphs
- **graphviz** (0.20.1) - Graph visualization
- **pygraphviz** (1.12) - Graphviz bindings

#### 📅 Time Series & Statistics
- **patsy** (0.5.6) - Statistical formulas
- **pingouin** (0.5.4) - Statistical tests
- **pmdarima** (2.0.4) - ARIMA models
- **ruptures** (1.1.9) - Change point detection

#### 🌍 Geographic Data
- **shapely** (2.0.3) - Geometric objects
- **geopandas** (0.14.3) - Geographic DataFrames
- **pyproj** (3.6.1) - Cartographic projections

#### ⚡ Performance & Utilities
- **joblib** (1.3.2) - Parallel computing
- **dask** (2024.2.0) - Parallel arrays and DataFrames
- **fastparquet** (2024.2.0) - Parquet format
- **ujson** (5.9.0) - Ultra-fast JSON
- **orjson** (3.9.15) - Optimized JSON
- **tenacity** (8.2.3) - Retry logic
- **cachetools** (5.3.2) - Caching utilities

#### 🛠️ Development Tools
- **tqdm** (4.66.2) - Progress bars
- **rich** (13.7.0) - Rich terminal output
- **ipython** (8.21.0) - Interactive Python shell
- **click** (8.1.7) - CLI framework
- **typer** (0.9.0) - CLI framework (type hints)
- **tabulate** (0.9.0) - Pretty tables
- **python-dotenv** (1.0.1) - Environment variables
- **validators** (0.22.0) - Data validation
- **pyyaml** (6.0.1) - YAML parser
- **python-dateutil** (2.8.2) - Date utilities
- **pytz** (2024.1) - Timezone handling
- **python-magic** (0.4.27) - File type detection
- **chardet** (5.2.0) - Character encoding detection
- **charset-normalizer** (3.3.2) - Character encoding

**Memory:** Recommend 1-2GB limit (increase from default 512MB)
**Best for:** Data analysis, ML training, scientific computing, complex visualizations

---

## Configuration

### Using Data Science Image

Edit `sandbox/orchestrator/sandbox_executor.py` line ~147:

```python
container = self.docker.containers.run(
    image="sandbox-datascience:latest",  # Changed from "sandbox-base:latest"
    # ... rest of config
```

### Update Memory Limits

For data science workloads, increase memory in `sandbox_executor.py` line ~161:

```python
# Resource limits
mem_limit="1536m",  # Changed from "512m" (1.5GB for data science)
```

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
- ✅ **Network isolation** - No internet access (internal network only)
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

### With `sandbox-datascience` (Full)
```python
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Load data
df = pd.read_csv('/workspace/data.csv')

# Analyze
summary = df.describe()

# Visualize
plt.figure(figsize=(10, 6))
sns.boxplot(data=df)
plt.savefig('/workspace/plot.png')

# Machine learning
from sklearn.ensemble import RandomForestClassifier
model = RandomForestClassifier()
model.fit(X_train, y_train)
predictions = model.predict(X_test)
```

---

## Image Sizes

| Image | Compressed | Uncompressed | Build Time |
|-------|-----------|--------------|------------|
| `sandbox-base` | ~180MB | ~500MB | ~2 min |
| `sandbox-datascience` | ~1.2GB | ~3GB | ~15 min |

Build times are approximate and depend on internet speed and CPU.
