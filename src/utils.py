import pandas as pd
import xml.etree.ElementTree as ET
import requests
import time
import re
import os
import csv
import mygene
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import OrderedDict
from ete3 import NCBITaxa


def retrieve_pubmed_data(output_file, start_date, end_date, terms):
    query = ' OR '.join([f'("{term}"[Title/Abstract] OR "{term.lower()}"[Title/Abstract])' for term in terms])
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

    with open(output_file, 'w') as file:
        total_count = 0
        current_start = start_date
        while current_start < end_date:
            current_end = current_start + timedelta(days=30)
            if current_end > end_date:
                current_end = end_date

            start_str = current_start.strftime('%Y/%m/%d')
            end_str = current_end.strftime('%Y/%m/%d')

            params = {
                'db': 'pubmed',
                'term': query,
                'mindate': start_str,
                'maxdate': end_str,
                'datetype': 'epdt',
                'retmax': '9999',
                'retmode': 'xml',
                'tool': 'pubmed_retrieve',
                'email': '610439560@qq.com'
            }

            response = requests.get(base_url, params=params)
            xml_content = response.text
            root = ET.fromstring(xml_content)

            count = int(root.findtext('.//Count'))
            print(f"{count} related articles from {start_str} to {end_str} had been found.")
            total_count += count

            if count > 0:
                for id_node in root.findall('.//Id'):
                    file.write(id_node.text + '\n')

            current_start = current_end
            time.sleep(10)

    print(f"Finished retrieving and results saved to {output_file}.\nA total of {total_count} article PMID numbers were recorded.")

    return total_count

def retrieve_annotations(input_file, output_file_prefix):
    with open(input_file, 'r', encoding='utf-8') as file:
        pmids = [line.strip() for line in file.readlines()]

    failed_pmids = []
    batch_size = 100
    total_pmids = len(pmids)
    successful_requests = 0
    xml_count = 0
    max_pmids_per_file = 1000
    output_file_index = 1
    output_file = f'{output_file_prefix}{output_file_index}.xml'

    with open(output_file, 'w', encoding='utf-8') as file:
        file.write('<?xml version="1.0" encoding="UTF-8"?>\n<PubTatorData>\n')

        for i in range(0, len(pmids), batch_size):
            batch_pmids = pmids[i:i + batch_size]
            pmid_query = ','.join(batch_pmids)
            max_retries = 3
            retries = 0

            while retries < max_retries:
                try:
                    url = f"https://www.ncbi.nlm.nih.gov/research/pubtator3-api/publications/export/biocxml?pmids={pmid_query}&full=true"
                    #print(f"Requesting URL: {url}")

                    response = requests.get(url)
                    #print(f"Response status code: {response.status_code}")

                    if response.status_code == 200:
                        #print(f"Response content (first 500 chars): {response.text[:500]}")

                        start_index = response.text.find('<collection')
                        if start_index != -1:
                            xml_part = response.text[start_index:]
                            file.write(xml_part)
                            successful_requests += 1
                            xml_count += xml_part.count('<id>')

                            #print(f"Processed {len(batch_pmids)} PMIDs, currently have {xml_count} in the current file.")
                            print(f"Processing {len(batch_pmids)} papers and a total of {xml_count} papers had been processed.")

                            if xml_count >= max_pmids_per_file:
                                file.write('</PubTatorData>\n')
                                print(f"Created {output_file} with {xml_count} PMIDs.")
                                output_file_index += 1
                                output_file = f'{output_file_prefix}{output_file_index}.xml'
                                file = open(output_file, 'w', encoding='utf-8')
                                file.write('<?xml version="1.0" encoding="UTF-8"?>\n<PubTatorData>\n')
                                xml_count = 0

                        else:
                            print("XML content not found in response.")
                        break
                    else:
                        print(f"Unexpected status code: {response.status_code}")
                        raise Exception("Failed to retrieve data")

                except Exception as e:
                    print(f"Error for PMIDs: {pmid_query}, Retrying... ({retries + 1}/{max_retries})")
                    print(f"Error: {e}")
                    retries += 1
                    time.sleep(10)

            if retries == max_retries:
                failed_pmids.extend(batch_pmids)
                print(f"Failed after {max_retries} attempts for PMIDs: {pmid_query}")

        file.write('</PubTatorData>\n')
        print(f"Download {xml_count} related papers in XML format and save them in {output_file}.")

    failed_count = len(failed_pmids)
    successful_count = successful_requests

    if failed_pmids:
        with open('failed_pmids.txt', 'w', encoding='utf-8') as f:
            for pmid in failed_pmids:
                f.write(pmid + '\n')

    print(f"Finished retrieving annotations and saved to files.\nTotal papers processed: {total_pmids}\n"
          f"Successful requests: {successful_count}\nFailed requests: {failed_count}")
    return total_pmids  # 返回总 PMIDs 数量

