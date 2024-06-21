import os
import json
from threading import Thread
from opentelemetry import trace
from promptflow.client import load_flow
from opentelemetry.trace import set_span_in_context
from promptflow.core import AzureOpenAIModelConfiguration
from promptflow.evals.evaluators import RelevanceEvaluator, GroundednessEvaluator, FluencyEvaluator, CoherenceEvaluator



# original_init = GroundednessEvaluator.__init__

# def patched_init(self, model_config: AzureOpenAIModelConfiguration):
#     if model_config.api_version is None:
#         model_config.api_version = "2024-02-15-preview"

#     prompty_model_config = {"configuration": model_config}
#     # Update the file path to point to your custom directory
#     current_dir = os.path.dirname(__file__)
#     prompty_path = os.path.join(current_dir, "custom_groundness.prompty")
#     print(f"Loading prompt file from: {prompty_path}")  # Print statement to check which prompt file is being used

#     self._flow = load_flow(source=prompty_path, model=prompty_model_config)

# GroundednessEvaluator.__init__ = patched_init


def patch_evaluator(evaluator_class, prompty_file_name):
    original_init = evaluator_class.__init__

    def patched_init(self, model_config: AzureOpenAIModelConfiguration):
        original_init(self, model_config)  # Call the original __init__
        
        if model_config.api_version is None:
            model_config.api_version = "2024-02-15-preview"

        prompty_model_config = {"configuration": model_config}
        current_dir = os.path.dirname(__file__)
        prompty_path = os.path.join(current_dir, prompty_file_name)

        print(f"Loaded prompt file from: {prompty_path}")
        self._flow = load_flow(source=prompty_path, model=prompty_model_config)

    evaluator_class.__init__ = patched_init


patch_evaluator(RelevanceEvaluator, "custom_relevance.prompty")
patch_evaluator(GroundednessEvaluator, "custom_groundness.prompty")
patch_evaluator(FluencyEvaluator, "custom_fluency.prompty")
patch_evaluator(CoherenceEvaluator, "custom_coherence.prompty")

class ArticleEvaluator:
    def __init__(self, model_config):
        self.evaluators = [
            RelevanceEvaluator(model_config),
            FluencyEvaluator(model_config),
            CoherenceEvaluator(model_config),
            GroundednessEvaluator(model_config),
        ]

    def __call__(self, *, query: str, context: str, response: str, **kwargs):
        output = {}
        for evaluator in self.evaluators:
            result = evaluator(
                question=query,
                context=context,
                answer=response,
            )
            output.update(result)
        return output

def evaluate_article(data, trace_context):
    print("starting offline evals")

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("run_evaluators", context=trace_context) as span:
        span.set_attribute("inputs", json.dumps(data))
        configuration = AzureOpenAIModelConfiguration(
            azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME_4o"],
            api_version=os.environ["AZURE_OPENAI_API_VERSION"],
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"]
        )
        evaluator = ArticleEvaluator(configuration)
        print("query",data['query'])

        print("context",data['context'])
        print("response",data['response'])
        results = evaluator(query=data['query'], context=data['context'], response=data['response'])
        results_json = json.dumps(results)
        span.set_attribute("output", results_json)

        print("results: ", results_json)
        

def evaluate_article_in_background(request, instructions, research, products, article):
    eval_data = {
        "query": json.dumps({
            "request": request,
            "instructions": instructions,
        }),
        "context": json.dumps({
            "research": research,
            "products": products,
        }),
        "response": json.dumps(article)
    }

    # propagate trace context to the new thread
    span = trace.get_current_span()
    trace_context = set_span_in_context(span)
    thread = Thread(target=evaluate_article, args=(eval_data, trace_context,))
    thread.start()
