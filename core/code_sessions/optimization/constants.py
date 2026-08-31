"""
Token Optimization Constants

Centralized configuration for all token optimization features.
These values can be tuned to balance cost savings vs quality.
"""

import os

# =============================================================================
# FEATURE FLAGS
# =============================================================================

# Master switch for all optimizations
ENABLE_TOKEN_OPTIMIZATION = os.getenv("ENABLE_TOKEN_OPTIMIZATION", "true").lower() == "true"

# Individual feature flags
ENABLE_CONVERSATION_SUMMARIZATION = os.getenv(
    "ENABLE_CONVERSATION_SUMMARIZATION", "true"
).lower() == "true"

ENABLE_TOOL_COMPRESSION = os.getenv(
    "ENABLE_TOOL_COMPRESSION", "true"
).lower() == "true"

ENABLE_SMART_TRUNCATION = os.getenv(
    "ENABLE_SMART_TRUNCATION", "true"
).lower() == "true"

# Enable explore_codebase tool (scout as a callable tool)
ENABLE_SCOUT_TOOL = os.getenv(
    "ENABLE_SCOUT_TOOL", "true"
).lower() == "true"

# Debug mode - disables all optimizations
FORCE_FULL_CONTEXT = os.getenv("FORCE_FULL_CONTEXT", "false").lower() == "true"


# =============================================================================
# MODEL CONFIGURATION
# =============================================================================

# Scout model: cheap, fast model for exploration
# Using Gemini 2.5 Flash Lite - very cheap and fast, good for code understanding
SCOUT_MODEL_ID = os.getenv(
    "SCOUT_MODEL_ID",
    "google/gemini-2.5-flash-lite"
)

# Alternative scout models (in order of preference)
SCOUT_MODEL_FALLBACKS = [
    "google/gemini-2.5-flash-lite",
    "google/gemini-flash-1.5",
    "anthropic/claude-3-5-haiku-20241022",
    "openai/gpt-4o-mini",
]

# Editor model: uses session's selected model (no override)
# Set this to force a specific editor model (None = use session model)
EDITOR_MODEL_OVERRIDE = os.getenv("EDITOR_MODEL_OVERRIDE", None)


# =============================================================================
# CONVERSATION SUMMARIZATION
# =============================================================================

# Number of recent jobs to keep in full context
# Jobs older than this are summarized
MAX_FULL_HISTORY_JOBS = int(os.getenv("MAX_FULL_HISTORY_JOBS", "2"))

# Maximum tokens for each job summary
SUMMARY_MAX_TOKENS = int(os.getenv("SUMMARY_MAX_TOKENS", "300"))

# Maximum tokens for batch summary of multiple jobs
BATCH_SUMMARY_MAX_TOKENS = int(os.getenv("BATCH_SUMMARY_MAX_TOKENS", "500"))

# Temperature for summarization (lower = more deterministic)
SUMMARIZATION_TEMPERATURE = float(os.getenv("SUMMARIZATION_TEMPERATURE", "0.3"))


# =============================================================================
# TOOL RESULT COMPRESSION
# =============================================================================

# Maximum characters for any tool result
MAX_TOOL_RESULT_CHARS = int(os.getenv("MAX_TOOL_RESULT_CHARS", "4000"))

# list_files specific
LIST_FILES_MAX_ITEMS = int(os.getenv("LIST_FILES_MAX_ITEMS", "50"))
LIST_FILES_GROUP_BY_DIR = os.getenv("LIST_FILES_GROUP_BY_DIR", "true").lower() == "true"

# read_file specific
FILE_CONTENT_MAX_LINES = int(os.getenv("FILE_CONTENT_MAX_LINES", "200"))
FILE_HEAD_LINES = int(os.getenv("FILE_HEAD_LINES", "100"))  # Lines from start
FILE_TAIL_LINES = int(os.getenv("FILE_TAIL_LINES", "50"))   # Lines from end

# run_bash specific
BASH_OUTPUT_MAX_LINES = int(os.getenv("BASH_OUTPUT_MAX_LINES", "100"))
BASH_ERROR_MAX_LINES = int(os.getenv("BASH_ERROR_MAX_LINES", "50"))  # Errors kept longer

# execute_programming_task specific
PROGRAMMING_TASK_OUTPUT_MAX_CHARS = int(
    os.getenv("PROGRAMMING_TASK_OUTPUT_MAX_CHARS", "3000")
)


# =============================================================================
# SMART CONTEXT TRUNCATION
# =============================================================================

# Lines of context around target code for AST truncation
AST_CONTEXT_LINES_BEFORE = int(os.getenv("AST_CONTEXT_LINES_BEFORE", "15"))
AST_CONTEXT_LINES_AFTER = int(os.getenv("AST_CONTEXT_LINES_AFTER", "10"))

