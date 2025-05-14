# load the required packages
library(babelgene)
library(clusterProfiler)
library(dplyr)
library(tidyr)

# Get incoming parameters
args <- commandArgs(trailingOnly = TRUE)
input_file <- args[1]
output_file <- args[2]

# Define the main function
gene_kegg_analysis <- function(input_file, output_file) {
  # View supported species
  species_list <- species()
  
  # Check if the input file exists
  if (!file.exists(input_file)) {
    stop(paste("Input file does not exist:", input_file))
  }
  
  # Loading the gene data
  gene_data <- read.csv(input_file)
  
  # Extract taxid and compare it with species_list to find overlapping species
  gene_data$taxid <- as.character(gene_data$taxid)
  common_taxids <- intersect(gene_data$taxid, species_list$taxon_id)

  gene_data$human_geneID <- NA
  no_ortholog_genes <- c()
  
  for (i in 1:nrow(gene_data)) {
    current_taxid <- gene_data$taxid[i]
    current_geneID <- gene_data$geneID[i]
    
    if (current_taxid == "9606") {
      gene_data$human_geneID[i] <- current_geneID
    } else if (current_taxid %in% common_taxids) {
      species_name <- species_list$scientific_name[species_list$taxon_id == current_taxid]
      
      tryCatch({
        ortholog_result <- orthologs(genes = current_geneID, species = species_name, human = FALSE)
        
        if (nrow(ortholog_result) == 0 || !"human_entrez" %in% colnames(ortholog_result) ||
            all(is.na(ortholog_result$human_entrez)) || all(ortholog_result$human_entrez == "")) {
          no_ortholog_genes <- c(no_ortholog_genes, current_geneID)
        } else {
          gene_data$human_geneID[i] <- ortholog_result$human_entrez[!is.na(ortholog_result$human_entrez) & ortholog_result$human_entrez != ""][1]
        }
      }, error = function(e) {
        no_ortholog_genes <<- c(no_ortholog_genes, current_geneID)
      })
    }
  }
  
  if (length(no_ortholog_genes) > 0) {
    message("The following geneIDs did not find human orthologs: ", paste(no_ortholog_genes, collapse = ", "))
  } else {
    message("All geneIDs found human orthologs.")
  }
  
  converted_genes <- gene_data %>% filter(!is.na(human_geneID)) %>% select(geneID, human_geneID)
  
  # Set the timeout to 300 seconds
  options(timeout = 300)
  
  # Define the number of retry and initial retry counter
  max_retries <- 5
  retry_count <- 0
  
  # the KEGG enrichment analysis
  while (retry_count < max_retries) {
    tryCatch({
      kegg_results <- enrichKEGG(gene = unique(converted_genes$human_geneID), organism = "hsa")
      break  # skip if successful
    }, error = function(e) {
      retry_count <<- retry_count + 1
      if (retry_count < max_retries) {
        message("Attempt ", retry_count, " failed. Retrying in 300 seconds...")
        Sys.sleep(300)  # sleep for 300s and retry
      } else {
        stop("Error during KEGG enrichment analysis after ", max_retries, " attempts: ", e$message)
      }
    })
  }
  
  kegg_df <- as.data.frame(kegg_results)
  
  # process KEGG results
  kegg_df <- kegg_df %>%
    select(ID, Description, pvalue, p.adjust, qvalue, geneID) %>%
    rename(
      `KEGG.ID` = ID,
      `Description` = Description,
      `pvalue` = pvalue,
      `p.adjust` = p.adjust,
      `qvalue` = qvalue,
      `human_geneID` = geneID
    )
  
  expanded_kegg_df <- kegg_df %>%
    mutate(human_geneID = strsplit(as.character(human_geneID), "/")) %>%
    unnest(human_geneID) %>%
    left_join(converted_genes %>% mutate(human_geneID = as.character(human_geneID)), 
              by = "human_geneID", 
              relationship = "many-to-many") %>%
    select(`KEGG.ID`, Description, pvalue, p.adjust, qvalue, geneID, human_geneID)
  
  # save the results
  write.csv(expanded_kegg_df, output_file, row.names = FALSE)
  if (!file.exists(output_file)) {
    stop(paste("Failed to save the output file:", output_file))
  }
  message(paste("KEGG enrichment results saved to", output_file))
  
  return(expanded_kegg_df)
}

# call the main function
tryCatch({
  results <- gene_kegg_analysis(input_file, output_file)
}, error = function(e) {
  message("An error occurred: ", e$message)
})
