# PTC (Pitch to the Panel) Project Runner
# This will start BOTH backend and frontend in separate windows.

Write-Host "🚀 Starting Pitch to the Panel Hybrid System..." -ForegroundColor Cyan

# 1. Start Backend
Write-Host "🔌 Starting Backend with Uvicorn (Port 8000)..." -ForegroundColor Yellow
Start-Process "cmd.exe" -ArgumentList "/k", "cd backend && venv\Scripts\python.exe -m uvicorn main:app --port 8000 --reload"

# 2. Wait a second for backend to initiate
Start-Sleep -Seconds 2

# 3. Start Frontend
Write-Host "🌐 Starting Frontend with NPM (Port 3000)..." -ForegroundColor Green
Start-Process "cmd.exe" -ArgumentList "/k", "cd frontend && npm run dev"

Write-Host "✅ Both servers are launching in new windows!" -ForegroundColor Cyan
Write-Host "Backend: http://localhost:8000"
Write-Host "Frontend: http://localhost:3000"