def process_folder(folder_path):
    """Process all XML files in the folder using multithreading for speedup."""
    all_data = []
    xml_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith('.xml')]
    total_files = len(xml_files)
    alpha = 0.3  # EMA smoothing factor

    start_time = time.time()  # Record start time
    ema_time_per_file = None

    with ThreadPoolExecutor(max_workers=8) as executor:  # 8 is the number of threads, can adjust based on your CPU cores
        future_to_file = {executor.submit(process_single_file, filepath): filepath for filepath in xml_files}

        for index, future in enumerate(as_completed(future_to_file)):
            file_path = future_to_file[future]
            try:
                data = future.result()
                all_data.extend(data)
            except Exception as e:
                print(f"Error processing file {file_path}: {e}")

            # Calculate progress
            elapsed_time = time.time() - start_time  # Time elapsed
            files_processed = index + 1
            percent_complete = (files_processed / total_files) * 100

            # Estimate remaining time
            if files_processed > 0:
                current_time_per_file = elapsed_time / files_processed
                if ema_time_per_file is None:
                    ema_time_per_file = current_time_per_file
                else:
                    ema_time_per_file = alpha * current_time_per_file + (1 - alpha) * ema_time_per_file

                remaining_files = total_files - files_processed
                estimated_time_remaining = ema_time_per_file * remaining_files
            else:
                estimated_time_remaining = 0

            # Output progress information
            print(f"Processed {files_processed}/{total_files} files ({percent_complete:.2f}%)."
                  f"Estimated time remaining: {estimated_time_remaining:.2f} seconds")

    return all_data

def process_single_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            xml_content = file.read()
            results = extract_gene_info(xml_content)
            if not results:
                print(f"No results found in file: {filepath}")
            return results
    except Exception as e:
        print(f"Error processing file {filepath}: {e}")
        return []

