import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from langchain.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.prompts import PromptTemplate
from langchain.chains import RetrievalQA
from langchain_ollama import OllamaLLM

def chunk_movie_dataset(csv_path, chunksize=5000, max_rows=100000):
    """
    Load and preprocess movie ticketing dataset in chunks for testing.

    Args:
        csv_path (str): Path to the CSV file.
        chunksize (int): Number of rows per chunk (default: 5,000).
        max_rows (int): Maximum rows to load (default: 100,000).

    Returns:
        tuple: (full DataFrame, list of text snippets for embeddings)
    """
    try:
        df_list = []
        rows_loaded = 0

        print("Reading CSV in chunks...")
        chunks = pd.read_csv(csv_path, chunksize=chunksize, low_memory=False, nrows=max_rows)

        for i, chunk in enumerate(chunks):
            print(f"Processing chunk {i+1}...")
            date_columns = ['date_sh', 'last_updates', 'running_date', 'release_date',
                            'dsr_date_sh', 'dsr_last_updates']
            for col in date_columns:
                if col in chunk.columns:
                    chunk[col] = pd.to_datetime(chunk[col], errors='coerce')
            df_list.append(chunk)
            rows_loaded += len(chunk)
            if rows_loaded >= max_rows:
                break

        print("Concatenating chunks...")
        df = pd.concat(df_list, ignore_index=True)

        text_columns = ['title', 'genre', 'rating', 'studio_name', 'theater_name',
                        'theater_city', 'language_format', 'country']
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].fillna('').astype(str)
            else:
                print(f"Warning: Column {col} not found in CSV")

        texts = (
            df['title'] + ' ' +
            df['genre'] + ' ' +
            df['rating'] + ' ' +
            df['studio_name'] + ' ' +
            df['theater_name'] + ' ' +
            df['theater_city'] + ' ' +
            df['language_format'] + ' ' +
            df['country']
        ).tolist()

        return df, texts
    except Exception as e:
        print(f"Error in chunk_movie_dataset: {e}")
        raise

def create_vector_store(texts, faiss_index_path='faiss_index_test', batch_size=512):
    """
    Generate embeddings and create FAISS vector store.

    Args:
        texts (list): List of text snippets for embeddings.
        faiss_index_path (str): Path to save FAISS index.
        batch_size (int): Batch size for embedding generation (default: 512).

    Returns:
        FAISS: Vector store object.
    """
    try:
        print("Generating embeddings...")
        model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=True)
        np.save('embeddings_test.npy', embeddings)
        embeddings_model = HuggingFaceEmbeddings(model_name='paraphrase-multilingual-MiniLM-L12-v2')
        vectorstore = FAISS.from_embeddings(zip(texts, embeddings), embeddings_model)
        vectorstore.save_local(faiss_index_path)
        print(f"FAISS index saved to {faiss_index_path}")
        return vectorstore
    except Exception as e:
        print(f"Error in create_vector_store: {e}")
        raise

def setup_rag_chain(faiss_index_path='faiss_index_test'):
    """
    Setup RAG pipeline with FAISS and LLaMA 3.2 8B.

    Args:
        faiss_index_path (str): Path to FAISS index.

    Returns:
        RetrievalQA: RAG chain for querying.
    """
    try:
        print("Setting up RAG chain...")
        embeddings_model = HuggingFaceEmbeddings(model_name='paraphrase-multilingual-MiniLM-L12-v2')
        vectorstore = FAISS.load_local(faiss_index_path, embeddings_model, allow_dangerous_deserialization=True)
        llm = OllamaLLM(model="llama3:8b", temperature=0.2, num_predict=256)
        print("Testing Ollama connection...")
        llm.invoke("Test")
        print("Ollama connection successful")

        prompt_template = """
        Based on the following movie ticket data:
        {context}

        Question: {question}

        Answer in natural language using only the provided data. For comparisons, use metrics like ratings, reserved tickets, or genres. If numerical insights are needed, approximate from the retrieved data.
        """
        PROMPT = PromptTemplate(template=prompt_template, input_variables=["context", "question"])

        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=vectorstore.as_retriever(search_kwargs={"k": 20}),
            return_source_documents=True,
            chain_type_kwargs={"prompt": PROMPT}
        )
        return qa_chain
    except Exception as e:
        print(f"Error in setup_rag_chain: {e}")
        raise

def run_query(qa_chain, query):
    """
    Run a query through the RAG pipeline.

    Args:
        qa_chain (RetrievalQA): RAG chain object.
        query (str): User query.

    Returns:
        tuple: (answer, list of source documents)
    """
    try:
        print(f"Running query: {query}")
        result = qa_chain.invoke({"query": query})
        return result['result'], [doc.page_content for doc in result['source_documents']]
    except Exception as e:
        print(f"Error in run_query: {e}")
        raise

def main():
    """
    Main function to run the RAG pipeline for testing.
    """
    # csv_path = '/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/chat/test_dataset_100k.csv'
    # print("Loading dataset and creating FAISS index...")
    #
    # # Load and preprocess data
    # df, texts = chunk_movie_dataset(csv_path, chunksize=5000, max_rows=100000)
    # print(f"Loaded {len(df)} rows and {len(texts)} text snippets")
    #
    # # Create FAISS index
    # vectorstore = create_vector_store(texts, batch_size=512)
    # print("FAISS index created and saved")

    # Setup RAG chain
    qa_chain = setup_rag_chain()
    print("RAG pipeline ready")

    # Test queries
    test_queries = [
        "AMC Entertainment Inc New york movies.",
    ]

    for query in test_queries:
        print(f"\nQuery: {query}")
        answer, sources = run_query(qa_chain, query)
        print(f"Answer: {answer}")
        print("Sources:")
        for i, source in enumerate(sources, 1):
            print(f"  {i}. {source}")

if __name__ == "__main__":
    main()