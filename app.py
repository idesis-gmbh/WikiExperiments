from time import time

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from config import WIKI_NAME
from search import search_query
from explore import (
    shortest_path,
    redirect_statistics,
    degree_distribution,
    top_pages_by_pagerank,
)

templates = Jinja2Templates(directory="templates")


def base_context(**kwargs):
    return {"wiki_name": WIKI_NAME[:-4], **kwargs}


async def search(request):
    query = request.query_params.get("query", "")
    start = time()
    results = search_query(query) if query else []
    for result in results:
        tokens = result["text"].split()
        result["text"] = " ".join(tokens[:64]) + (" ..." if len(tokens) > 64 else "")
    end = time()
    print(f"Searched: {end - start:.2f} seconds")
    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context=base_context(query=query, results=results),
    )


async def path(request):
    source = request.query_params.get("source", "")
    target = request.query_params.get("target", "")
    result = shortest_path(source, target) if source and target else None
    return templates.TemplateResponse(
        request=request,
        name="path.html",
        context=base_context(source=source, target=target, result=result),
    )


async def degrees(request):
    distribution = degree_distribution()
    return templates.TemplateResponse(
        request=request,
        name="degrees.html",
        context=base_context(distribution=distribution),
    )


async def redirects(request):
    stats = redirect_statistics()
    return templates.TemplateResponse(
        request=request,
        name="redirects.html",
        context=base_context(stats=stats),
    )


async def pagerank(request):
    ns = int(request.query_params.get("ns", 0))
    pages = top_pages_by_pagerank(ns)
    return templates.TemplateResponse(
        request=request,
        name="pagerank.html",
        context=base_context(pages=pages, ns=ns),
    )


app = Starlette(
    debug=True,
    routes=[
        Route("/", search),
        Route("/path", path),
        Route("/degrees", degrees),
        Route("/redirects", redirects),
        Route("/pagerank", pagerank),
    ],
)
