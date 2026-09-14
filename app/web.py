from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Telegram Docker Deploy Manager")

@app.get("/")
async def root():
    return JSONResponse(
        content={
            "status": "ok",
            "service": "telegram-docker-deploy-manager"
        }
    )

@app.get("/health")
async def health():
    return JSONResponse(
        content={
            "status": "healthy"
        }
    )
