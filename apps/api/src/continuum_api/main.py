from fastapi import FastAPI

from continuum_api.routes import health, internal

app = FastAPI(title="Continuum API")
app.include_router(health.router)
app.include_router(internal.router)


def serve() -> None:
    import uvicorn

    uvicorn.run("continuum_api.main:app", host="0.0.0.0", port=8000)
