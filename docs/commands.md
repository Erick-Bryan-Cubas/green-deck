> Criando modelo Ollama para flashcards Qwen
```powershell
ollama create qwen-flashcard -f models/qwen_flashcard_finetuned/Modelfile
```
> Listar arquivos excluindo node_modules, .git e data
```powershell
$exclude = '(?i)[\\/](node_modules|\.git|data)([\\/]|$)'

Get-ChildItem -Path . -Force -Recurse -File |
  Where-Object { $_.FullName -notmatch $exclude } |
  Format-Table Mode,LastWriteTime,Length,FullName -AutoSize
```

> Iniciar o aplicativo Spaced Rep com build atualizado
```powershell
PS C:\Users\Erick Bryan\Documents\GitHub\spaced-rep> clear && Set-Location 'C:\Users\Erick Bryan\Documents\GitHub\spaced-rep\frontend' && npm i quill && npm run build && Set-Location '..' && python .\run.py
```

> Excluir banco de dados DuckDB e arquivo WAL
```powershell
del data\storage.duckdb & del data\storage.duckdb.wal 2>nul
```