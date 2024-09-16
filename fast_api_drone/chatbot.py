import openai
import json

  

# Predefined API command templates (curl commands)
api_commands = {
    "connect_all_drones": "curl -X POST 'http://localhost:8000/connect_all_drones'",
    "connect_drone": "curl -X POST 'http://localhost:8000/connect_drone' -H 'Content-Type: application/json' -d '{{\"drone_id\": \"{drone_id}\"}}'",
    "get_all_telemetry": "curl -X GET 'http://localhost:8000/get_all_telemetry'",
    "get_telemetry": "curl -X GET 'http://localhost:8000/get_telemetry/{drone_id}'",
    "update_drone_mode": "curl -X POST 'http://localhost:8000/update_drone_mode/{drone_id}/{mode}' -H 'Content-Type: application/json'",
    # Add more API commands as necessary
}

def get_gpt4_response(user_command: str):
    """Use GPT-4 to process the user command and return an appropriate API command."""
    
    prompt = f"""
    You are a drone assistant. Based on the user command, output the appropriate API command.
    
    Command: {user_command}
    
    API Commands: {json.dumps(api_commands, indent=2)}
    
    Your task is to determine which API command is the closest match and fill in any necessary parameters such as drone_id or mode.
    
    Respond with the exact curl command or an error message if you can't interpret the command.
    """
    
    # Call GPT-4 with the user command using OpenAI ChatCompletion endpoint
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are a drone assistant."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=100,
        temperature=0.2,
    )
    
    # Extract the response text
    gpt_output = response['choices'][0]['message']['content'].strip()
    
    return gpt_output

def run_console_chatbot():
    """Run the chatbot in a console loop, allowing the user to input natural language commands."""
    print("Drone Control Chatbot (using GPT-4). Type 'exit' to quit.")
    
    while True:
        user_command = input("Enter your drone command: ")
        
        if user_command.lower() == 'exit':
            print("Exiting chatbot.")
            break
        
        # Get the response from GPT-4 and display it
        result = get_gpt4_response(user_command)
        
        print(f"GPT-4 Response: {result}")

# Run the console chatbot
if __name__ == "__main__":
    run_console_chatbot()
