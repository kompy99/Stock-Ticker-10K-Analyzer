from sec_edgar_downloader import Downloader
import os
import re
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb
import logging, sys

logging.basicConfig(stream=sys.stderr, level=logging.INFO)

def download_10k(ticker, download_directory_path):
    if not os.path.exists(download_directory_path):
        os.makedirs(download_directory_path)

    dl = Downloader("Gtech", "james@gtech.com",download_directory_path)
    dl.get("10-K", ticker, after="1995-01-01", before="2024-01-01")

    logging.info("10-Ks downloaded for " + ticker + " to " + download_directory_path)

def remove_consecutive_newlines(text):
    return re.sub(r'\n\s*\n\s*\n', '\n\n', text)

def clean_html(html_text):
    soup = BeautifulSoup(html_text, 'lxml')
    text = soup.get_text(' ')
    
    # Convert 2 or more newlines to single newline
    text = remove_consecutive_newlines(text)
    # Remove leading and trailing whitespaces
    text = text.strip()
    return text

ticker_10k_download_directory_path_template = "{download_directory_path}/sec-edgar-filings/{ticker}/10-K/"

def extract_10k_text(ticker, ticker_download_directory, ticker_output_directory_path):    
    
    if not os.path.exists(ticker_output_directory_path):
        os.makedirs(ticker_output_directory_path)

    for subdir, dirs, files in os.walk(ticker_download_directory):
        for file in files:
            if file.endswith('.txt'):
                file_path = os.path.join(subdir, file)
                with open(file_path, 'r') as f:
                    logging.debug("Extracting text from " + file_path)
                    filing_id = subdir.split("/")[-1]
                    year = filing_id.split("-")[1]
                    year = "19"+year if int(year) > 90 else "20"+year
                    text = f.read()
                    cleaned_text = clean_html(text)
                    output_file_path = os.path.join(ticker_output_directory_path, ticker + "_" + year + ".txt")
                    with open(output_file_path, 'w') as output_file:
                        output_file.write(cleaned_text)

    logging.info("Completed extracting 10-K text for " + ticker + " to " + ticker_output_directory_path)

def get_chunks(text, chunk_size, chunk_overlap):
    logging.debug("Splitting text into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size,chunk_overlap=chunk_overlap)
    chunks = text_splitter.split_text(text)
    logging.debug("Text split into " + str(len(chunks)) + " chunks")
    return chunks


def add_10k_to_store(client, ticker, filepath):
    with open(filepath, 'r') as f:
        text = f.read()
        chunks = get_chunks(text, 1000, 100)
        collection = client.get_or_create_collection(name=ticker, metadata={"ticker": ticker})
        year = filepath.split("_")[-1].split(".")[0]
        for i, chunk in enumerate(chunks):
            if i % 1000 == 0:
                logging.debug("Adding chunk " + str(i) + " to store...")
            collection.add(
                documents=[chunk],
                metadatas=[{"chunk": i, "ticker": ticker, "year": year}],
                ids=[f"{ticker}_{year}_{i}"]
                )

def add_ticker_10kData_to_store(client, ticker, processed_10k_ticker_path):
    if not os.path.exists(processed_10k_ticker_path):
        logging.error("Processed 10-K directory does not exist for " + ticker)
        return

    for subdir, dirs, files in os.walk(processed_10k_ticker_path):
        for file in files:
            if file.endswith('.txt'):
                file_path = os.path.join(subdir, file)
                logging.info("Adding 10-K data for " + ticker + " from " + file_path + " to store...")
                add_10k_to_store(client, ticker, file_path)
                logging.info("Completed adding 10-K data for " + ticker + " from " + file_path + " to store")

def download_and_add_10k_to_store(client, ticker, download_directory_path, processed_10k_directory_path):
    ticker_download_directory = ticker_10k_download_directory_path_template.format(download_directory_path=download_directory_path, ticker=ticker)
    ticker_output_directory_path = os.path.join(processed_10k_directory_path, ticker)

    download_10k(ticker, download_directory_path)
    extract_10k_text(ticker, ticker_download_directory, ticker_output_directory_path)
    add_ticker_10kData_to_store(client, ticker, ticker_output_directory_path)

def ingest_ticker(ticker):
    download_directory_path = "./data/10k_downloads"
    processed_10Ks_directory_path = "./data/10k_processed"
    client = chromadb.PersistentClient(path="./data/chroma_db")

    download_and_add_10k_to_store(client, ticker, download_directory_path, processed_10Ks_directory_path)

# Code below is for testing purposes

def main():
    download_directory_path = "./data/10k_downloads"
    processed_10Ks_directory_path = "./data/10k_processed"
    tickers = ["AAPL","BRK-B"]
    client = chromadb.PersistentClient(path="./data/chroma_db")
    
    for ticker in tickers:
        ticker_output_directory_path = os.path.join(processed_10Ks_directory_path, ticker)
        add_ticker_10kData_to_store(client, ticker, ticker_output_directory_path)

if __name__ == "__main__":
    main()
