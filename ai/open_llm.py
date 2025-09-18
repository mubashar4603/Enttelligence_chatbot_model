from openai import OpenAI
import requests
import json

BASE_URL = "http://20.83.161.156:5001"

def list_models():
    try:
        response = requests.get(f"{BASE_URL}/v1/models")
        if response.status_code == 200:
            data = response.json().get("data", [])
            models_dict = {model["id"]: model for model in data}
            return json.dumps(models_dict, indent=4)
        else:
            print(f"Failed with status code: {response.status_code}")
            return {}
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return {}

def ai_call_open_source(system_prompt: str, user_prompt: str, max_tokens:int = 1000, temprature=0.3, model="command-r7b:latest"):
    client = OpenAI(
        base_url=f"{BASE_URL}/v1",
        # required but ignored
        api_key='ollama',
    )

    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                'role': 'user',
                'content': user_prompt,
            }
        ],
        max_tokens=max_tokens,
        temperature=temprature,
        model=model,
    )
    response = chat_completion.choices[0].message.content
    return response


def pull_model(model_name):
    url = f"{BASE_URL}/api/pull"
    payload = {
        "model": model_name
    }

    try:
        response = requests.post(url, json=payload)
        print(f"Status Code: {response.status_code}")
        try:
            return response.json()
        except ValueError:
            print("Non-JSON Response:", response.text)
            return {}
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return {}
    

print(list_models())