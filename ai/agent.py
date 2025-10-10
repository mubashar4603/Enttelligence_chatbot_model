from phi.agent import Agent
from phi.model.openai import OpenAIChat
from langchain_openai import ChatOpenAI
from langchain_experimental.agents import create_csv_agent
from langchain.agents.agent_types import AgentType
import os
from phi.model.ollama import Ollama

os.environ['OPENAI_API_KEY'] = "key"

llm = ChatOpenAI(
    model="cogito:8b",
    temperature=0.2,  # Lower temperature for more focused responses
    base_url="http://20.83.161.156:5001/v1",
    api_key="key"
)

# Create a specialized CSV agent for data analysis
agent_executor = create_csv_agent(
    llm,
    "data/Movie_shows_2023.csv",
    agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,  # Better for analytical tasks
    verbose=True,
    handle_parsing_errors=True,
    max_iterations=5,  # Prevent infinite loops
    allow_pandas_syntax=True  # Enable pandas operations for better data analysis
)def get_answer(question: str):
    """
    Answer user questions about movies, theaters, and showtimes 
    using the cinema dataset.

    The dataset includes:
    - Movie details: title, release_date, genre, runtime, rating, studio_name
    - Theater info: theater_name, address, city, state, zip, circuit_name
    - Showtimes: date_sh, time_sh, screen_format, movie_format, language_format
    - Ticketing: price, child, senior, ticket_availability, is_ticketing
    - Seating: total_seats, available, reserved, checkered, seating_type
    - Metadata: last_updates, running_date, dma, source_flag

    Use this tool when the user asks about:
    - Movies (popularity, availability, genre, runtime, release date)
    - Showtimes (dates, times, formats, ticket availability)
    - Pricing (adult, child, senior ticket prices)
    - Theater details (location, amenities, circuit, DMA region)
    - Seating or reservation status

    """
    response = agent_executor.run("what is the most famous movie")
    return response


agent = Agent(
    model=Ollama(id="phi4-mini:latest", host="http://20.83.161.156:5001"),
    description="You are an HVAC assistant. Use the following reference documents to answer the user's question.",
    instructions=[
        "Use the `get_answer` tool to answer questions about movies, theaters, showtimes, ticket prices, and seating.",
        "The dataset contains movie info, theater details, ticketing, seating, and showtime availability.",
        "If the question is about these topics, call the get_answer tool."
    ],
    tools=[
        get_answer,
    ],
    markdown=True
)

def ai_question_answer_agent(query: str):
    response = agent.run(query, stream=False)
    return response


print(ai_question_answer_agent("hi"))
