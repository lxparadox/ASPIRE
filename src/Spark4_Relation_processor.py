import pandas as pd
import time
from sparkai.llm.llm import ChunkPrintHandler
from sparkai.core.messages import ChatMessage
import re


def process_chunk(chunk, prompt_task_header, spark, max_retries, global_sleep_time):
    """Process data blocks and generate responses to API requests"""
    # Construct task prompt
    chunk_prompt = prompt_task_header
    for index, row in chunk.iterrows():
        chunk_prompt += (
            f"Index: {row['Index']} PMID: {row['PMID']} Sentence: {row['Sentence']} Gene Name: {row['Gene Name']} "
            f"Gene Type: {row['Gene Type']} Gene ID: {row['Gene ID']} Biomedical Entity: {row['Biomedical Entity']}\n"
        )

    # Prepare message list
    messages = [ChatMessage(role="user", content=chunk_prompt)]
    handler = ChunkPrintHandler()

    retries = 0
    while retries < max_retries:
        try:
            # Call new API to get response using SPARK model
            response = spark.generate([messages], callbacks=[handler])
            print(f"API response for chunk: {response}")

            if hasattr(response, 'generations') and len(response.generations) > 0:
                completion_message = response.generations[0][0].text
                print(f"Received completion for chunk: {completion_message}")
                return completion_message
            else:
                print(f"Warning: No 'content' found in completion response for chunk")
                retries += 1
                if retries < max_retries:
                    time.sleep(2 ** retries)
                else:
                    print(f"Exceeded maximum retries for chunk.")
        except Exception as e:
            error_message = str(e)
            print(f"An error occurred for chunk: {error_message}")
            retries += 1
            if retries < max_retries:
                time.sleep(2 ** retries)
            else:
                print(f"Exceeded maximum retries for chunk.")

        # Increase global sleep time
        print(f"Sleeping for {global_sleep_time} seconds to avoid rate limit...")
        time.sleep(global_sleep_time)

    return None


def process_data(input_txt_path, output_txt_path, prompt_task_header, spark, max_retries, global_sleep_time):
    """read the file and process data"""
    # read the TXT file
    df = pd.read_csv(input_txt_path, delimiter='\t')

    # split into 10
    chunk_size = 10
    chunks = [df.iloc[i:i + chunk_size].copy() for i in range(0, len(df), chunk_size)]

    chunk_result = []

    for chunk_index, chunk in enumerate(chunks):
        # process every data chunk
        completion_message = process_chunk(chunk, prompt_task_header, spark, max_retries, global_sleep_time)
        chunk_result.append(completion_message)

    # write the results into the output file
    with open(output_txt_path, 'w', encoding='utf-8') as f:
        for item in chunk_result:
            if item:
                f.write(item.strip() + "\n")


def process_files(input_txt_path, output_csv_path, original_uv_path):
    """process the file and output as csv format"""

    original_uv = pd.read_csv(original_uv_path, sep='\t')

    results = []

    with open(input_txt_path, 'r', encoding='utf-8') as infile:
        for line in infile:
            matches = re.findall(r'\{\s*"Index":\s*"?(\d+)"?\s*,\s*"answer":\s*"?([TF])"?\s*\}', line)
            for match in matches:
                index, answer = match
                index = int(index)

                if index in original_uv['Index'].values:
                    corresponding_row = original_uv[original_uv['Index'] == index].copy()
                    corresponding_row['answer'] = answer
                    results.append(corresponding_row)

    if results:
        final_df = pd.concat(results, ignore_index=True)
        final_df.to_csv(output_csv_path, index=False)
        print(f"Results written to {output_csv_path}")
    else:
        print("No valid results found.")


def process_missing_rows_and_loop(original_txt_path, initial_generated_csv_path, combined_csv_path, prefix,
                                  prompt_task_header, spark, max_retries, global_sleep_time):
    """process the missing columns until all done"""
    iteration = 1
    generated_csv_path = initial_generated_csv_path

    while True:
        try:
            # Read original data and generated CSV file
            original_df = pd.read_csv(original_txt_path, sep='\t')
            generated_df = pd.read_csv(generated_csv_path)

            # Ensure Index columns have consistent types
            original_df['Index'] = original_df['Index'].astype(str)
            generated_df['Index'] = generated_df['Index'].astype(str)

            # Check for missing rows
            missing_rows_df = original_df[~original_df['Index'].isin(generated_df['Index'])]

            if missing_rows_df.empty:
                print("No missing rows found. Final combined file saved.")
                generated_df = generated_df.sort_values(by='Index')  # Sort final DataFrame by Index
                generated_df.to_csv(combined_csv_path, index=False)
                break

            # Save missing rows to file
            missing_output_txt_path = f"{prefix}_missing_rows-{iteration}.txt"
            missing_rows_df.to_csv(missing_output_txt_path, sep='\t', index=False)

            # Process missing row data
            temp_missing_output_txt_path = f"{prefix}_temp_missing-{iteration}.txt"
            missing_output_csv_path = f"{prefix}_missing_rows-{iteration}.csv"

            process_data(missing_output_txt_path, temp_missing_output_txt_path, prompt_task_header, spark,
                         max_retries, global_sleep_time)
            process_files(temp_missing_output_txt_path, missing_output_csv_path, missing_output_txt_path)

            # Read results of processing missing rows
            processed_missing_rows_df = pd.read_csv(missing_output_csv_path)

            # Merge currently generated missing row CSV file with previously generated file
            combined_df = pd.concat([processed_missing_rows_df, generated_df], ignore_index=True)

            # Ensure Index column is consistently a string in the combined DataFrame
            combined_df['Index'] = combined_df['Index'].astype(str)

            # Check for duplicate rows after merging
            if combined_df.duplicated(['Index'], keep=False).any():
                print("Duplicates found after merging:")
                print(combined_df[combined_df.duplicated(['Index'], keep=False)])

            # Remove duplicate rows
            combined_df.drop_duplicates(subset=['Index'], inplace=True)

            # Sort by Index column
            combined_df_sorted = combined_df.sort_values(by='Index')

            # Reset index
            combined_df_sorted.reset_index(drop=True, inplace=True)

            # Output results to a new CSV file
            combined_df_sorted.to_csv(combined_csv_path, index=False)

            # Update generated CSV file path to the latest merged file
            generated_csv_path = combined_csv_path
            iteration += 1

        except Exception as e:
            print(f"Error during iteration {iteration}: {e}")
            break

    print("All missing rows processed.")