import traceback
import pandas as pd
import time
import re

def process_chunk(chunk, client, system_message, model_name, global_sleep_time, max_retries, prompt_task_header):
    chunk_prompt = prompt_task_header
    for index, row in chunk.iterrows():
        chunk_prompt += (
            f"Index: {row['Index']} PMID: {row['PMID']} Sentence: {row['Sentence']} Gene Name: {row['Gene Name']} "
            f"Gene Type: {row['Gene Type']} Gene ID: {row['Gene ID']} Biomedical Entity: {row['Biomedical Entity']}"
        )

    messages = [
        system_message,
        {"role": "user", "content": chunk_prompt}
    ]

    retries = 0
    while retries < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.7,
                max_tokens=30000,
            )

            if hasattr(completion, 'choices') and len(completion.choices) > 0:
                completion_message = completion.choices[0].message.content
                if completion_message:
                    return completion_message
                else:
                    retries += 1
                    if retries < max_retries:
                        time.sleep(2 ** retries)
                    else:
                        print(f"Exceeded maximum retries for chunk.")
            break
        except Exception as e:
            error_message = str(e)
            if 'rate_limit_reached_error' in error_message:
                retries += 1
                wait_time = 2 ** retries
                if retries < max_retries:
                    time.sleep(wait_time)
            else:
                retries += 1
                if retries < max_retries:
                    time.sleep(2 ** retries)

        time.sleep(global_sleep_time)

    return None


def process_data(input_txt_path, output_txt_path, client, system_message, model_name, global_sleep_time,
                 max_retries, prompt_task_header):
    df = pd.read_csv(input_txt_path, delimiter='\t')
    chunk_size = 10
    chunks = [df.iloc[i:i + chunk_size].copy() for i in range(0, len(df), chunk_size)]

    chunk_result = []

    for chunk_index, chunk in enumerate(chunks):
        completion_message = process_chunk(chunk, client, system_message, model_name, global_sleep_time,
                                           max_retries, prompt_task_header)
        # 打印每个返回结果
        print(f"Chunk {chunk_index + 1} completion message:")
        print(completion_message)  # 打印完成消息
        chunk_result.extend(completion_message)

    with open(output_txt_path, 'w', encoding='utf-8') as f:
        for item in chunk_result:
            f.write(item.strip())


def process_files(input_txt_path, output_csv_path, original_uv_path):
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
                                  prompt_task_header, client, max_retries, global_sleep_time, system_message,
                                  model_name):
    iteration = 1
    generated_csv_path = initial_generated_csv_path

    while True:
        try:
            # Read original and generated data
            original_df = pd.read_csv(original_txt_path, sep='\t')
            generated_df = pd.read_csv(generated_csv_path)

            # Ensure 'Index' columns have consistent types
            original_df['Index'] = original_df['Index'].astype(str)
            generated_df['Index'] = generated_df['Index'].astype(str)

            # Find missing rows
            missing_rows_df = original_df[~original_df['Index'].isin(generated_df['Index'])]

            # If no missing rows, finalize and exit loop
            if missing_rows_df.empty:
                print("No missing rows found. Final combined file saved.")
                generated_df = generated_df.sort_values(by='Index')
                generated_df.to_csv(combined_csv_path, index=False)
                break

            # Save missing rows to an intermediate file
            missing_output_txt_path = f"{prefix}_missing_rows-{iteration}.txt"
            missing_rows_df.to_csv(missing_output_txt_path, sep='\t', index=False)

            # Define intermediate file paths
            temp_missing_output_txt_path = f"{prefix}_temp_missing-{iteration}.txt"
            missing_output_csv_path = f"{prefix}_missing_rows-{iteration}.csv"

            # Process missing data
            process_data(missing_output_txt_path, temp_missing_output_txt_path, client, system_message, model_name,
                         global_sleep_time, max_retries, prompt_task_header)
            process_files(temp_missing_output_txt_path, missing_output_csv_path, missing_output_txt_path)

            # Read and combine processed data
            processed_missing_rows_df = pd.read_csv(missing_output_csv_path)
            combined_df = pd.concat([processed_missing_rows_df, generated_df], ignore_index=True)

            # Ensure 'Index' column consistency
            combined_df['Index'] = combined_df['Index'].astype(str)

            # Log and handle duplicates
            if combined_df.duplicated(['Index'], keep=False).any():
                print("Duplicates found after merging:")
                print(combined_df[combined_df.duplicated(['Index'], keep=False)])

            # Remove duplicates and sort
            combined_df.drop_duplicates(subset=['Index'], inplace=True)

            combined_df_sorted = combined_df.sort_values(by='Index')
            combined_df_sorted.reset_index(drop=True, inplace=True)

            # Save combined results
            combined_df_sorted.to_csv(combined_csv_path, index=False)

            # Update generated CSV path for next iteration
            generated_csv_path = combined_csv_path
            iteration += 1

        except Exception as e:
            print(f"Error during iteration {iteration}: {e}")
            print(traceback.format_exc())
            break

    print("All missing rows processed.")