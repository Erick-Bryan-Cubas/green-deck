import uvicorn
import subprocess
from app.config import PORT

if __name__ == "__main__":
    # Liberar porta (Windows)
    try:
        result = subprocess.run(f'netstat -ano | findstr :{PORT}', shell=True, capture_output=True, text=True)
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                if "LISTENING" in line:
                    pid = line.split()[-1]
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                    print(f"✅ Porta {PORT} liberada (PID {pid} finalizado)")
    except:
        pass

    print(f"\n🚀 Servidor iniciado em http://localhost:{PORT}")
    print(f"📚 Flash Card Generator v1.0.1-beta\n")

    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=True)