def extract_gene_info(xml_content):
    try:
        tree = ET.ElementTree(ET.fromstring(xml_content))
    except ET.ParseError as e:
        print(f"Error parsing XML content: {e}")
        return []

    root = tree.getroot()
    results = []

    for document in root.findall('.//document'):
        # Priority: extract <infon key="article-id_pmid"> if available
        pmid_element = document.find(".//infon[@key='article-id_pmid']")
        if pmid_element is not None and pmid_element.text.isdigit():
            pmid = pmid_element.text
        else:
            # Fallback to <id> if <infon key="article-id_pmid"> is missing
            pmid_element = document.find('id')
            pmid = pmid_element.text if pmid_element is not None else 'N/A'

        for passage in document.findall('.//passage'):
            section_type_element = passage.find(".//infon[@key='section_type']")
            type_element = passage.find(".//infon[@key='type']")
            section_type = section_type_element.text if section_type_element is not None else None
            type = type_element.text if type_element is not None else None

            if (section_type in ['TITLE', 'ABSTRACT']) or (type in ['title', 'abstract']):
                text_element = passage.find('text')
                if text_element is not None:
                    text = text_element.text
                    passage_offset_element = passage.find('offset')
                    passage_offset = int(passage_offset_element.text) if passage_offset_element is not None else 0
                    sentences = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s', text)
                    sentence_offsets = []
                    current_offset = passage_offset
                    for sentence in sentences:
                        sentence_offsets.append((current_offset, current_offset + len(sentence)))
                        current_offset += len(sentence) + 1  # +1 for the space or punctuation

                    for annotation in passage.findall('annotation'):
                        annotation_type_element = annotation.find(".//infon[@key='type']")
                        if annotation_type_element is not None and annotation_type_element.text == 'Gene':
                            gene_name_element = annotation.find('text')
                            if gene_name_element is not None:
                                gene_name = gene_name_element.text
                                entity_id_element = annotation.find(".//infon[@key='identifier']")
                                entity_id = entity_id_element.text if entity_id_element is not None else 'N/A'
                                location_element = annotation.find('location')
                                if location_element is not None:
                                    gene_offset = int(location_element.attrib['offset'])
                                    gene_length = int(location_element.attrib['length'])
                                    gene_end_offset = gene_offset + gene_length

                                    for i, (start_offset, end_offset) in enumerate(sentence_offsets):
                                        if start_offset <= gene_offset < end_offset:
                                            sentence = sentences[i]
                                            # Look for the position of the gene in the sentence to ensure correct matching
                                            relative_offset = gene_offset - start_offset
                                            gene_pos_in_sentence = sentence.find(gene_name, relative_offset)
                                            if gene_pos_in_sentence != -1:
                                                start_offset_in_sentence = gene_pos_in_sentence
                                                end_offset_in_sentence = start_offset_in_sentence + len(gene_name)
                                                # Add extracted information to results
                                                results.append(
                                                    (pmid, sentence, gene_name, 'Gene', entity_id))
                                            break

    return results

