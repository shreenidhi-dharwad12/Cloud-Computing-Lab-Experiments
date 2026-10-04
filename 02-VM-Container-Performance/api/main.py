from fastapi import FastAPI

app = FastAPI(title="VM vs Container Performance API")

@app.get("/")
def root():
    return {"message": "VM vs Container Performance API"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/compute")
def compute():
    total = sum(range(1, 100001))
    return {"result": total}
