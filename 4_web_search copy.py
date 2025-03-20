import os
import time
from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    AgentStreamEvent,
    MessageDeltaChunk,
    RunStepDeltaChunk,
    ThreadMessage,
    ThreadRun,
    RunStep,
    BingGroundingTool,
    MessageRole,
    MessageDeltaTextContent,
    MessageDeltaTextUrlCitationAnnotation,
)
from azure.identity import DefaultAzureCredential

# Load environment variables
load_dotenv()

# Retrieve required environment variables
conn_str = os.getenv("PROJECT_CONNECTION_STRING")
model_name = os.getenv("MODEL_DEPLOYMENT_NAME")
bing_conn_name = os.getenv("BING_CONNECTION_NAME")

# Validate environment variables
if not conn_str or not model_name or not bing_conn_name:
    print("❌ Missing required environment variables. Ensure PROJECT_CONNECTION_STRING, MODEL_DEPLOYMENT_NAME, and BING_CONNECTION_NAME are set.")
    exit(1)

# Initialize Azure AI Project Client
project_client = AIProjectClient.from_connection_string(
    conn_str=conn_str, credential=DefaultAzureCredential()
)

# Retrieve Bing Search Connection
print("🔍 Retrieving Bing connection...")
bing_connection = project_client.connections.get(connection_name=bing_conn_name)
bing = BingGroundingTool(connection_id=bing_connection.id)
print(f"✅ Bing Connection ID: {bing_connection.id}")

# Create AI Agent with Bing Web Search Tool
print("🛠 Creating AI Agent...")
agent = project_client.agents.create_agent(
    model=model_name,
    name="web-search-agent",
    instructions="You are an AI assistant that retrieves real-time web search results from Bing.",
    tools=bing.definitions,
)
print(f"✅ Agent created with ID: {agent.id}")

# Create a conversation thread
thread = project_client.agents.create_thread()
print(f"✅ Thread created with ID: {thread.id}")

# User sends a search query
query = "Latest advancements in quantum computing"
print(f"🔍 Sending web search query: {query}")
message = project_client.agents.create_message(thread_id=thread.id, role=MessageRole.USER, content=query)
print(f"✅ Created message, ID: {message.id}")

# Process the run (triggers the Bing Search tool)
print("⏳ Processing run...")
run = project_client.agents.create_and_process_run(thread_id=thread.id, agent_id=agent.id)
print(f"✅ Run started with ID: {run.id}")

# Wait for the run to complete
while True:
    run_status = project_client.agents.get_run(thread_id=thread.id, run_id=run.id)
    if run_status.status not in ["queued", "in_progress"]:
        break
    time.sleep(2)

print(f"✅ Final Run status: {run_status.status}")

# Stream AI responses in real-time
print("\n📥 Streaming AI response:")
with project_client.agents.create_stream(thread_id=thread.id, agent_id=agent.id) as stream:
    for event_type, event_data, _ in stream:
        if isinstance(event_data, MessageDeltaChunk):
            print(f"Text delta received: {event_data.text}")
            if event_data.delta.content and isinstance(event_data.delta.content[0], MessageDeltaTextContent):
                delta_text_content = event_data.delta.content[0]
                if delta_text_content.text and delta_text_content.text.annotations:
                    for delta_annotation in delta_text_content.text.annotations:
                        if isinstance(delta_annotation, MessageDeltaTextUrlCitationAnnotation):
                            print(f"🔗 URL Citation: [{delta_annotation.url_citation.title}]({delta_annotation.url_citation.url})")

        elif isinstance(event_data, RunStepDeltaChunk):
            print(f"🛠 RunStepDeltaChunk received. ID: {event_data.id}")

        elif isinstance(event_data, ThreadMessage):
            print(f"💬 ThreadMessage created. ID: {event_data.id}, Status: {event_data.status}")

        elif isinstance(event_data, ThreadRun):
            print(f"📌 ThreadRun status: {event_data.status}")
            if event_data.status == "failed":
                print(f"❌ Run failed. Error: {event_data.last_error}")

        elif isinstance(event_data, RunStep):
            print(f"🔄 RunStep type: {event_data.type}, Status: {event_data.status}")

        elif event_type == AgentStreamEvent.ERROR:
            print(f"⚠️ An error occurred. Data: {event_data}")

        elif event_type == AgentStreamEvent.DONE:
            print("✅ Stream completed.")

        else:
            print(f"⚡ Unhandled Event Type: {event_type}, Data: {event_data}")

# Retrieve the last AI response from the agent
print("\n📜 Retrieving last AI response:")
messages = project_client.agents.list_messages(thread_id=thread.id)
response_message = next((msg for msg in messages if msg.role == MessageRole.AGENT), None)

if response_message:
    print("\n📜 **Agent Response:**")
    for text_message in response_message.text_messages:
        print(f"{text_message.text.value}")

    for annotation in response_message.url_citation_annotations:
        print(f"🔗 **URL Citation:** [{annotation.url_citation.title}]({annotation.url_citation.url})")

# Cleanup: Delete the agent when done
project_client.agents.delete_agent(agent.id)
print("🗑️ Deleted agent.")
