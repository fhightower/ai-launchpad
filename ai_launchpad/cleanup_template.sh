#!/bin/bash
set -euo pipefail

CONTEXT_NAME="__CONTEXT_NAME__"
HOME_BASE="__HOME_BASE__"
MULTIPLEXER="__MULTIPLEXER__"
SESSION_NOUN="__SESSION_NOUN__"
SESSIONS=(__SESSIONS__)
SOURCE_REPOS=(__SOURCE_REPOS__)
WORKTREE_PATHS=(__WORKTREE_PATHS__)
BASE_WORKTREES_DIR="__BASE_WORKTREES_DIR__"

kill_session() {
    local session="$1"
__KILL_SESSION_BODY__
}

echo "=== Cleanup: $CONTEXT_NAME ==="
echo ""
echo "This will:"
for session in "${SESSIONS[@]}"; do
    echo "  - Kill $MULTIPLEXER $SESSION_NOUN: $session"
done
for wt in "${WORKTREE_PATHS[@]}"; do
    echo "  - Remove worktree: $wt"
done
echo "  - Delete home base: $HOME_BASE"
echo ""

read -p "Proceed? [y/N] " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Killing $MULTIPLEXER ${SESSION_NOUN}s..."
for session in "${SESSIONS[@]}"; do
    echo "  Killing: $session"
    kill_session "$session"
done

echo "Removing worktrees..."
for i in "${!WORKTREE_PATHS[@]}"; do
    echo "  Removing: ${WORKTREE_PATHS[$i]}"
    git -C "${SOURCE_REPOS[$i]}" worktree remove "${WORKTREE_PATHS[$i]}" --force || echo "  Warning: Failed to remove ${WORKTREE_PATHS[$i]}"
done

echo "Removing home base: $HOME_BASE"
rm -rf "$HOME_BASE"

cd "$BASE_WORKTREES_DIR"
echo "Cleanup complete."
