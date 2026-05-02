from starlette.applications import Starlette
from starlette.routing import Route
from starlette.templating import Jinja2Templates

from config import WIKI_NAME
from search import search_query


templates = Jinja2Templates(directory="templates")


async def homepage(request):
    query = request.query_params.get("q", "")
    _, _, results = search_query(query) if query else (None, None, [])
    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={"wiki_name": WIKI_NAME[:-4], "query": query, "results": results},
    )


app = Starlette(
    debug=True,
    routes=[
        Route("/", homepage),
    ],
)
