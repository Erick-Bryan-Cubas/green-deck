import subprocess
import uvicorn
from app.config import PORT
from app.utils.banner import print_banner

if __name__ == "__main__":
    try:
        result = subprocess.run(f'netstat -ano | findstr :{PORT}', shell=True, capture_output=True, text=True, check=False)
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                if "LISTENING" in line:
                    pid = line.split()[-1]
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True, text=True, check=False)
                    print(f"✅ Porta {PORT} liberada (PID {pid} finalizado)")
    except Exception as e:
        print(f"Warning: error while trying to free port {PORT}: {e}")
    print_banner()
    print(f"\nServer running on http://localhost:{PORT}\n")

    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=True)
