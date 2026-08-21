# Coding Agent CLI Integration Plan

## Overview

Replace the mock Coding Agent runner with the real Coding Agent CLI, configured to use OpenRouter as the API backend. This allows users to leverage their existing OpenRouter API keys with any supported model.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌───────────────────┐
│   Web Service   │────▶│   Orchestrator   │────▶│ Sandbox Container │
│   (Django)      │     │   (FastAPI)      │     │                   │
└─────────────────┘     └──────────────────┘     │  claude CLI       │
                                                 │  (npm package)    │
                                                 │                   │
                                                 │  Environment:     │
                                                 │  ANTHROPIC_BASE_URL│
                                                 │  ANTHROPIC_AUTH_TOKEN│
                                                 └───────────────────┘
```

## Implementation Steps

### Phase 1: Sandbox Image Update

**File: `core/sandbox/Dockerfile`**

1. Add Node.js installation (if not present)
2. Install Coding Agent CLI globally: `npm install -g @anthropic-ai/coding-agent`
3. Verify installation in build

### Phase 2: Runner Script Update

**File: `core/sandbox/orchestrator/coding_agent_runner.py`**

1. Remove mock `RUNNER_SCRIPT` constant
2. Implement real CLI execution:
   - Set environment variables for OpenRouter
   - Execute `claude --print --output-format stream-json`
   - Parse streaming JSON output
   - Capture files modified/created
   - Handle errors and timeouts

### Phase 3: Output Parsing

**New: `core/sandbox/orchestrator/claude_output_parser.py`**

1. Parse Coding Agent's stream-json format
2. Extract:
   - Tool calls (Read, Write, Edit, Bash, etc.)
   - File modifications
   - Thinking/reasoning steps
   - Final summary
   - Token usage

### Phase 4: Version Tracking Integration

**File: `core/sandbox/orchestrator/coding_agent_runner.py`**

1. Before execution: snapshot existing files
2. After execution: compare with new state
3. Create versions for all changed files
4. Link versions to job_id

## Environment Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `ANTHROPIC_BASE_URL` | `https://openrouter.ai/api` | Route to OpenRouter |
| `ANTHROPIC_AUTH_TOKEN` | User's OpenRouter key | Authentication |
| `ANTHROPIC_API_KEY` | `""` (empty) | Must be empty for OpenRouter |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | Chat's selected model | Model override |

## CLI Arguments

```bash
claude \
  --print \                    # Non-interactive mode
  --output-format stream-json \ # Structured output
  --max-turns 50 \             # Iteration limit
  --allowedTools "Read,Write,Edit,Bash,Glob,Grep" \
  "task description"
```

## Output Format (stream-json)

Each line is a JSON object:
```json
{"type": "system", "content": "Starting..."}
{"type": "assistant", "content": "I'll help you..."}
{"type": "tool_use", "tool": "Read", "input": {"path": "file.py"}}
{"type": "tool_result", "content": "file contents..."}
{"type": "result", "summary": "Task completed", "files_modified": [...]}
```

## Error Handling

1. **Timeout**: 10-minute max execution time
2. **API errors**: Capture stderr, return meaningful error
3. **Permission errors**: Sandbox isolation prevents escapes
4. **Model not available**: Fall back to default or return error

## Testing Checklist

- [ ] Coding Agent CLI installs correctly in sandbox
- [ ] OpenRouter authentication works
- [ ] Model override works (user's selected model)
- [ ] File operations create proper versions
- [ ] Streaming output is captured
- [ ] Errors are handled gracefully
- [ ] Timeout works correctly

## Files to Modify

| File | Changes |
|------|---------|
| `core/sandbox/Dockerfile` | Add Node.js, install coding-agent |
| `core/sandbox/orchestrator/coding_agent_runner.py` | Replace mock with real CLI |
| `core/sandbox/orchestrator/claude_output_parser.py` | New file for parsing |

## Rollback Plan

Keep the mock runner as a fallback. Add environment variable `USE_MOCK_RUNNER=true` to switch back if needed.
