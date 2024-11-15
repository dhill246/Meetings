import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_cohere import ChatCohere
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_mistralai import ChatMistralAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.checkpoint.sqlite import SqliteSaver
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime, timedelta
from typing import Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import Annotated, TypedDict
from langchain_community.chat_message_histories import SQLChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory
import pandas as pd
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, END, StateGraph, MessagesState
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from app.utils.mongo import get_meetings_for_chat

# Get necessary AI env vars
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

def reframe_the_prompt(user_message):
    # Define template to start all chat instances with:
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "The user is going to give you a prompt. If the quality of their prompt could be better, please restate it for them. Return only the restated question.",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )

    graph_builder = StateGraph(state_schema=MessagesState)

    open_ai_model = ChatOpenAI(model="gpt-4o", openai_api_key=OPENAI_API_KEY, temperature=0)

    def call_model(state: MessagesState):
        chain = prompt | open_ai_model
        response = chain.invoke(state)
        return {"messages": response}
    
    graph_builder.add_node("model", call_model)
    graph_builder.add_edge(START, "model")

    graph = graph_builder.compile()

    config = {"configurable": {"thread_id": "2309tuaeosiegije45s"}}

    input_messages = [HumanMessage(user_message)]

    # Run the workflow and store a checkpoint
    output = graph.invoke({"messages": input_messages}, config)

    # Retrieve the most recent message from the output
    user_message_reframed = output.get("messages", [])[-1] if output.get("messages") else None

    return user_message_reframed.content



def generate_ai_reply(user_message, user_id, org_name, org_id, days, employee_ids, manager_ids=None):

    # Reframe users prompt:
    user_message_reframed = reframe_the_prompt(user_message)

    # Preprocessing input
    # ------

    # Query list of meetings for the current context
    meetings_list = get_meetings_for_chat(
        org_name, org_id, days, manager_ids, employee_ids, collection_name="Meetings", type_name="One-on-One"
    )

    # Enhance data quality for passing into AI model
    context = ""
    for count, meeting in enumerate(meetings_list):
        # Ensure 'date' and 'attendees' keys exist in meeting data
        date_str = meeting.get("date", "").strftime("%m-%d-%Y") if meeting.get("date") else "Unknown Date"
        print(f"Processing Meeting #{count+1} - Date: {date_str}")

        # Initialize names to avoid reference issues
        manager_name, report_name = None, None
        for person in meeting.get("attendees", []):
            if person.get("role") == "Manager":
                manager_name = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
            elif person.get("role") == "Report":
                report_name = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()

        # Check for valid names
        if manager_name and report_name:
            attendees_section = f"between {manager_name} (manager) and {report_name} (report)"
            meeting_duration = meeting.get("meeting_duration", "unknown duration")
            raw_text = meeting.get("raw_text", "No transcript available.")
            meeting_details = (
                f"Here is meeting #{count+1}. This was a {meeting.get('type_name', 'unknown type')} on {date_str}, "
                f"{attendees_section}. This meeting lasted {meeting_duration}. Here is the transcript: {raw_text}"
            )

            context += meeting_details
        else:
            print(f"Warning: Missing manager or report name in attendees for meeting #{count+1}.")

    # Constructing LangGraph
    # ------

    # First, define the model we will use
    cohere_model = ChatCohere(model="command-r-plus", cohere_api_key=COHERE_API_KEY, temperature=0)

    # Define the prompt template with message objects
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Please help the user answer the question they ask about meetings using the following meeting data. Answer the question thoroughly, but in as few sentences as possible. No bullet points or lists. The meeting data is {context}"
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )

    class State(TypedDict):
        messages: Annotated[Sequence[BaseMessage], add_messages]
        context: str

    # Define a new graph
    graph_builder = StateGraph(state_schema=State)

    # Define the function that calls the model
    def call_model(state: State):
        chain = prompt | cohere_model
        response = chain.invoke(state)
        return {"messages": response}
    
    # Define the node with a name and the function to be called
    graph_builder.add_node("model", call_model)

    # Set the starting place for the graph to start its work
    graph_builder.add_edge(START, "model")

    # Set the ending place so the graph knows where to exit
    graph_builder.add_edge("model", END)

    # Use a SQLite database file for persistent checkpointing
    DB_URI = "checkpoints.db"

    # Use SqliteSaver within a context manager for storing, loading, and listing checkpoints
    with SqliteSaver.from_conn_string(DB_URI) as sqlite_saver:
        graph = graph_builder.compile(checkpointer=sqlite_saver)

        # Configuration for checkpointing
        config = {"configurable": {"thread_id": user_id}}

        # Define input message
        input_messages = [HumanMessage(user_message_reframed)]
        
        # Run the workflow and store a checkpoint
        output = graph.invoke({"messages": input_messages, "context": context}, config)
        
        # Retrieve the most recent message from the output
        most_recent = output.get("messages", [])[-1] if output.get("messages") else None

        # Example of loading the checkpoint
        saved_checkpoint = sqlite_saver.get(config)

        # Example of listing checkpoints
        checkpoints = list(sqlite_saver.list(config))

    # Return the content of the most recent message if available
    print(f"Recreated your prompt to be: {user_message_reframed} \n")
    return most_recent.content if most_recent else "No response generated."
