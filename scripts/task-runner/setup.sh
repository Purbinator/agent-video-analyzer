#!/bin/bash

# Task Runner Setup Script
# This script sets up the VM environment for the agent-video-analyzer project

set -e

echo "=========================================="
echo "Task Runner Setup for agent-video-analyzer"
echo "=========================================="

# Check Node version
echo ""
echo "Step 1: Verifying Node.js version..."
NODE_VERSION=$(node -v)
echo "Current Node.js version: $NODE_VERSION"

if [[ ! "$NODE_VERSION" =~ ^v18\. ]]; then
    echo "ERROR: Node.js 18.x is required, but found $NODE_VERSION"
    echo "Please ensure Node 18 is installed and active"
    exit 1
fi
echo "✓ Node.js version check passed"

# Check npm version
echo ""
echo "Step 2: Verifying npm version..."
NPM_VERSION=$(npm -v)
echo "Current npm version: $NPM_VERSION"
echo "✓ npm version check passed"

# System information
echo ""
echo "Step 3: Gathering system information..."
echo "OS: $(lsb_release -d | cut -f2)"
echo "Kernel: $(uname -r)"
echo "Architecture: $(uname -m)"
echo "CPU cores: $(nproc)"
echo "Memory: $(free -h | awk '/^Mem:/ {print $2}')"
echo "✓ System information gathered"

# Install project dependencies (if any)
echo ""
echo "Step 4: Installing project dependencies..."
if [ -f "package.json" ]; then
    npm install
    echo "✓ Dependencies installed"
else
    echo "⚠ No package.json found, skipping dependency installation"
fi

# Create necessary directories
echo ""
echo "Step 5: Creating necessary directories..."
mkdir -p tests
mkdir -p logs
mkdir -p tmp
echo "✓ Directories created"

echo ""
echo "=========================================="
echo "Setup completed successfully!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Run 'npm test' to run tests"
echo "  2. Run 'npm run test:autoscale' to test autoscale functionality"
echo "  3. Run 'npm run verify' to verify the setup"
