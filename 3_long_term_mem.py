import os
import psycopg2  # PostgreSQL driver
from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

# Load environment variables
load_dotenv()
conn_str = os.getenv("PROJECT_CONNECTION_STRING")
db_connection_str = os.getenv("AZURE_COSMOSDB_PG_CONNECTION_STRING")

# Initialize Azure AI Agent Client
project_client = AIProjectClient.from_connection_string(conn_str, DefaultAzureCredential())

# Connect to Azure Cosmos DB for PostgreSQL
conn = psycopg2.connect(db_connection_str)
cursor = conn.cursor()

# **1️⃣ Create a Table for Chat Messages (Run Once)**
cursor.execute("""
    CREATE TABLE IF NOT EXISTS ChatMessages (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255),
        thread_id VARCHAR(255),
        role VARCHAR(50),
        message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()

# **2️⃣ Function to Retrieve or Create a User Thread**
def get_or_create_thread(user_id):
    cursor.execute("SELECT thread_id FROM ChatMessages WHERE user_id = %s LIMIT 1", (user_id,))
    row = cursor.fetchone()

    if row:
        return row[0]  # Return existing thread ID
    
    thread = project_client.agents.create_thread()
    return thread.id  # Return new thread ID

# **3️⃣ Function to Store Messages in CosmosDB PostgreSQL**
def store_message(user_id, thread_id, role, message):
    cursor.execute("INSERT INTO ChatMessages (user_id, thread_id, role, message) VALUES (%s, %s, %s, %s)",
                   (user_id, thread_id, role, message))
    conn.commit()

# **4️⃣ Function to Retrieve Chat History**
def get_chat_history(user_id):
    cursor.execute("SELECT role, message FROM ChatMessages WHERE user_id = %s ORDER BY created_at", (user_id,))
    return cursor.fetchall()

# **5️⃣ Persistent AI Memory Example**
user_id = "user_123"
thread_id = get_or_create_thread(user_id)

# User sends a message
user_message = "What advice did you give me last time?"
project_client.agents.create_message(thread_id=thread_id, role="user", content=user_message)
store_message(user_id, thread_id, "user", user_message)

# AI Generates a Response
project_client.agents.create_and_process_run(thread_id=thread_id, agent_id="your_agent_id")

# Fetch AI response
messages = project_client.agents.list_messages(thread_id=thread_id)
ai_response = messages.data[-1].content[0].text.value if messages.data else "No response received."

# Store AI response
store_message(user_id, thread_id, "assistant", ai_response)

# Retrieve Full Chat History
chat_history = get_chat_history(user_id)
print("\n🗂 Chat History:")
for role, msg in chat_history:
    print(f"{role}: {msg}")