# Maximum characters for file preview (initial exploration)
MAX_FILE_PREVIEW_CHARS = int(os.getenv("MAX_FILE_PREVIEW_CHARS", "2000"))

# File extensions that support AST parsing
AST_SUPPORTED_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
}

# Maximum file size to attempt AST parsing (bytes)
MAX_AST_FILE_SIZE = int(os.getenv("MAX_AST_FILE_SIZE", "500000"))  # 500KB


# =============================================================================
# TWO-PHASE (SCOUT/EDITOR) CONFIGURATION
# =============================================================================

# Maximum iterations for scout phase (reduced from 15 - loop detection should catch issues earlier)
SCOUT_MAX_ITERATIONS = int(os.getenv("SCOUT_MAX_ITERATIONS", "8"))

# Maximum tokens for scout phase total
SCOUT_MAX_TOKENS = int(os.getenv("SCOUT_MAX_TOKENS", "4000"))

# Maximum iterations for editor phase
EDITOR_MAX_ITERATIONS = int(os.getenv("EDITOR_MAX_ITERATIONS", "30"))

# Maximum code snippets to include in editor context
MAX_SNIPPETS_FOR_EDITOR = int(os.getenv("MAX_SNIPPETS_FOR_EDITOR", "10"))

# Maximum chars per code snippet in editor context
MAX_SNIPPET_CHARS = int(os.getenv("MAX_SNIPPET_CHARS", "1500"))

# Scout tools (read-only exploration)
SCOUT_TOOLS = [
    "list_files",
    "read_file",
    "run_bash",  # For read-only commands like `cat`, `grep`, `find`
]

# Editor tools (modification allowed)
EDITOR_TOOLS = [
    "list_files",
    "read_file",
    "write_file",
    "edit_file",
    "create_directory",
    "delete_file",
    "rename_file",
    "run_bash",
    "execute_programming_task",
    "update_todos",
    "prepare_pull_request",
]


# =============================================================================
# COST TRACKING
# =============================================================================

# Approximate cost per 1K tokens for scout model (for estimation)
SCOUT_COST_PER_1K_INPUT = float(os.getenv("SCOUT_COST_PER_1K_INPUT", "0.0001"))
SCOUT_COST_PER_1K_OUTPUT = float(os.getenv("SCOUT_COST_PER_1K_OUTPUT", "0.0005"))

# Threshold to warn about high token usage
HIGH_TOKEN_WARNING_THRESHOLD = int(os.getenv("HIGH_TOKEN_WARNING_THRESHOLD", "50000"))


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

SCOUT_SYSTEM_PROMPT = """You are a code exploration assistant. Your job is to understand a coding task and find the relevant code.

## Your Role
- Explore the codebase efficiently
- Identify files that need to be modified
- Extract relevant code snippets
- Suggest an implementation approach

## Rules
- DO NOT make any changes to files
- DO NOT use write_file or edit_file
- ONLY use list_files and read_file
- NEVER re-read the same file twice - you already have the content
- For large files, use read_file parameters:
  - `read_file(path, max_lines=50)` - first 50 lines
  - `read_file(path, start_line=100, end_line=150)` - specific range
  - `read_file(path, summary_only=true)` - just file structure
- DO NOT use run_bash with cat/head/tail - use read_file instead
- Focus on finding the MINIMUM code needed to understand the task
- After 2-3 iterations, produce your final report even if incomplete

## Output Format
When you've gathered enough information, output a JSON report:
```json
{
    "files_to_modify": [
        {"path": "src/file.py", "reason": "Add new function", "lines": "50-80"}
    ],
    "files_to_create": [
        {"path": "src/new.py", "purpose": "New helper module"}
    ],
    "approach": "Brief description of implementation approach",
    "snippets": [
        {"path": "src/file.py", "lines": "10-30", "content": "relevant code..."}
    ]
}
```
"""

EDITOR_SYSTEM_PROMPT_TEMPLATE = """Expert software engineer. Make the requested changes efficiently.

## Context from Scout
The codebase has been analyzed. Here's what you need to know:

### Files to Modify
{files_to_modify}

### Suggested Approach
{approach}

### Relevant Code Snippets
{snippets}

## Your Task
Implement the changes based on the scout's analysis. You have:
- The exact files that need changes
- The relevant code sections
- A suggested approach

## Rules
- Trust the scout's analysis - don't re-explore unnecessarily
- Make targeted edits using edit_file
- If you need to read more of a file, use read_file
- Test your changes with run_bash when appropriate
- Commit changes and prepare PR when done
"""
