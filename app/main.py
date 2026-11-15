"""Thin FastAPI shell. All the science happens offline in pipeline/; this serves pages + data.

Run:  uvicorn app.main:app --reload
"""
import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(BASE, "static", "data", "index.json")

app = FastAPI(title="Earth, by ear")
URLS = {"assets": "/static", "home": "/", "story": "/story"}
app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE, "templates"))


def load_index() -> dict:
    if not os.path.exists(INDEX):
        return {"datasets": []}
    with open(INDEX) as f:
        return json.load(f)


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"page": "home", **URLS})


@app.get("/story")
def story(request: Request):
    return templates.TemplateResponse(request, "story.html",
                                      {"page": "story", "datasets": load_index()["datasets"], **URLS})


@app.get("/api/datasets")
def api_datasets():
    return JSONResponse(load_index())


@app.get("/healthz")
def healthz():
    return {"ok": True, "datasets": len(load_index()["datasets"])}
