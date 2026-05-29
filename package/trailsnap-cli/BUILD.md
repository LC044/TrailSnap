# TrailSnap CLI

Command Line Interface for TrailSnap.

## Installation

### Via pip

```bash
pip install trailsnap-cli
```

### Via npm

```bash
npm install -g trailsnap-cli
```

## Local Development / Testing

If you want to test or develop the CLI locally before publishing:

### 1. Test via Python (Recommended for Development)

Use pip's editable mode to install the package so your code changes take effect immediately without reinstalling:

```bash
cd package/trailsnap-cli
pip install -e .

# Test if the command works
trailsnap --help
```

### 2. Test via npm (Testing the Node.js Wrapper)

Since the npm package relies on downloading pre-built binaries from GitHub Releases (which don't exist locally), you must build the binary manually and skip the download script.

```bash
cd package/trailsnap-cli

# Install pyinstaller
pip install pyinstaller

# Build the standalone executable
pyinstaller --onefile --name trailsnap --paths trailsnap trailsnap/cli.py

# Create bin directory and move the executable (Windows example)
mkdir bin
cp dist/trailsnap.exe bin/
# For Mac/Linux: cp dist/trailsnap bin/

# Install globally via npm, skipping the postinstall download script
npm install -g . --ignore-scripts

# Test if the wrapper works
trailsnap --help
```

To uninstall local versions:
- `pip uninstall trailsnap-cli`
- `npm uninstall -g trailsnap-cli`
