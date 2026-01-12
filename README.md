# Green Deck

## Setting up Node.js environment with nvm
To set up a Node.js environment using nvm (Node Version Manager), follow these steps:
- First, get instructions for NodeJS:
  - [NodeJS Official Site](https://nodejs.org/en/download)

> Download and install nvm:
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash

> in lieu of restarting the shell
\. "$HOME/.nvm/nvm.sh"

> Download and install Node.js:
nvm install 24

> Verify the Node.js version:
node -v # Should print "v24.12.0".

> Verify npm version:
npm -v # Should print "11.6.2".


## Windows PowerShell snippets:
> Creating Ollama template for Qwen flashcards
```powershell
ollama create qwen-flashcard -f models/qwen_flashcard_finetuned/Modelfile
```
> List files excluding node_modules, .git, and data
```powershell
$exclude = '(?i)[\\/](node_modules|\.git|data)([\\/]|$)'

Get-ChildItem -Path . -Force -Recurse -File |
  Where-Object { $_.FullName -notmatch $exclude } |
  Format-Table Mode,LastWriteTime,Length,FullName -AutoSize
```

> Deleting DuckDB database and WAL file (optional)
```powershell
del data\storage.duckdb & del data\storage.duckdb.wal 2>nul
```

> Starting the Spaced Rep application with the current build
```powershell
PS C:\Users\Erick Bryan\Documents\GitHub\spaced-rep> clear && Set-Location 'C:\Users\Erick Bryan\Documents\GitHub\spaced-rep\frontend' && npm i quill && npm run build && Set-Location '..' && python .\run.py
```


## Linux bash snippets:

> Install the venv package
```bash
sudo apt update && sudo apt install python3-venv -y
sudo apt update && sudo apt install python3-dev -y
```

> Creates the virtual environment
```bash
python3 -m venv srs-venv
source srs-venv/bin/activate
```

> Install the required packages
```bash
pip install -r requirements.txt
```

> Starting the Spaced Rep application with the current build
```bash
clear && source srs-venv/bin/activate && cd frontend && npm run build && cd .. && python3 run.py
```