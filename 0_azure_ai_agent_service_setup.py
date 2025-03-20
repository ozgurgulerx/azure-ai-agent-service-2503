import os
from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

# Load environment variables from .env file
load_dotenv()

# Get connection string from the environment
conn_str = os.environ.get("PROJECT_CONNECTION_STRING")
if not conn_str:
    print("PROJECT_CONNECTION_STRING not found in environment")
    exit(1)

# Initialize the Azure AI Agent Client
project_client = AIProjectClient.from_connection_string(conn_str, DefaultAzureCredential())

# Create an AI Agent with gpt-4o-mini
print("Creating AI Agent with gpt-4o-mini...")
agent = project_client.agents.create_agent(
    model="gpt-4o-mini",
    name="simple-agent",
    instructions="You are a helpful assistant."
)
print(f"Agent created with ID: {agent.id}")

# Create a conversation thread
thread = project_client.agents.create_thread()
print(f"Thread created with ID: {thread.id}")

# User sends a message
print("Sending message...")
message = project_client.agents.create_message(
    thread_id=thread.id, role="user", content="What is a black hole?"
)

# Ask the agent to respond
print("Processing run...")
run = project_client.agents.create_and_process_run(thread_id=thread.id, agent_id=agent.id)
print(f"Run ID: {run.id}")

# Get the run status once
run_status = project_client.agents.get_run(thread_id=thread.id, run_id=run.id)
print(f"Run status: {run_status.status}")

# Fetch and print the messages
print("\nRetrieving conversation:")
messages = project_client.agents.list_messages(thread_id=thread.id)
for msg in messages.data:
    role = "User" if msg.role == "user" else "Assistant"
    if msg.content and hasattr(msg.content[0], 'text'):
        print(f"\n{role}: {msg.content[0].text.value}")
