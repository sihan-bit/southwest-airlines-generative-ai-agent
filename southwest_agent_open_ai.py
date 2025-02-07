from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain_openai import ChatOpenAI
from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from langchain_core.prompts.chat import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.callbacks import StreamlitCallbackHandler
from langchain_core.runnables import RunnableConfig
from langchain.memory import ConversationBufferMemory
from langchain.tools import tool
from langchain.agents import Tool
import requests
import json
import os

# ------------------------------------------------------------------------
# Constants

# Bedrock model id
MODEL_ID = "gpt-3.5-turbo"

# Bedrock model inference parameters
MODEL_KWARGS =  {
    "temperature": 0.0
}

# Southwest API URL
SOUTHWEST_API_URL = "http://127.0.0.1"

# ------------------------------------------------------------------------
# LangChain

@tool
def search_southwest_flights(event: str) -> str:
    """Search Southwest Airlines for flights on the departure date \
    between the origination airport and the destination airport \
    for the number of passengers and the number of adults.

    event: str --> The event in the format of a JSON String with the following keys: \
    departure_date: str --> The date of the flight in the format yyyy-mm-dd. \
    origination: str --> The origination airport 3-letter code. Examples: SAN, LAX, SFO. \
    destination: str --> The destination airport 3-letter code. Examples: DAL, PHX, LGA. \
    passenger_count: int --> The number of passengers. \
    adult_count: int --> The number of adults.
    """
    data = json.loads(event)
    response = requests.post(
        SOUTHWEST_API_URL,
        json=data
    )
    return response.json()['message']

def initialize_tools():
    search_southwest_flights_tool = Tool(
        name="SearchSouthwestFlightsTool", 
        func=search_southwest_flights, 
        description="""
        Use this tool with a JSON-encoded string argument like \
        "{{"departure_date": "yyyy-mm-dd", "origination": "XXX", "destination": "YYY", "passenger_count": 1, "adult_count": 1}}" \
        when you need to search for flights on Southwest Airlines. The input will always be a JSON encoded string with those arguments.
        """,
    )

    return [
        search_southwest_flights_tool
    ]

def initialize_model(model_id, model_kwargs):
    model = ChatOpenAI(
        temperature=model_kwargs['temperature'],
        model=model_id,
        openai_api_key=os.environ['OPENAI_API_KEY']
    )
    return model

def initialize_streamlit_memory():
    history = StreamlitChatMessageHistory()
    return history

def initialize_memory(streamlit_memory):
    memory = ConversationBufferMemory(
        chat_memory=streamlit_memory,
        return_messages=True,
        memory_key="chat_history",
        output_key="output"
    )
    return memory

def intialize_prompt():
    system = '''You are a Southwest Airlines customer support agent. You help customers find flights and book them.
    Your goal is to generate an answer to the employee's message in a friendly, customer support like tone.
    All tool inputs are in the format of a JSON string.

    Do not use any tools if you can answer the employee's latest message without them.
    
    You have access to the following tools:

    {tools}

    Use a json blob to specify a tool by providing an action key (tool name) and an action_input key (tool input).

    Valid "action" values: "Final Answer" or {tool_names}

    Provide only ONE action per $JSON_BLOB, as shown:

    ```
    {{
    "action": $TOOL_NAME,
    "action_input": $INPUT
    }}
    ```

    Follow this format:

    Question: input question to answer
    Thought: consider previous and subsequent steps
    Action:
    ```
    $JSON_BLOB
    ```
    Observation: action result
    ... (repeat Thought/Action/Observation N times)
    Thought: I know what to respond
    Action:
    ```
    {{
    "action": "Final Answer",
    "action_input": "Final response to human"
    }}

    Begin! Reminder to ALWAYS respond with a valid json blob of a single action. Use tools if necessary. Respond directly if appropriate. Format is Action:```$JSON_BLOB```then Observation'''

    human = '''

    {input}

    {agent_scratchpad}

    (reminder to respond in a JSON blob no matter what)'''

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", human),
        ]
    )

    return prompt

# Initialize the Model
model = initialize_model(MODEL_ID, MODEL_KWARGS)

# Initialize the Memory
streamlit_memory = initialize_streamlit_memory()
memory = initialize_memory(streamlit_memory)

# Initialize the Tools
tools = initialize_tools()

# Initialize the Agent
system_prompt = intialize_prompt()
agent = create_structured_chat_agent(
    model,
    tools,
    system_prompt
)
executor = agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        verbose=False,
        return_intermediate_steps=True,
        handle_parsing_errors=True,
    )

# ------------------------------------------------------------------------
# Streamlit

import streamlit as st

# Page title
st.set_page_config(page_title="Southwest Generative AI Agent Demo", page_icon=":plane:")
st.title("Southwest Generative AI Agent Demo")
st.caption("This is a demo of a Generative AI Assistant that can use Tools to interact with Southwest Airlines.")

# Display current chat messages
for message in streamlit_memory.messages:
    with st.chat_message(message.type):
        st.write(message.content)

# Chat Input - User Prompt 
if user_input := st.chat_input("Message"):
    with st.chat_message("human"):
        st.write(user_input)

    # As usual, new messages are added to StreamlitChatMessageHistory when the Chain is called.
    config = {"configurable": {"session_id": "any"}}

    with st.chat_message("assistant"):
        chat_history = memory.buffer_as_messages
        response = agent_executor.invoke(
            input={
                "input": f"{user_input}",
                "chat_history": chat_history,             
            },
        )
        st.write(response["output"])
