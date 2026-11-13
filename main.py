
from fastapi import FastAPI


app = FastAPI()


@app.get("/")
def read_root():
    return {
        "message": "Enterprise AI Knowledge & Workflow Agent",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "application": "Enterprise AI Knowledge & Workflow Agent",
    }
