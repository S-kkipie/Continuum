from fastapi import FastAPI

from continuum_api.routes import capture, health, internal

app = FastAPI(title="Continuum API")
app.include_router(health.router)
app.include_router(internal.router)
app.include_router(capture.router)


def serve() -> None:
    import uvicorn

    uvicorn.run("continuum_api.main:app", host="0.0.0.0", port=8000)
