#!/bin/bash
set -euo pipefail

CONTEXT_NAME="__CONTEXT_NAME__"
HOME_BASE="__HOME_BASE__"
TMUX_SESSIONS=(__TMUX_SESSIONS__)
SOURCE_REPOS=(__SOURCE_REPOS__)
WORKTREE_PATHS=(__WORKTREE_PATHS__)

echo "=== Cleanup: $CONTEXT_NAME ==="
echo ""
echo "This will:"
for session in "${TMUX_SESSIONS[@]}"; do
    echo "  - Kill tmux session: $session"
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
echo "Killing tmux sessions..."
for session in "${TMUX_SESSIONS[@]}"; do
    echo "  Killing: $session"
    tmux kill-session -t "$session" 2>/dev/null || echo "  Session not found: $session"
done

echo "Removing worktrees..."
for i in "${!WORKTREE_PATHS[@]}"; do
    echo "  Removing: ${WORKTREE_PATHS[$i]}"
    git -C "${SOURCE_REPOS[$i]}" worktree remove "${WORKTREE_PATHS[$i]}" --force || echo "  Warning: Failed to remove ${WORKTREE_PATHS[$i]}"
done

echo "Removing home base: $HOME_BASE"
cd /
rm -rf "$HOME_BASE"

echo "Cleanup complete."
