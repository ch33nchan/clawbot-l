
## Node.js + npm setup (Ubuntu 24.04 / AWS)

This repo uses Node.js tooling (npm) and the `openclaw` CLI.

### Recommended: install via `nvm` (per-user, easy upgrades)

```bash
sudo apt-get update
sudo apt-get install -y curl ca-certificates build-essential

# Install nvm
curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash

# Load nvm into the *current* shell (also added to ~/.bashrc for new shells)
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

# Install the latest LTS Node.js and use it
nvm install --lts
nvm use --lts

# Sanity check
node -v
npm -v
```

### Install OpenClaw

```bash
# In a fresh shell, re-load nvm first:
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
nvm use --lts

npm install -g openclaw@latest
openclaw --version
openclaw --help
```

### Notes / troubleshooting

- If `node`/`npm` are “not found” after install: close/reopen the terminal, or run the `export NVM_DIR=...` + `source nvm.sh` lines above.
- If you were already inside `tmux` when you installed `nvm`/Node: run `source ~/.bashrc && nvm use --lts` (or just start a new `tmux` session) so `PATH` picks up `~/.nvm/versions/node/.../bin`.
- If you use non-bash shells later (zsh, etc.), you’ll want to add the same `nvm` load lines to that shell’s startup file.

### What we added to `~/.bashrc` (so `openclaw` stays on PATH)

The `nvm` installer appended these lines (loads `nvm` for interactive bash shells):

```bash
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion
```

Then we added this small block to automatically select the latest LTS Node in new shells (so global npm CLIs like `openclaw` work without manually running `nvm use`):

```bash
if command -v nvm >/dev/null 2>&1; then
  nvm use --silent --lts >/dev/null 2>&1 || true
fi
```
