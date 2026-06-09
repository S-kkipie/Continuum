from fastapi import FastAPI

from continuum_api.routes import health

app = FastAPI(title="Continuum API")
app.include_router(health.router)


def serve() -> None:
    import uvicorn

    uvicorn.run("continuum_api.main:app", host="0.0.0.0", port=8000)
