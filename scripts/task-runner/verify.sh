#!/bin/bash

# Task Runner Verification Script
# This script verifies that the task runner environment is properly configured

set -e

echo "=========================================="
echo "Task Runner Verification"
echo "=========================================="

# Verify Node.js version
echo ""
echo "Verifying Node.js..."
NODE_VERSION=$(node -v)
if [[ "$NODE_VERSION" =~ ^v18\. ]]; then
    echo "✓ Node.js version: $NODE_VERSION (correct)"
else
    echo "✗ Node.js version: $NODE_VERSION (should be v18.x)"
    exit 1
fi

# Verify npm
echo ""
echo "Verifying npm..."
NPM_VERSION=$(npm -v)
echo "✓ npm version: $NPM_VERSION"

# Verify git
echo ""
echo "Verifying git..."
GIT_VERSION=$(git --version)
echo "✓ $GIT_VERSION"

# Verify repository state
echo ""
echo "Verifying repository..."
if [ -d ".git" ]; then
    echo "✓ Git repository detected"
else
    echo "✗ Not a git repository"
    exit 1
fi

# Run basic checks
echo ""
echo "Running basic project checks..."

if npm run lint > /dev/null 2>&1; then
    echo "✓ Lint check passed"
else
    echo "✗ Lint check failed"
    exit 1
fi

if npm run build > /dev/null 2>&1; then
    echo "✓ Build check passed"
else
    echo "✗ Build check failed"
    exit 1
fi

if npm test > /dev/null 2>&1; then
    echo "✓ Test suite passed"
else
    echo "✗ Test suite failed"
    exit 1
fi

echo ""
echo "=========================================="
echo "Verification completed successfully!"
echo "=========================================="
