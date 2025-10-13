#!/bin/bash
set -e

echo "🚀 Starting Modal vGPU Operator E2E Tests"

# Check prerequisites
command -v kind >/dev/null 2>&1 || { echo "❌ kind is required but not installed"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "❌ kubectl is required but not installed"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ docker is required but not installed"; exit 1; }

# Build operator image
echo "🔨 Building operator image..."
docker build -t modal-vgpu-operator:latest .

# Load image into kind (will be done by test setup)
echo "📦 Image built successfully"

# Run e2e tests
echo "🧪 Running E2E tests..."
uv run pytest tests/e2e/ -v -s --tb=short

echo "✅ E2E tests completed!"
