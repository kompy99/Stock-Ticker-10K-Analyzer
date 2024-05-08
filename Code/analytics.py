import chromadb
import os
from openai import AzureOpenAI
import logging, sys
import json
from typing import Union

logging.basicConfig(stream=sys.stderr, level=logging.INFO)

AZURE_OPENAI_API_KEY = "<AZURE_OPENAI_API_KEY>"
AZURE_OPENAI_ENDPOINT = "<AZURE_OPENAI_ENDPOINT>"

def query_gpt(query, context):
    azclient = AzureOpenAI(azure_endpoint = AZURE_OPENAI_ENDPOINT, 
                           api_key=AZURE_OPENAI_API_KEY,  
                           api_version="2024-02-01")
    
    template = """
                Context: {context}
                
                Question: {question}
                
                """
    
    message = template.format(context=context, question=query)
    
    logging.debug(f"Querying GPT... \nRequest\n-----------\n\nMessage: {message}")
    response = azclient.chat.completions.create(
    model="gpt-35-turbo-16k",
    messages=[
        {"role": "system", "content": "You are a financial data assistant. Use the given context to find and return the financial metrics for the given year. If a metric is not available for a year, return None for that year. Use only the information available in the context do not ever make up a value."},
        {"role": "user", "content": message},
    ])

    logging.debug(f"\n\nResponse: {response}")
    return response


def get_context_document_ids_for_query(client, ticker, query, year):
    collection = client.get_collection(ticker)
    query_results = collection.query(
        query_texts=[query],
        n_results=5,
        where={"year": f"{str(year)}"},
    )

    logging.debug(f"Query results for {query}: {query_results}")
    context_document_ids = query_results["ids"][0]
    return context_document_ids

def get_documents_by_ids(client, ids, ticker):
    collection = client.get_collection(ticker)
    documents = collection.get(ids=ids)["documents"]
    return documents

def parse_metrics(metrics_json: str) -> tuple[Union[float, None], Union[float, None], Union[float, None]]:
    
    logging.debug(f"Parsing metrics: {metrics_json}")
    
    metrics_json = metrics_json.replace("'", '"')
    metrics_json = metrics_json.replace("None", "null")
    data = json.loads(metrics_json)

    revenue = data.get("revenue")
    if isinstance(revenue, (int, float)):
        revenue = float(revenue)
    else:
        revenue = None

    income = data.get("income")
    if isinstance(income, (int, float)):
        income = float(income)
    else:
        income = None

    eps = data.get("eps")
    if isinstance(eps, (int, float)):
        eps = float(eps)
    else:
        eps = None

    return revenue, income, eps

def get_stats_by_year(client, ticker, year):
    revenue_query = f"What is the revenue for {str(year)} (in millions)?"
    revenue_context_document_ids = get_context_document_ids_for_query(client, ticker, revenue_query, year)
    logging.debug(f"Revenue context document ids: {revenue_context_document_ids}")
     
    income_query = f"According to the Comprehensive Income statments section under Item 8, what is the net income for {str(year)}?"
    income_context_document_ids = get_context_document_ids_for_query(client, ticker, income_query, year)
    logging.debug(f"income context document ids: {income_context_document_ids}")
    
    eps_query = f"What is the earnings per share (or EPS) for {str(year)} under Item 8 Financial Statements and Supplementary Data?"
    eps_context_document_ids = get_context_document_ids_for_query(client, ticker, eps_query, year)
    logging.debug(f"EPS context document ids: {eps_context_document_ids}")

    context_document_ids = set(revenue_context_document_ids + income_context_document_ids + eps_context_document_ids)
    logging.debug(f"Context document ids: {context_document_ids}")

    if len(context_document_ids) == 0:
        logging.critical(f"No context document ids found for year {str(year)}")
        return None, None, None

    context_documents = get_documents_by_ids(client, list(context_document_ids), ticker)

    context = ""
    for i, doc in enumerate(context_documents):
        context += doc + " "

    logging.debug(f"Context for year {str(year)}: {context}")

    query = f"""Check under Item 8 of Financial Statements and Supplementary Data. What is the revenue, net income, and earnings per share for {str(year)}?
            Return the value as a JSON object. Use this example - "{{ "revenue" : <revenue-value-in-millions>, "income" : <income-value-in-millions>, "eps" : <eps-value-in-dollars> }}"
            If a value is not available for the mentioned year then use "null" to fill in the value.
            """
    
    response = query_gpt(query, context)

    metrics_json = response.choices[0].message.content

    logging.info(f"The metrics are: {metrics_json}")

    revenue, income, eps = parse_metrics(metrics_json)

    return revenue, income, eps

def continue_generation(client, ticker):
    with open(f"./data/{ticker}_financial_metrics.json", "r") as f:
        data = json.load(f)
        revenue_list = data["revenue"]
        income_list = data["income"]
        eps_list = data["eps"]

    start_year = len(revenue_list)-1 + 1995
    end_year = 2023

    for year in range(start_year, end_year+1):
        try:
            revenue, income, eps = get_stats_by_year(client, ticker, year)
        except Exception as e:
            logging.error(f"Error getting metrics for {ticker} for year {year}: {e}")
            revenue = None
            income = None
            eps = None
        revenue_list.append(revenue)
        income_list.append(income)
        eps_list.append(eps)

        # Write to file on each iteration to avoid losing data
        with open(f"./data/{ticker}_financial_metrics.json", "w") as f:
            data = {"revenue": revenue_list, "income": income_list, "eps": eps_list}
            json.dump(data, f)



def generate_statistics(client, ticker, start_year=1995, end_year=2023):

    logging.info(f"Generating metrics for {ticker} from {start_year} to {end_year}...")
    
    revenue_list = []
    income_list = []
    eps_list = []
    for year in range(start_year, end_year+1):
        try:
            revenue, income, eps = get_stats_by_year(client, ticker, year)
        except Exception as e:
            logging.error(f"Error getting metrics for {ticker} for year {year}: {e}")
            revenue = None
            income = None
            eps = None
        revenue_list.append(revenue)
        income_list.append(income)
        eps_list.append(eps)

        # Write to file on each iteration to avoid losing data
        with open(f"./data/{ticker}_financial_metrics.json", "w") as f:
            data = {"revenue": revenue_list, "income": income_list, "eps": eps_list}
            json.dump(data, f)

def analyze_ticker(ticker):
    dbclient = chromadb.PersistentClient(path="./data/chroma_db")
    generate_statistics(dbclient, ticker, 1995, 2023)

# Code below is for testing purposes
    
def main():
    dbclient = chromadb.PersistentClient(path="./data/chroma_db")
    generate_statistics(dbclient, "BRK-B", 1995, 2023)

if __name__ == "__main__":
    main()