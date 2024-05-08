from flask import Flask, request, render_template, jsonify
import threading
import chromadb
import logging, sys
import json
from ingest import ingest_ticker
from analytics import analyze_ticker

logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

app = Flask(__name__)


def get_tickers():
    dbclient = chromadb.PersistentClient(path="./data/chroma_db")
    collections = dbclient.list_collections()
    ticker_list = []
    
    for collection in collections:
        ticker_list.append(collection.name)
    
    logging.info(f"Found tickers: {ticker_list}")
    return ticker_list

@app.route('/')
def index():
    return render_template('index.html', tickers=get_tickers())

@app.route('/data/<ticker>')
def get_data(ticker):
    
    try:
        with open(f"./data/{ticker}_financial_metrics.json", "r") as f:
            data = json.load(f)
            revenue = data["revenue"]
            income = data["income"]
            eps = data["eps"]

            # Create a list of labels for each of the metrics from 1995 to 2023 where the corresponding value in the list is not None

            revenue_labels = []
            income_labels = []
            eps_labels = []
            revenue_data = []
            income_data = []
            eps_data = []

            for i in range(1995, 2024):
                if revenue[i-1995] is not None:
                    revenue_labels.append(i)
                    revenue_data.append(revenue[i-1995])
                if income[i-1995] is not None:
                    income_labels.append(i)
                    income_data.append(income[i-1995])
                if eps[i-1995] is not None:
                    eps_labels.append(i)
                    eps_data.append(eps[i-1995])
                    
            data = {
                "revenue": {"labels": revenue_labels, "data": revenue_data},
                "income": {"labels": income_labels, "data": income_data},
                "eps": {"labels": eps_labels, "data": eps_data}
            }

            logging.debug(f"Actual JSON for {ticker}: {data}")

            return data
    except Exception as e:
        logging.error(f"Error getting data for {ticker}: {e}")
        return {"revenue": {"labels": [], "data": []}, "income": {"labels": [], "data": []}, "eps": {"labels": [], "data": []}}

def process_new_ticker(ticker):
    ingest_ticker(ticker)
    analyze_ticker(ticker)

@app.route('/add_ticker', methods=['POST'])
def add_ticker():
    data = request.get_json()
    ticker = data.get('ticker')
    if ticker:
        # Start the background task
        thread = threading.Thread(target=process_new_ticker, args=(ticker,))
        thread.start()
        # Return a response immediately to the client
        return jsonify({"message": "Ticker is being processed", "status": "success"}), 200
    else:
        return jsonify({"message": "No ticker provided", "status": "error"}), 400

if __name__ == '__main__':
    app.run(debug=True)
