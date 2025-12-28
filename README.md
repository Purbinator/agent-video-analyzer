# Agent Video Analyzer - Task Runner Setup

This repository demonstrates the Task Runner VM setup for cto.new with Ubuntu 24.04, Node.js 18, and autoscale testing capabilities.

## System Requirements

- **Ubuntu**: 24.04
- **Node.js**: 18.x (specifically v18.20.8)
- **Memory**: 4GB with autoscaling up to 16GB
- **CPU**: 2 vCPUs

## Setup

The task runner is configured with the following components:

### System Setup
- Node.js 18.20.8 installed via nvm
- Git configured
- Ubuntu 24.04 base system

### Project Dependencies
Install dependencies using:
```bash
npm install
```

### Code Checks
The following checks are configured:

```bash
# Lint check
npm run lint

# Build check
npm run build

# Run tests
npm test
```

## Scripts

### Setup Script
Run the complete setup:
```bash
npm run setup
```

### Verification Script
Verify the task runner configuration:
```bash
npm run verify
```

### Autoscale Test
Test autoscale functionality:
```bash
npm run test:autoscale
```

## Development

The project structure:
```
.
├── scripts/
│   └── task-runner/
│       ├── setup.sh          # System setup script
│       ├── verify.sh         # Verification script
│       └── test-autoscale.js # Autoscale testing
├── tests/
│   └── basic.test.js         # Basic test suite
├── package.json              # Project configuration
├── .nvmrc                    # Node version specification
└── README.md                 # This file
```

## Task Runner Configuration

### System Setup Commands
```bash
# Node 18 is installed via nvm
source ~/.nvm/nvm.sh && nvm use 18
```

### Project Dependencies
```bash
npm install
```

### Code Checks
```bash
npm run lint
npm run build
npm test
```

## License

MIT