def process_gene_id_column(input_filepath, output_filepath):
    """
    Clean and process Gene ID column in results file.
    - Remove rows with invalid Gene ID (None, empty, NA, or N/A).
    - Split rows with multiple Gene IDs into separate rows.
    - Reindex the processed rows sequentially.

    Parameters:
    - input_filepath (str): Path to the input file (results_all_gene.txt).
    - output_filepath (str): Path to save the processed file.
    """
    processed_lines = []
    with open(input_filepath, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    header = lines[0].strip()  # Preserve header
    processed_lines.append(header)

    for line in lines[1:]:  # Skip header line
        parts = line.strip().split('\t')

        if len(parts) < 6:  # Ensure there are enough columns
            #print(f"Skipping malformed line: {line.strip()}")
            continue

        # Extract Gene ID and validate it
        gene_id = parts[5].strip()
        if gene_id in ['', 'None', 'NA', 'N/A']:  # Include 'N/A' in invalid values
            continue  # Skip invalid rows

        # Split Gene IDs by semicolon
        gene_ids = [id.strip() for id in gene_id.split(';') if id.strip()]
        for single_gene_id in gene_ids:
            new_line = parts[:5] + [single_gene_id]  # Replace Gene ID with single ID
            processed_lines.append('\t'.join(new_line))

    # Reindex the processed lines
    reindexed_lines = [header]
    for index, line in enumerate(processed_lines[1:], start=1):  # Start reindexing from 1
        parts = line.split('\t')
        parts[0] = str(index)  # Replace the original index
        reindexed_lines.append('\t'.join(parts))

    # Save the reindexed data to the output file
    with open(output_filepath, 'w', encoding='utf-8') as file:
        file.write('\n'.join(reindexed_lines) + '\n')

    print(f"Processed and the original file saved to {output_filepath}")

def process_biomedical_entity_results(input_filepath, output_filepath, biomedical_entity_terms_lower):
    """Process results containing biomedical-related terms."""
    with open(input_filepath, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    biomedical_entity_results = []
    header = "Index\tPMID\tSentence\tGene Name\tGene Type\tGene ID\tBiomedical Entity\n"
    biomedical_entity_results.append(header)

    # Start the index counter at 1 for this file
    index_counter = 1

    for line in lines[1:]:  # Skip header
        parts = line.strip().split('\t')

        if len(parts) != 6:
            print(f"Skipping malformed line: {line.strip()}")
            continue

        _, pmid, sentence, gene_name, gene_type, gene_id = parts
        sentence_lower = sentence.lower()

        matches = []
        for term in biomedical_entity_terms_lower:
            if re.search(r'\b' + re.escape(term) + r'\b', sentence_lower):
                start_pos = sentence_lower.find(term)
                end_pos = start_pos + len(term)
                # Annotation position information
                # matches.append((sentence[start_pos:end_pos], f"{start_pos}#{end_pos}"))
                matches.append(sentence[start_pos:end_pos])

        if matches:
            matches.sort(key=lambda x: len(x), reverse=True)
            longest_entity = matches[0]
            biomedical_entity_results.append(
                f"{index_counter}\t{pmid}\t{sentence}\t{gene_name}\t{gene_type}\t{gene_id}\t{longest_entity}\n")
            index_counter += 1

    with open(output_filepath, 'w', encoding='utf-8') as file:
        file.writelines(biomedical_entity_results)

def save_results_to_file(results, output_filepath):
    unique_results = list(OrderedDict.fromkeys(results))
    with open(output_filepath, 'w', encoding='utf-8') as file:
        file.write("Index\tPMID\tSentence\tGene Name\tGene Type\tGene ID\n")
        for index, result in enumerate(unique_results, start=1):
            # Replace None values with an empty string
            result = [str(item) if item is not None else '' for item in result]
            file.write(f"{index}\t" + "\t".join(result) + '\n')

def filter_gene_ids(txt_file_path, csv_file_path, output_file_path):
    """
    compare the column of Gene ID between the txt and csv. Select the lines that didn't exist in the csv and save to the new txt.
    parameters：
        txt_file_path (str): the input txt file path
        csv_file_path (str): the input csv file path
        output_file_path (str): the output txt file path
    """
    # collect the Gene IDs in the CSV file
    csv_gene_ids = set()
    with open(csv_file_path, 'r', encoding='utf-8') as csv_file:
        # Attempt to automatically detect separators
        dialect = csv.Sniffer().sniff(csv_file.read(1024), delimiters=",\t")
        csv_file.seek(0)  # Reset the file pointer
        csv_reader = csv.reader(csv_file, dialect)

        next(csv_reader, None)  # 跳过表头
        for row in csv_reader:

            if len(row) > 5:  # 确保有第6列
                gene_id = row[5].strip()  # 去掉首尾空格
                csv_gene_ids.add(gene_id)

    # Iterate through the TXT file and filter lines whose Gene ID is not in the CSV file
    with open(txt_file_path, 'r', encoding='utf-8') as txt_file, \
            open(output_file_path, 'w', encoding='utf-8') as output_file:
        txt_reader = csv.reader(txt_file, delimiter='\t')
        header = next(txt_reader, None)
        output_file.write('\t'.join(header) + '\n')

        for row in txt_reader:

            if len(row) > 5:
                gene_id = row[5].strip()
                if gene_id not in csv_gene_ids:
                    output_file.write('\t'.join(row) + '\n')

    #print(f"Filtering completed, results have been saved to {output_file_path}")

def merge_and_clean_csv(input_files, output_file):
    """
    Merge multiple CSV files, remove duplicates based on specified columns, and reset index.
    """
    dataframes = [pd.read_csv(file) for file in input_files]
    merged_df = pd.concat(dataframes)

    # Remove duplicates based on specific columns
    columns_to_check = ['PMID', 'Sentence', 'Gene Name', 'Gene Type', 'Gene ID', 'Biomedical Entity']
    merged_df = merged_df.drop_duplicates(subset=columns_to_check)

    # Reset index from 1
    merged_df = merged_df.reset_index(drop=True)
    merged_df.index = merged_df.index + 1
    merged_df['Index'] = merged_df.index

    # Save cleaned data to output CSV
    merged_df.to_csv(output_file, index=False)
    print(f"Merged and newest file saved to {output_file}")

def filter_and_query_genes(input_file, output_file):
    """
    Filter rows with 'T' in 'answer' and valid 'Gene ID', query gene information, and save results.
    """
    # Load and filter data
    df = pd.read_csv(input_file)
    df_filtered = df[(df["answer"] == "T") & (df["Gene ID"].notna()) &
                     (df["Gene ID"] != "") & (df["Gene ID"] != "None")]

    # Group by Gene ID to calculate statistics
    gene_stats = df_filtered.groupby("Gene ID").agg(
        time_added_to_KG=("time_added_to_KG", "min"),
        support_evidence=("Gene ID", "size")
    ).reset_index()

    # Query gene information using MyGeneInfo
    entrez_ids = gene_stats["Gene ID"].astype(str).tolist()
    print(f"Total unique Gene IDs to query: {len(entrez_ids)}")

    mg = mygene.MyGeneInfo()
    batch_size = 1000
    results = []
    for i in range(0, len(entrez_ids), batch_size):
        batch = entrez_ids[i:i + batch_size]
        print(f"Querying batch {i // batch_size + 1} with {len(batch)} IDs")
        try:
            batch_results = mg.querymany(batch, scopes="entrezgene", fields=["symbol", "name", "taxid"], species="all")
            results.extend(batch_results)
        except Exception as e:
            print(f"Error processing batch {i // batch_size + 1}: {e}")
        time.sleep(1)

    # Create gene info dictionary
    gene_info = {}
    for item in results:
        if "notfound" not in item:
            query = str(item["query"])
            if query not in gene_info:
                gene_info[query] = item

    # Map gene information to gene_stats
    gene_stats["genename"] = gene_stats["Gene ID"].astype(str).map(
        lambda x: gene_info.get(x, {}).get("symbol", "N/A"))
    gene_stats["Description"] = gene_stats["Gene ID"].astype(str).map(
        lambda x: gene_info.get(x, {}).get("name", "N/A"))
    gene_stats["taxid"] = gene_stats["Gene ID"].astype(str).map(
        lambda x: gene_info.get(x, {}).get("taxid", "N/A"))

    # Filter out discontinued Gene IDs
    gene_stats_filtered = gene_stats[
        (gene_stats["genename"] != "N/A") |
        (gene_stats["Description"] != "N/A") |
        (gene_stats["taxid"] != "N/A")
        ]

    discontinued_ids = gene_stats[
        (gene_stats["genename"] == "N/A") &
        (gene_stats["Description"] == "N/A") &
        (gene_stats["taxid"] == "N/A")
        ]["Gene ID"].tolist()
    if discontinued_ids:
        print(f"The following Gene IDs are discontinued and have been filtered: {discontinued_ids}")

    # Rename and map taxid to species
    gene_stats_filtered.rename(columns={"Gene ID": "geneID"}, inplace=True)
    ncbi = NCBITaxa()
    gene_stats_filtered["species"] = gene_stats_filtered["taxid"].map(
        lambda x: ncbi.get_taxid_translator([x]).get(x, "Unknown") if x != "N/A" else "N/A"
    )

    # Reorder and save results
    output_columns = ["geneID", "genename", "Description", "taxid", "species", "time_added_to_KG", "support_evidence"]
    gene_stats_filtered = gene_stats_filtered[output_columns]
    gene_stats_filtered.to_csv(output_file, index=False)
    print(f"Results saved to {output_file}")