import json
import os
import pandas as pd

# Load the evaluation results from the JSONL file
file_path = 'eval_results.jsonl'
if os.path.exists(file_path):
    with open(file_path) as f:
        data = [json.loads(line) for line in f]

    # Flatten the list of dictionaries into a single DataFrame
    flattened_data = []
    for entry in data:
        flattened_data.extend(entry)  # Since entry is already a list of dictionaries

    df = pd.DataFrame(flattened_data)

    # Print the columns and the first few rows of the DataFrame
    print("Columns in the DataFrame:", df.columns)
    print("DataFrame head:")
    print(df.head())

    # Check if the required columns exist
    required_columns = ['gpt_relevance', 'gpt_fluency', 'gpt_coherence', 'gpt_groundedness']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        print(f"Missing columns: {missing_columns}")
    else:
        # Calculate the average scores for each criterion
        avg_relevance = df['gpt_relevance'].mean()
        avg_fluency = df['gpt_fluency'].mean()
        avg_coherence = df['gpt_coherence'].mean()
        avg_groundedness = df['gpt_groundedness'].mean()

        # Calculate the overall average score
        overall_avg = (avg_relevance + avg_fluency + avg_coherence + avg_groundedness) / 4

        # Print the overall average score (used for setting GitHub Actions output)
        print(f'::set-output name=overall_avg::{overall_avg}')

        # Optionally, print the average scores to check manually
        print(f'Average GPT Relevance Score: {avg_relevance}')
        print(f'Average GPT Fluency Score: {avg_fluency}')
        print(f'Average GPT Coherence Score: {avg_coherence}')
        print(f'Average GPT Groundedness Score: {avg_groundedness}')
        print(f'Overall Average GPT Score: {overall_avg}')

else:
    print(f"File not found: {file_path}")
