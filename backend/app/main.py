from fastapi import FastAPI

app = FastAPI(title="Findipend")


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
