@echo off
echo 🔄 Baixando modelo de embeddings nomic-embed-text:v1.5...
ollama pull nomic-embed-text:v1.5

echo ✅ Modelo instalado com sucesso!
echo 📊 Testando modelo...

ollama run nomic-embed-text:v1.5 "teste de embedding"

echo 🎉 Setup concluído!
pause
