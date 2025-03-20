import os
import time
from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

# Load environment variables
load_dotenv()

# Get connection string from environment
conn_str = os.getenv("PROJECT_CONNECTION_STRING")
if not conn_str:
    print("ERROR: PROJECT_CONNECTION_STRING not found in environment.")
    exit(1)

# Initialize Azure AI Agent Client
try:
    project_client = AIProjectClient.from_connection_string(
        conn_str=conn_str, 
        credential=DefaultAzureCredential()
    )
    print("✅ Successfully connected to Azure AI Agent Service.")
except Exception as e:
    print(f"ERROR: Failed to connect to Azure AI Agent Service. {e}")
    exit(1)

# Create an AI Agent (Conversational Chatbot)
try:
    print("\n🗣 Creating AI Chatbot Agent...")
    agent = project_client.agents.create_agent(
        model="gpt-4o-mini",
        name="context-limited-chatbot",
        instructions="You are a conversational assistant that keeps only the last 5 messages. "
                     "Every 5th message is a summary of the previous 4 messages. "
                     "Ensure responses are informative and unique."
    )
    print(f"✅ Agent created successfully! ID: {agent.id}")
except Exception as e:
    print(f"ERROR: Failed to create agent. {e}")
    exit(1)

# Create a conversation thread
try:
    thread = project_client.agents.create_thread()
    print(f"✅ Thread created successfully! ID: {thread.id}")
except Exception as e:
    print(f"ERROR: Failed to create thread. {e}")
    exit(1)

# Store messages in memory instead of API deletion
message_history = []  # Keep track of last 5 messages

# Function to manage messages and summarize every 5th message
def manage_messages(thread_id, user_input):
    """ Maintains only the last 5 messages and generates summary every 5th message. """
    
    # Append new message to history
    message_history.append(user_input)

    # If there are more than 4 user messages, generate a summary
    if len(message_history) >= 5:
        summary_content = "Summarize the following conversation: " + " | ".join(message_history[-4:])
        
        summary_message = project_client.agents.create_message(
            thread_id=thread_id,
            role="user",
            content=summary_content
        )
        print(f"📄 Generating summary: {summary_content}")
        
        # Replace the last 4 messages with the summary
        message_history[-4:] = [summary_content]  # Only keep summary as context

    # Ensure only last 5 messages are kept
    if len(message_history) > 5:
        message_history.pop(0)  # Remove oldest message from memory

    # Send the new user message
    message = project_client.agents.create_message(
        thread_id=thread_id,
        role="user",
        content=user_input
    )
    print(f"📝 User: {user_input}")
    return message

# Function to process agent response
def run_agent(thread_id, agent_id):
    """ Runs the agent and retrieves its response. """
    try:
        run = project_client.agents.create_and_process_run(thread_id=thread_id, agent_id=agent_id)
        time.sleep(2)  # Short delay to allow processing
        
        # Fetch the latest AI response
        messages = project_client.agents.list_messages(thread_id=thread_id)
        
        if messages.data:
            last_response = messages.data[-1].content[0].text.value  # Ensure correct response retrieval
        else:
            last_response = "No response received."
        
        print(f"🤖 Chatbot: {last_response}")
        return last_response
    except Exception as e:
        print(f"ERROR: Failed to process agent run. {e}")
        return None

# Simulating a Conversation
user_inputs = [
    "Tell me about space travel.",
    "What are the latest advancements in AI?",
    "Can you explain quantum computing?",
    "What are some healthy diet tips?",
    "How does machine learning work?",  # This triggers a summary
    "Can you suggest a good book?",
    "Tell me about black holes."
]

for user_input in user_inputs:
    manage_messages(thread.id, user_input)
    run_agent(thread.id, agent.id)

# Cleanup: Delete the thread after the session
try:
    project_client.agents.delete_thread(thread_id=thread.id)
    print(f"🧹 Session ended: Thread {thread.id} deleted to clear memory.")
except Exception as e:
    print(f"ERROR: Failed to delete thread. {e}")
