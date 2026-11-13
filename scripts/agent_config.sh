#!/usr/bin/env bash
# Shared configuration for run_one.sh and smoke_test.sh. Source it, do not execute it.
# Every value can be overridden with the environment variable of the same name.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNS_ROOT="${TDD_PILOT_RUNS_ROOT:-/tmp/tdd-pilot-runs}"
MODEL="${TDD_PILOT_MODEL:-claude-sonnet-5-5}"
EFFORT="${TDD_PILOT_EFFORT:-medium}"
MAX_BUDGET_USD="${TDD_PILOT_MAX_BUDGET_USD:-10}"
TIMEOUT_SECONDS="${TDD_PILOT_TIMEOUT_SECONDS:-5400}"

if [[ -d "$PROJECT_DIR/.venv/Scripts" ]]; then
    VENV_BIN="$PROJECT_DIR/.venv/Scripts"
else
    VENV_BIN="$PROJECT_DIR/.venv/bin"
fi
PYTHON="$VENV_BIN/python"

# Locate the Claude Code CLI: explicit CLAUDE_BIN, then PATH, then the copy
# bundled with the Claude desktop app on Windows (newest version wins).
resolve_claude_bin() {
    if [[ -n "${CLAUDE_BIN:-}" ]]; then
        echo "$CLAUDE_BIN"
    elif command -v claude >/dev/null 2>&1; then
        command -v claude
    elif [[ -n "${LOCALAPPDATA:-}" ]]; then
        local base
        base="$(cygpath -u "$LOCALAPPDATA" 2>/dev/null || echo "$LOCALAPPDATA")"
        local candidates=("$base"/Claude-Data/*/claude-code/*/*/claude.exe)
        [[ -e "${candidates[0]}" ]] && printf '%s\n' "${candidates[@]}" | sort -V | tail -n 1
    fi
}
CLAUDE_BIN="$(resolve_claude_bin)"
if [[ -z "$CLAUDE_BIN" ]]; then
    echo "Claude Code CLI not found; set CLAUDE_BIN" >&2
    return 1 2>/dev/null || exit 1
fi

# Environment variables that must not leak from the orchestrating session into the
# agent (e.g. CLAUDECODE, CLAUDE_CODE_SIMPLE, CLAUDE_EFFORT set by a parent Claude).
# Only credentials and the Git Bash location are kept.
KEEP_ENV_REGEX='^(ANTHROPIC_API_KEY|CLAUDE_CODE_OAUTH_TOKEN|CLAUDE_CODE_GIT_BASH_PATH|CLAUDE_CONFIG_DIR)$'
SCRUB_ENV_ARGS=()
while IFS= read -r env_name; do
    [[ "$env_name" =~ $KEEP_ENV_REGEX ]] || SCRUB_ENV_ARGS+=(-u "$env_name")
done < <(compgen -e | grep -E '^(CLAUDE|ANTHROPIC)')

# v1 allowed only "Bash(git *)" and "Bash(./run_tests.sh*)": 3 of 6 pilot runs stopped after
# a denied heredoc file write. v2 allows Bash in general; the file tools stay confined by
# --restricted and the transcript scan in check_process.py flags access outside the workspace.
CONFIG_VERSION="v2-bash-allowed"

# The prompt (positional argument) must come before the variadic --tools /
# --allowedTools options, otherwise it would be parsed as one more tool name.
AGENT_FLAGS=(
    --model "$MODEL"
    --effort "$EFFORT"
    --output-format stream-json
    --verbose
    --safe-mode
    --restricted
    --strict-mcp-config
    --no-session-persistence
    --disable-slash-commands
    --tools "Bash,Read,Edit,Write,Glob,Grep"
    --allowedTools "Read" "Edit" "Write" "Glob" "Grep" "Bash"
    --permission-mode dontAsk
    --permission-prompts none
    --max-budget-usd "$MAX_BUDGET_USD"
)

# Git identity and config for the workspace, independent of the user's global config.
GIT_ISOLATION_ENV=(
    GIT_CONFIG_NOSYSTEM=1
    GIT_CONFIG_GLOBAL="$RUNS_ROOT/.empty-gitconfig"
    GIT_AUTHOR_NAME=tdd-pilot-agent
    GIT_AUTHOR_EMAIL=agent@tdd-pilot.invalid
    GIT_COMMITTER_NAME=tdd-pilot-agent
    GIT_COMMITTER_EMAIL=agent@tdd-pilot.invalid
)

# Creates a fresh workspace from the template with the initial commit.
# Usage: init_workspace <dir>
init_workspace() {
    local ws="$1"
    if [[ -e "$ws" ]]; then
        echo "Workspace $ws already exists; refusing to reuse it" >&2
        return 1
    fi
    mkdir -p "$ws" "$RUNS_ROOT"
    : > "$RUNS_ROOT/.empty-gitconfig"
    cp -r "$PROJECT_DIR/task/template/." "$ws/"
    (
        cd "$ws"
        export "${GIT_ISOLATION_ENV[@]}"
        git init -q
        git config core.autocrlf false
        git config core.filemode false
        git add -A
        git update-index --chmod=+x run_tests.sh
        git commit -q -m "chore: initial template"
    )
}

# Runs the agent in <workspace> with <prompt>; stdout -> <transcript>, stderr -> <stderr_log>.
# Usage: run_agent <workspace> <prompt> <transcript> <stderr_log>
run_agent() {
    local ws="$1" prompt="$2" transcript="$3" stderr_log="$4"
    (
        cd "$ws"
        env "${SCRUB_ENV_ARGS[@]}" "${GIT_ISOLATION_ENV[@]}" PATH="$VENV_BIN:$PATH" \
            timeout "$TIMEOUT_SECONDS" "$CLAUDE_BIN" -p "$prompt" "${AGENT_FLAGS[@]}" \
            > "$transcript" 2> "$stderr_log" < /dev/null
    )
}
