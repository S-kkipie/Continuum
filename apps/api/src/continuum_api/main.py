from fastapi import FastAPI

from continuum_api.routes import health

app = FastAPI(title="Continuum API")
app.include_router(health.router)
