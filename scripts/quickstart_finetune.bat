@echo off
echo ========================================
echo Flashcard Model Fine-Tuning Quick Start
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.8+
    pause
    exit /b 1
)

echo Step 1: Installing dependencies...
echo.
pip install -r requirements_finetune.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo ========================================
echo Step 2: Generate Training Data
echo ========================================
echo.
echo Do you have a Claude API key? (Y/N)
set /p HAS_KEY=

if /i "%HAS_KEY%"=="Y" (
    echo.
    set /p API_KEY="Enter your Anthropic API key: "
    echo.
    echo Generating training data with Claude...
    python generate_training_data.py %API_KEY%
    if errorlevel 1 (
        echo WARNING: Failed to generate data with Claude
        echo Falling back to built-in examples...
    )
) else (
    echo.
    echo Using built-in training examples...
)

echo.
echo ========================================
echo Step 3: Fine-Tuning Model
echo ========================================
echo.
echo This will take 15-30 minutes depending on your GPU.
echo Press any key to start training...
pause >nul

if exist "training_data_formatted.jsonl" (
    python finetune_with_data.py
) else (
    python finetune_flashcard_model.py
)

if errorlevel 1 (
    echo ERROR: Fine-tuning failed
    pause
    exit /b 1
)

echo.
echo ========================================
echo Step 4: Import to Ollama
echo ========================================
echo.

cd flashcard_qwen3_finetuned
ollama create flashcard-qwen3:4b -f Modelfile
if errorlevel 1 (
    echo ERROR: Failed to import model to Ollama
    cd ..
    pause
    exit /b 1
)
cd ..

echo.
echo ========================================
echo Step 5: Test the Model
echo ========================================
echo.
python test_finetuned_model.py

echo.
echo ========================================
echo SUCCESS! Fine-tuning complete!
echo ========================================
echo.
echo Your fine-tuned model is ready: flashcard-qwen3:4b
echo.
echo To use it, update main_optimized.py:
echo   OLLAMA_MODEL = "flashcard-qwen3:4b"
echo.
echo Or set environment variable:
echo   set OLLAMA_MODEL=flashcard-qwen3:4b
echo.
echo Then restart your server:
echo   python main_optimized.py
echo.
pause
