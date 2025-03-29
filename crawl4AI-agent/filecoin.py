import requests
import json

# Define the Filecoin node address (for example, a public Glif node)
node_address = 'https://api.node.glif.io'

# Prepare the JSON-RPC request payload
payload = {
    "jsonrpc": "2.0",
    "method": "Filecoin.ChainHead",
    "params": [],
    "id": 1
}

# Make the POST request to the Filecoin node
response = requests.post(node_address, json=payload)

# Check if the request was successful
if response.status_code == 200:
    # Parse and print the JSON response
    data = response.json()
    print(json.dumps(data, indent=4))
else:
    print(f"Error: {response.status_code} - {response.text}")