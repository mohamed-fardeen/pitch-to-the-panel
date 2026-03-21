@echo off
echo 🚀 Starting Pitch to the Panel Hybrid System...

:: Start Backend
echo 🔌 Starting Backend...
start cmd /k "cd backend && venv\Scripts\python.exe -m uvicorn main:app --port 8000 --reload"

:: Wait a moment
timeout /t 2 /nobreak > nul

:: Start Frontend
echo 🌐 Starting Frontend...
start cmd /k "cd frontend && npm run dev"

echo ✅ Both servers are launching!
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
pause
