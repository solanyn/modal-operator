#!/bin/bash
set -e

echo "🚀 Starting Modal Operator Tilt Demo"

# Set Docker host for Colima
export DOCKER_HOST="unix://$HOME/.colima/default/docker.sock"

# Verify prerequisites
echo "📋 Checking prerequisites..."
docker info > /dev/null || { echo "❌ Docker not available"; exit 1; }
kubectl version --client > /dev/null || { echo "❌ kubectl not available"; exit 1; }
tilt version > /dev/null || { echo "❌ Tilt not available"; exit 1; }

echo "✅ Prerequisites OK"

# Start Tilt
echo "🔧 Starting Tilt development environment..."
echo "📱 Tilt UI will be available at: http://localhost:10350"
echo "🛑 Press Ctrl+C to stop"

tilt up --port=10350
