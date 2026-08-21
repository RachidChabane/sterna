# Data Science with Sterna Sandbox

Guide for using the full data science environment with AI models.

## Quick Start

No additional configuration needed! The models can already use all pre-installed libraries via the `execute_code` tool.

## How It Works

### ✅ What Models Can Do (Already Working)

Models can execute Python code with access to 90+ libraries:

```python
# Example user request:
"Analyze this CSV file and create a visualization"

# Model's response (automatically uses execute_code):
execute_code(code="""
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Load data
df = pd.read_csv('/workspace/data.csv')

# Basic analysis
print("Dataset shape:", df.shape)
print("\nSummary statistics:")
print(df.describe())

# Correlation heatmap
plt.figure(figsize=(10, 8))
sns.heatmap(df.corr(), annot=True, cmap='coolwarm')
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

### 2. Machine Learning

**User:** "Build a classification model to predict customer churn"

**Model automatically:**
1. Loads and explores data
2. Preprocesses features
3. Splits train/test sets
4. Trains multiple models (RF, XGBoost, LightGBM)
5. Evaluates performance
6. Saves the best model
7. Generates feature importance plots

### 3. Image Processing

**User:** "Resize and enhance these images"

**Model automatically:**
1. Uses PIL/opencv to load images
2. Applies transformations
3. Saves processed images
4. Creates before/after comparisons

### 4. PDF Analysis

**User:** "Extract tables from this PDF and convert to Excel"

**Model automatically:**
1. Uses pymupdf to extract tables
2. Parses with pandas
3. Saves to Excel with openpyxl
4. Provides summary

---

## Available Libraries

See [SANDBOX_IMAGES.md](./SANDBOX_IMAGES.md) for the complete list of 90+ pre-installed libraries.

### Key Categories:
- **Data:** pandas, polars, duckdb
- **ML:** scikit-learn, xgboost, lightgbm, catboost
- **Viz:** matplotlib, seaborn, plotly, bokeh
- **Files:** openpyxl, python-docx, pypdf, pymupdf
- **Image:** pillow, opencv, scikit-image
- **Stats:** scipy, statsmodels, pingouin

---

## System Prompt (Auto-Included)

When `enable_file_tools=True`, models automatically receive this context:

> Your code execution environment has a comprehensive data science stack pre-installed.
> Available libraries include: numpy, pandas, polars, scikit-learn, xgboost, matplotlib,
> seaborn, plotly, opencv, and many more.
>
> You can use these libraries directly without installation. For visualizations, save plots
> to files (e.g., plt.savefig('/workspace/plot.png')) as the environment has no display.

This means models know exactly what's available!

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

For large datasets (>500MB), increase sandbox memory:

```python
# sandbox_executor.py
mem_limit="2048m",  # 2GB for large datasets
```

### 2. Efficient Libraries

Recommend to models:
- **polars** > pandas (for large datasets)
- **duckdb** > pandas (for SQL-like queries)
- **orjson** > json (for large JSON files)
- **fastparquet** > csv (for columnar data)

### 3. Chunking

For very large files, process in chunks:

```python
# Process CSV in chunks
for chunk in pd.read_csv('large.csv', chunksize=10000):
    process(chunk)
```

---

## Limitations

### ❌ No Internet Access
- Cannot `pip install` additional packages
- Cannot download data from URLs
- Cannot access external APIs

**Workaround:** Pre-install packages in Dockerfile or use file uploads

### ❌ No Display
- Cannot show interactive plots
- Cannot open GUI windows

**Workaround:** Save plots to files, models can read them back

### ❌ Resource Limits
- CPU: 1 core (configurable)
- Memory: 1.5GB (configurable)
- Disk: 2GB tmpfs

**Workaround:** Increase limits in `sandbox_executor.py`

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'X'"

Check if library is installed:
```bash
docker exec sandbox-exec-user1 python -c "import X"
```

If missing, add to `Dockerfile.sandbox-datascience` and rebuild.

### Out of Memory

Increase memory limit:
```python
mem_limit="2048m"  # or higher
```

### Code Timeout

Increase execution timeout in orchestrator:
```python
timeout=60  # seconds
```

---

## Next Steps

1. ✅ **No action needed** - Models can already use all libraries
2. 📚 **Learn** - Check [SANDBOX_IMAGES.md](./SANDBOX_IMAGES.md) for full library list
3. 🎨 **Customize** - Add domain-specific libraries to Dockerfile if needed
4. 🔧 **Optimize** - Create custom tools for repeated workflows (optional)

The data science environment is **production-ready** with existing tools!
