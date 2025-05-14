import pandas as pd
from pyvis.network import Network
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
from flask import Flask, render_template_string
from pyvis.options import Options
import webbrowser
import sys
import os
import signal
import socket
import subprocess
import json
import math

def kill_process_on_port(port):
    """
    检测并终止占用指定端口的进程
    """
    try:
        result = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True)
        for line in result.strip().split("\n"):
            if "LISTENING" in line:
                pid = int(line.split()[-1])
                os.kill(pid, signal.SIGTERM)
                print(f"Terminated process {pid} on port {port}")
    except Exception as e:
        print(f"Failed to terminate process on port {port}: {e}")


def is_port_in_use(port):
    """
    检查指定端口是否被占用
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


# Read the CSV
def read_csv(file_path):
    try:
        print(f"Attempting to read file: {file_path}")
        df = pd.read_csv(file_path, dtype={'geneID': str})
        print(f"File loaded successfully: {file_path}")
        return df
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return pd.DataFrame()


# Connect different dataframes according to the GENE IDs and create the knowledge graph
def create_knowledge_graph(selected_pathway, selected_genes, gene_info_df, significant_pathways, other_pathways,
                           selected_time):
    # create a pyvis network
    net = Network(height='600px', width='100%', directed=True)

    # Set layout and physical simulation parameters
    options = {
        "physics": {
            "enabled": True,
            "barnesHut": {
                "gravitationalConstant": -2000,
                "centralGravity": 0.1,
                "springLength": 100,
                "springConstant": 0.05,
            },
            "minVelocity": 0.75,
            "solver": "barnesHut",
        },
        "layout": {
            "improvedLayout": True,
        }
    }

    net.set_options(json.dumps(options))

    if selected_time and selected_time != 'ALL TIME':
        filtered_gene_info_df = gene_info_df[gene_info_df['time_added_to_KG'] == selected_time]
    else:
        filtered_gene_info_df = gene_info_df
    if selected_pathway != "others":
        pathway_genes = significant_pathways[significant_pathways['Description'] == selected_pathway]
    else:
        pathway_genes = other_pathways[other_pathways['geneID'].isin(selected_genes)]

    selected_genes_in_pathway = pathway_genes[pathway_genes['geneID'].isin(selected_genes)]
    # Add the KEGG path node
    if selected_pathway == "others":
        unique_pathways = selected_genes_in_pathway.drop_duplicates(subset=['Description'])
        num_pathways = len(unique_pathways)
        if num_pathways == 0:
            return net
        # Calculate the KEGG path location
        center_radius = 50
        angle_increment = 2 * math.pi / num_pathways

        for i, (_, row) in enumerate(unique_pathways.iterrows()):
            kegg_description = row['Description']
            kegg_ID = row['KEGG.ID']

            theta = i * angle_increment
            x = center_radius * math.cos(theta)
            y = center_radius * math.sin(theta)

            net.add_node(kegg_description, label=kegg_description, shape='dot', color='red', size=20,
                         font={'align': 'center', 'valign': 'bottom', 'face': 'arial', 'size': 15, 'bold': True,
                               'color': 'black'},
                         title=kegg_ID, x=x, y=y)  # locate in the center origin
    else:
        pathway_row = significant_pathways[significant_pathways['Description'] == selected_pathway].iloc[0]
        kegg_description = pathway_row['Description']
        kegg_ID = pathway_row['KEGG.ID']

        net.add_node(kegg_description, label=kegg_description, shape='dot', color='red', size=20,
                     font={'align': 'center', 'valign': 'bottom', 'face': 'arial', 'size': 15, 'bold': True,
                           'color': 'black'},
                     title=kegg_ID, x=0, y=0)

    # Sort genes in descending order based on their support and evidence
    sorted_genes = filtered_gene_info_df[filtered_gene_info_df['geneID'].isin(selected_genes_in_pathway['geneID'])]
    sorted_genes = sorted_genes.sort_values(by='support_evidence', ascending=False)

    # Define layering rules: the number of nodes in each layer
    layer_sizes = [6, 10, 16, 26, 42, 68, 110, 178, 288]
    base_radius = 120
    layer_spacing = 50
    node_size = 15
    min_distance = 50
    label_offset = 20

    # Assign hierarchies and calculate node locations
    current_index = 0
    for layer, size in enumerate(layer_sizes, start=1):
        # get the gene of this layer
        layer_genes = sorted_genes.iloc[current_index:current_index + size]
        current_index += size

        # Adjust the node number if not reach
        if len(layer_genes) < size:
            size = len(layer_genes)

        radius = base_radius + (layer - 1) * layer_spacing
        angle_increment = 2 * math.pi / size
        placed_nodes = []
        placed_labels = []
        for index, row in layer_genes.iterrows():
            gene_id = row['geneID']
            gene_name = row['genename']
            gene_description = row['Description']
            theta = index * angle_increment
            attempts = 0
            while attempts < 100:  # max times: 100
                x = radius * math.cos(theta)
                y = radius * math.sin(theta)
                label_x = x + label_offset
                label_y = y + label_offset

                # Check if nodes and labels overlap
                node_overlap = False
                label_overlap = False
                for (px, py) in placed_nodes:
                    distance = math.sqrt((x - px) ** 2 + (y - py) ** 2)
                    if distance < min_distance:
                        node_overlap = True
                        break
                for (lx, ly, _) in placed_labels:
                    if abs(label_x - lx) < label_offset and abs(label_y - ly) < label_offset:
                        label_overlap = True
                        break
                if not node_overlap and not label_overlap:
                    placed_nodes.append((x, y))
                    placed_labels.append((label_x, label_y, gene_name))
                    break
                theta += angle_increment / 10
                attempts += 1

            # Add the gene node
            net.add_node(gene_id, label=gene_name, shape='star', color='blue', size=node_size,
                         font={'align': 'left', 'valign': 'top', 'face': 'arial', 'size': 15, 'bold': True},
                         title=gene_description, x=x, y=y)

            # Add the edge
            if selected_pathway == "others":
                for _, row in unique_pathways.iterrows():
                    kegg_description = row['Description']
                    net.add_edge(gene_id, kegg_description, color='gray', arrows='none')
            else:
                net.add_edge(gene_id, kegg_description, color='gray', arrows='none')

        if current_index >= len(sorted_genes):
            break

    return net

# Create the Flask
server = Flask(__name__)

# Create and integrate Dash app with Flask
app = dash.Dash(__name__, server=server, url_base_pathname='/dash/')

# Layout with Dropdowns for selecting time and pathway
app.layout = html.Div([
    html.H1(f"Knowledge Graph of Radiation-Related genes sorted by pathways", style={'textAlign': 'center', 'color': '#2c3e50', 'marginBottom': '20px'}),
    # Upper part: includes the map and the selection box on the right side
    html.Div([
        # Left: Select time and KEGG
        html.Div([
            html.H2("Time Selection", style={'color': '#34495e', 'marginBottom': '10px'}),
            dcc.Dropdown(id='time-dropdown', options=[], placeholder="选择时间", value=None, style={'width': '100%', 'marginBottom': '20px'}),
            html.H2("Pathway Selection", style={'color': '#34495e', 'marginBottom': '10px'}),
            dcc.Dropdown(id='pathway-dropdown', options=[], placeholder="选择Pathway", value=None, style={'width': '100%'}), ],
            style={'width': '25%', 'display': 'inline-block', 'verticalAlign': 'top', 'padding': '20px', 'backgroundColor': '#f8f9fa',
                   'borderRadius': '10px', 'boxShadow': '0 4px 8px 0 rgba(0,0,0,0.2)', 'marginRight': '20px'}),
        # Right: Show the knowledge graph
        html.Div([
            html.H2("", style={'color': '#34495e', 'marginBottom': '10px'}),
            html.Iframe(id='graph', srcDoc='', width='100%', height='600px', style={'border': '1px solid #ddd', 'borderRadius': '10px', 'overflow': 'hidden'})
        ], style={'width': '73%', 'display': 'inline-block', 'verticalAlign': 'top', 'padding': '20px', 'backgroundColor': '#f8f9fa',
                  'borderRadius': '10px', 'boxShadow': '0 4px 8px 0 rgba(0,0,0,0.2)'}),
    ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'padding': '20px', 'marginBottom': '20px',
              'maxWidth': '1400px', 'margin': '0 auto', 'gap': '20px'}),  # 调整 maxWidth 为 1400px

    # Bottom part: Details of the genes
    html.Div([
        html.H2(f"Basic information of Genes in the graph ", style={'color': '#34495e', 'marginBottom': '10px'}),
        dash_table.DataTable(
            id='table-detailed',
            columns=[
                {'name': 'geneID', 'id': 'geneID'},
                {'name': 'genename', 'id': 'genename'},
                {'name': 'Description', 'id': 'Description'},
                {'name': 'Species', 'id': 'species'},
                {'name': 'time_added_to_KG', 'id': 'time_added_to_KG'},
                {'name': 'support_evidence_number', 'id': 'support_evidence', 'presentation': 'markdown'}
            ],
            style_table={'height': '400px', 'overflowY': 'auto', 'border': '1px solid #ddd', 'borderRadius': '10px', 'width': '95%',  'margin': '0 auto'},
            # 设置表格高度和滚动
            style_cell={
                'textAlign': 'center',
                'padding': '10px',
                'border': '1px solid #ddd',
                'minWidth': '100px',
                'width': '100px',
                'maxWidth': '100px',
                'whiteSpace': 'normal',
                'fontSize': '18px',
            },
            style_header={'backgroundColor': '#34495e', 'color': 'white', 'fontWeight': 'bold', 'fontSize': '16px', },  # 表头样式
            page_size=20,
            page_action='native',
            page_current=0,
            fixed_rows={'headers': True}
        ),
        html.Div(id='table-row-count', style={'textAlign': 'center', 'marginTop': '10px', 'fontSize': '16px', 'color': '#34495e'})
    ], style={'width': '100%', 'textAlign': 'center', 'padding': '20px', 'backgroundColor': '#f8f9fa',
              'borderRadius': '10px', 'boxShadow': '0 4px 8px 0 rgba(0,0,0,0.2)', 'maxWidth': '1400px', 'margin': '0 auto'}),  # 调整 maxWidth 为 1400px
], style={'paddingTop': '20px', 'paddingLeft': '20px', 'paddingRight': '20px', 'paddingBottom': '20px', 'backgroundColor': '#ecf0f1',
          'minHeight': '100vh', 'maxWidth': '1600px', 'margin': '0 auto'})  # 调整 maxWidth 为 1600px


# Update the graph and table
@app.callback(
    [Output('time-dropdown', 'options'),
     Output('pathway-dropdown', 'options'),
     Output('time-dropdown', 'value'),
     Output('pathway-dropdown', 'value'),
     Output('graph', 'srcDoc'),
     Output('table-detailed', 'data'),
     Output('table-row-count', 'children')],
    [Input('time-dropdown', 'value'),
     Input('pathway-dropdown', 'value')])
def update_graph_and_table(selected_time, selected_pathway):
    global new_gene_info_path, new_gene_pathway_path, new_all_data_path

    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    gene_info_df = read_csv(new_gene_info_path)
    gene_pathway_results_df = read_csv(new_gene_pathway_path)

    significant_pathways = gene_pathway_results_df[gene_pathway_results_df['pvalue'] < 0.02]
    other_pathways = gene_pathway_results_df[gene_pathway_results_df['pvalue'] >= 0.02]

    all_time_options = [{'label': time, 'value': time} for time in gene_info_df['time_added_to_KG'].unique()]
    all_time_options.insert(0, {'label': 'ALL TIME', 'value': 'ALL TIME'})

    if selected_time == 'ALL TIME' or selected_time is None:
        selected_gene_ids = gene_info_df['geneID'].unique()
    else:
        selected_gene_ids = gene_info_df[gene_info_df['time_added_to_KG'] == selected_time]['geneID'].unique()

    pathways_for_selected_genes = gene_pathway_results_df[gene_pathway_results_df['geneID'].isin(selected_gene_ids)]['Description'].unique()

    pathway_options = [{'label': pathway, 'value': pathway} for pathway in pathways_for_selected_genes if pathway in significant_pathways['Description'].values]
    pathway_options.append({'label': 'others', 'value': 'others'})

    # Sort the options
    time_options_sorted = sorted(all_time_options[1:], key=lambda x: x['value'])
    time_options_sorted.insert(0, {'label': 'ALL TIME', 'value': 'ALL TIME'})
    pathway_options_sorted = sorted(pathway_options[:-1], key=lambda x: x['label'].lower()) + [pathway_options[-1]]

    valid_times = [option['value'] for option in time_options_sorted]
    if selected_time not in valid_times:
        selected_time = time_options_sorted[0]['value']

    if triggered_id == 'time-dropdown':
        selected_pathway = pathway_options_sorted[0]['value'] if pathway_options_sorted else None
    else:
        valid_pathways = [option['value'] for option in pathway_options_sorted]
        if selected_pathway not in valid_pathways:
            selected_pathway = pathway_options_sorted[0]['value'] if pathway_options_sorted else None

    # Filter gene ID according to selected time and pathway
    if selected_pathway == 'others':
        valid_gene_ids = list(set(selected_gene_ids) & set(other_pathways['geneID'].unique()))
    elif selected_pathway is not None:
        valid_gene_ids = list(set(selected_gene_ids) & set(gene_pathway_results_df[gene_pathway_results_df['Description'] == selected_pathway]['geneID'].unique()))
    else:
        valid_gene_ids = selected_gene_ids

    # Create knowledge graph
    net = create_knowledge_graph(selected_pathway, valid_gene_ids, gene_info_df, significant_pathways, other_pathways, selected_time)
    net.options = Options()
    net.options.physics.enabled = False
    graph_html = net.generate_html().replace('<iframe', '<iframe scrolling="no"')

    # Filter data of the table
    gene_info_filtered = gene_info_df.copy()
    if selected_time != 'ALL TIME':
        gene_info_filtered = gene_info_filtered[gene_info_filtered['time_added_to_KG'] == selected_time]
    if selected_pathway == 'others':
        gene_info_filtered = gene_info_filtered[gene_info_filtered['geneID'].isin(other_pathways['geneID'])]
    elif selected_pathway is not None:
        gene_info_filtered = gene_info_filtered[gene_info_filtered['geneID'].isin(gene_pathway_results_df[gene_pathway_results_df['Description'] == selected_pathway]['geneID'])]

    table_data = gene_info_filtered.to_dict('records')
    for row in table_data:
        row['support_evidence'] = f"[{row['support_evidence']}](/gene-details/{row['geneID']})"

    row_count = len(table_data)
    row_count_text = f"Total Genes: {row_count}"

    return time_options_sorted, pathway_options_sorted, selected_time, selected_pathway, graph_html, table_data, row_count_text


# Create Flask routes to display gene details
@server.route('/gene-details/<gene_id>')
def gene_details(gene_id):
    global new_all_data_path, new_gene_info_path

    information_initial_df = read_csv(new_all_data_path)
    gene_info_df = read_csv(new_gene_info_path)

    information_initial_df['Gene ID'] = information_initial_df['Gene ID'].astype(str)

    gene_name = gene_info_df[gene_info_df['geneID'] == gene_id]['genename'].values
    gene_name = gene_name[0] if len(gene_name) > 0 else 'Unknown'

    gene_info = information_initial_df[
        (information_initial_df['Gene ID'] == gene_id) & (information_initial_df['answer'] == 'T')]

    if gene_info.empty:
        return render_template_string('''
            <div style="text-align: center; padding: 50px;">
                <h1>Evidence for Gene <span style="color: red;">{{ gene_name }}</span> (GeneID: <a href="https://www.ncbi.nlm.nih.gov/gene/{{ gene_id }}" target="_blank">{{ gene_id }}</a>)</h1>
                <p style="font-size: 18px; color: #666;">The details of the gene are not found </p>
            </div>
        ''', gene_name=gene_name, gene_id=gene_id)

    gene_info = gene_info[['PMID', 'Sentence', 'time_added_to_KG', 'model_type', 'Gene Name', 'Biomedical Entity']]

    # Mark the background colors of Gene Name and Biomedical Entity in Sentence as yellow and green
    for index, row in gene_info.iterrows():
        sentence = row['Sentence']
        gene_name = row['Gene Name']
        uv_entity = row['Biomedical Entity']
        if gene_name:
            sentence = sentence.replace(gene_name, f'<span style="background-color: yellow;">{gene_name}</span>')
        if uv_entity:
            sentence = sentence.replace(uv_entity, f'<span style="background-color: lightgreen;">{uv_entity}</span>')
        gene_info.at[index, 'Sentence'] = sentence

    return render_template_string('''
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Evidence for Gene {{ gene_name }} (GeneID: {{ gene_id }})</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f9f9f9;
                    margin: 0;
                    padding: 20px;
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    background: #fff;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                }
                h1 {
                    text-align: center;
                    color: #333;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                }
                th, td {
                    padding: 12px;
                    text-align: left;
                    border-bottom: 1px solid #ddd;
                }
                th {
                    background-color: #f2f2f2;
                }
                tr:hover {
                    background-color: #f5f5f5;
                }
                a {
                    color: #007bff;
                    text-decoration: none;
                }
                a:hover {
                    text-decoration: underline;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Evidence for Gene <span style="color: red;">{{ gene_name }}</span> (GeneID: <a href="https://www.ncbi.nlm.nih.gov/gene/{{ gene_id }}" target="_blank">{{ gene_id }}</a>)</h1>
                <table>
                    <thead>
                        <tr>
                            <th>PMID</th>
                            <th>Sentence</th>
                            <th>Time Added to KG</th>
                            <th>Model Type</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for _, row in gene_info.iterrows() %}
                            <tr>
                                <td><a href="https://pubmed.ncbi.nlm.nih.gov/{{ row['PMID'] }}" target="_blank">{{ row['PMID'] }}</a></td>
                                <td>{{ row['Sentence'] | safe }}</td>
                                <td>{{ row['time_added_to_KG'] }}</td>
                                <td>{{ row['model_type'] }}</td>
                            </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </body>
        </html>
    ''', gene_name=gene_name, gene_id=gene_id, gene_info=gene_info)


# Start the program
if __name__ == '__main__':
    if len(sys.argv) > 3:
        new_gene_info_path = sys.argv[1]
        new_gene_pathway_path = sys.argv[2]
        new_all_data_path = sys.argv[3]
        print("Received file paths:")
        print(f"Gene info path: {new_gene_info_path}")
        print(f"Gene pathway path: {new_gene_pathway_path}")
        print(f"All data path: {new_all_data_path}")
    else:
        print("Using default file paths")
        new_gene_info_path = '1_gene_info_show.csv'
        new_gene_pathway_path = '1_gene_pathway_results.csv'
        new_all_data_path = '1_all_data.csv'

    print("Starting Dash app...")

    port = 8050
    if is_port_in_use(port):
        print(f"Port {port} is in use. Terminating the process...")
        kill_process_on_port(port)
    else:
        print(f"Port {port} is free. Starting the application...")

    webbrowser.open(f'http://127.0.0.1:{port}/dash/')
    app.run_server(debug=False)