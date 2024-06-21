import json
import os
import requests
import sys
import urllib.parse

from promptflow.tracing import trace
from promptflow.core import Prompty, AzureOpenAIModelConfiguration

from dotenv import load_dotenv
from pathlib import Path

import base64

folder = Path(__file__).parent.absolute().as_posix()
load_dotenv()

#bing does not currently support managed identity
BING_SEARCH_ENDPOINT = os.environ["BING_SEARCH_ENDPOINT"]
BING_SEARCH_KEY = os.environ["BING_SEARCH_KEY"]
BING_HEADERS = {"Ocp-Apim-Subscription-Key": BING_SEARCH_KEY}


def _make_endpoint(endpoint, path):
    """Make an endpoint URL"""
    return f"{endpoint}{'' if endpoint.endswith('/') else '/'}{path}"


def _make_request(path, params=None):
    """Make a request to the API"""
    endpoint = _make_endpoint(BING_SEARCH_ENDPOINT, path)
    response = requests.get(endpoint, headers=BING_HEADERS, params=params)
    items = response.json()
    return items


def find_information(query, market="en-US"):
    """Find information using the Bing Search API"""
    params = {"q": query, "mkt": market, "count": 5}
    items = _make_request("v7.0/search", params)
    pages = [
        {"url": a["url"], "name": a["name"], "description": a["snippet"]}
        for a in items["webPages"]["value"]
    ]
    # check if relatedsearches exists
    if "relatedSearches" not in items:
        return {"pages": pages, "related": []}
    
    # else add related searching
    related = [a["text"] for a in items["relatedSearches"]["value"]]
    return {"pages": pages, "related": related}


def find_entities(query, market="en-US"):
    """Find entities using the Bing Entity Search API"""
    params = "?mkt=" + market + "&q=" + urllib.parse.quote(query)
    items = _make_request(f"v7.0/entities{params}")
    entities = []
    if "entities" in items:
        entities = [
            {"name": e["name"], "description": e["description"]}
            for e in items["entities"]["value"]
        ]
    return entities

def find_news(query, market="en-US"):
    """Find images using the Bing News Search API"""
    params = {"q": query, "mkt": market, "count": 5}
    items = _make_request("v7.0/news/search", params)
    articles = [
        {
            "name": a["name"],
            "url": a["url"],
            "description": a["description"],
            "provider": a["provider"][0]["name"],
            "datePublished": a["datePublished"],
        }
        for a in items["value"]
    ]
    return articles

@trace
def execute(request: str, instructions: str, feedback: str = ""):
    """Assign a research task to a researcher"""
    functions = {
        "find_information": find_information,
        "find_entities": find_entities,
        "find_news": find_news,
    }

    # create path to prompty file
    configuration = AzureOpenAIModelConfiguration(
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME_4o"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
    )
    override_model = {
        "configuration": configuration,
        "parameters": {"max_tokens": 512}
    }
    prompty_obj = Prompty.load(folder + "/researcher.prompty", model=override_model)
    try:
        results = prompty_obj(request=request, instructions=instructions, feedback=feedback)
        print("Raw results:", results)
        
        # Convert string response to dictionary if necessary
        if isinstance(results, str):
            results = json.loads(results)
    except Exception as e:
        print(f"Error processing the response: {str(e)}")
        return []

    # Validate the result as the expected format
    if not isinstance(results, dict) or "tool_calls" not in results:
        feedback = "Unexpected response from the researcher. Result: " + str(results)
        print(feedback)
        return []
    research = []
    for tool in results['tool_calls']:
        if not isinstance(tool, dict):
            print(f"Unexpected tool format: {tool}")
            continue

        if 'function' not in tool or 'arguments' not in tool:
            print(f"'function' or 'arguments' key missing in tool: {tool}")
            continue

        function_name = tool['function']
        try:
            args = json.loads(tool['arguments'])
        except json.JSONDecodeError as e:
            print(f"Error decoding arguments for function {function_name}: {str(e)}")
            continue

        if function_name not in functions:
            print(f"Function {function_name} not found in available functions.")
            continue

        try:
            r = functions[function_name](**args)
        except Exception as e:
            print(f"Error executing function {function_name} with arguments {args}: {str(e)}")
            continue
        
        research.append(
            {"id": tool.get('id', None), "function": function_name, "arguments": args, "result": r}
        )

    return research


def process(research):
    """Process the research results"""
    # process web searches
    web = filter(lambda r: r["function"] == "find_information", research)
    web_items = [page for web_item in web for page in web_item["result"]["pages"]]

    # process entity searches
    entities = filter(lambda r: r["function"] == "find_entities", research)
    entity_items = [
        {"url": "None Available", "name": it["name"], "description": it["description"]}
        for e in entities
        for it in e["result"]
    ]

    # process news searches
    news = filter(lambda r: r["function"] == "find_news", research)
    news_items = [
        {
            "url": article["url"],
            "name": article["name"],
            "description": article["description"],
        }
        for news_item in news
        for article in news_item["result"]
    ]
    return {
        "web": web_items,
        "entities": entity_items,
        "news": news_items,
    }


def research(request, instructions, feedback: str = ""):
    r = execute(request=request, instructions=instructions, feedback=feedback)
    p = process(r)
    return p


if __name__ == "__main__":
    # Get command line arguments

    #context = "Can you find the latest camping trends and what folks are doing in the winter?"
    context = sys.argv[1]
    instructions = sys.argv[2]

    r = execute(context=context, instructions=instructions, feedback="")
    processed = process(r)
    print(json.dumps(processed, indent=2))
