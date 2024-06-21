# https://github.com/Azure-Samples/contoso-chat/blob/may-2024-updates/evaluations/evaluate-chat-flow-sdk.ipynb
import os
import json
import concurrent.futures
from pathlib import Path
from datetime import datetime
from promptflow.core import AzureOpenAIModelConfiguration
from promptflow.evals.evaluate import evaluate
from api.evaluate.evaluators import ArticleEvaluator
from api.agents.orchestrator import write_article

from dotenv import load_dotenv

load_dotenv()
folder = Path(__file__).parent.absolute().as_posix()

def evaluate_aistudio(model_config, data_path):
     
    # create unique id for each run with date and time
    run_prefix = datetime.now().strftime("%Y%m%d%H%M%S")
    run_id = f"{run_prefix}_chat_evaluation_sdk"    
    print(run_id)

    result = evaluate(
        evaluation_name=run_id,
        data=data_path,
        evaluators={
            "article": ArticleEvaluator(model_config),
        },
        evaluator_config={
            "defaults": {
                "query": "${data.query}",
                "response": "${data.response}",
                "context": "${data.context}",
            },
        },
    )
    return result

def evaluate_data(model_config, data_path):
    writer_evaluator = ArticleEvaluator(model_config)

    data = []
    with open(data_path) as f:
        for line in f:
            data.append(json.loads(line))

    results = []
    for row in data:
        result = writer_evaluator(query=row["query"], context=row["context"], response=row["response"])
        print("Evaluation results: ", result)
        results.append(result)

    return results

def run_orchestrator(request, instructions):
    query = {"request": request, "instructions": instructions}
    context = {}
    response = None

    for result in write_article(request, instructions):
        if result[0] == "researcher":
            context['research'] = result[1]
        if result[0] == "products":
            context['products'] = result[1]
        if result[0] == "writer":
            response = result[1]
    
    return {
        "query": json.dumps(query), 
        "context": json.dumps(context), 
        "response": json.dumps(response),
    }

def evaluate_orchestrator(model_config, data_path):
     
     
    writer_evaluator = ArticleEvaluator(model_config)

    data = []
    with open(data_path) as f:
        for line in f:
            data.append(json.loads(line))

    eval_data = []
    eval_results = []

    results = []
    futures = []
    def evaluate_row(request, instructions):
        result = { "request": request }
        print("Running orchestrator...")
        eval_data = run_orchestrator(request, instructions)
        print("Evaluating results...")
        eval_result = writer_evaluator(query=eval_data["query"], context=eval_data["context"], response=eval_data["response"])
        result.update(eval_result)
        print("Evaluation results: ", eval_result)
        eval_results.append(result)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        for row in data:
            futures.append(executor.submit(evaluate_row, row["request"], row["instructions"]))
        for future in futures:
            results.append(future.result())

    # write out eval data to a file so we can re-run evaluation on it
    with jsonlines.open(folder + '/eval_data.jsonl', 'w') as writer:
        for row in eval_data:
            writer.write(row)

    import pandas as pd

    print("Evaluation summary:\n")
    results_df = pd.DataFrame.from_dict(eval_results)
    print(results_df)

    mean_df = results_df.drop("request", axis=1).mean()
    print("\nAverage scores:")
    print(mean_df)

    results_df.to_markdown(folder + '/eval_results.md')
    with open(folder + '/eval_results.md', 'a') as file:
        file.write("\n\nAverages scores:\n\n")
    mean_df.to_markdown(folder + '/eval_results.md', 'a')

    with jsonlines.open(folder + '/eval_results.jsonl', 'w') as writer:
        writer.write(eval_results)
    print(f"::set-output name=gpt_relevance::{mean_df['gpt_relevance']}")
    print(f"::set-output name=gpt_fluency::{mean_df['gpt_fluency']}")
    print(f"::set-output name=gpt_coherence::{mean_df['gpt_coherence']}")
    print(f"::set-output name=gpt_groundedness::{mean_df['gpt_groundedness']}")

    return eval_results

if __name__ == "__main__":
    import time
    import jsonlines
    
    # Initialize Azure OpenAI Connection
    model_config = AzureOpenAIModelConfiguration(
        azure_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT_NAME_4o"],   
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"]
    )

    start=time.time()
    print(f"Starting evaluate...")
    print(os.environ["BING_SEARCH_ENDPOINT"])
    print("value: ", os.environ["BING_SEARCH_KEY"], len(os.environ["BING_SEARCH_KEY"]))
    eval_result = evaluate_orchestrator(model_config, data_path=folder +"/eval_inputs.jsonl")

    end=time.time()
    print(f"Finished evaluate in {end - start}s")

