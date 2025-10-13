#!/bin/bash
set -e

echo "🚀 Running E2E tests in Modal..."

# Check if Modal is configured
if ! modal token current >/dev/null 2>&1; then
    echo "❌ Modal not configured. Run 'modal token new' first."
    exit 1
fi

# Run e2e tests in Modal
modal run scripts/modal_e2e.py --test-type=e2e

echo "✅ Modal E2E tests completed!"
