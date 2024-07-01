import os
from openai import OpenAI
from flask import Flask, render_template, request, flash, redirect, url_for, session
import json, requests, markdown2, asyncio

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
client = OpenAI()
client.api_key = os.getenv("API_KEY")

from werkzeug.middleware.proxy_fix import ProxyFix

app.wsgi_app = ProxyFix(
    app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
)

def get_weather(location):
    url = "http://api.weatherapi.com/v1/current.json?key=bd9253c192f247cb9c835024241906&q=" + location
    response = requests.get(url)
    data = response.json()
    return data

tools=[
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Gets the current weather at the specified location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The name of the town or city"
                    }
                },
            "required": ["location"]
            }
        }
    }
]

def get_openai_response(messages):
    print("b")
    response = client.chat.completions.create(
        model="gpt-4o",
        tools=tools,
        messages=messages,
        temperature=1,
        max_tokens=4095,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )
    return response.choices[0].message.content

def get_weather_response(messages):
    print("a")
    response = client.chat.completions.create(
        model="gpt-4o",
        tools=tools,
        messages=messages,
        temperature=1,
        max_tokens=4095,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    if (response.choices[0].message.tool_calls != None):
        arguments = response.choices[0].message.tool_calls[0].function.arguments
        data = json.loads(arguments)
        location = data['location']
        weather_data = get_weather(location)
        messages.append({"role": "system", "content": "Answer this weather information. If there is no information, say so to the user."})
        messages.append({"role": "user", "content": f"Here is the weather in {location}: {weather_data}"})
        response = client.chat.completions.create(
            model="gpt-4o",
            tools=tools,
            messages=messages,
            temperature=1,
            max_tokens=4095,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )
    print(response.choices[0].message.content)
    return response.choices[0].message.content

@app.before_request
def ensure_messages_in_session():
    if 'messages' not in session:
        session['messages'] = [{"role": "system", "content": "You are a helpful assistant."}]

@app.route("/", methods=["GET", "POST"])
def index():

    return render_template("index.html")

@app.route("/message", methods=["POST"])
def message():
    query = request.data.decode("utf-8")
    session['messages'].append({"role": "user", "content": query})
    #result2 = get_weather_response([{"role": "system", "content": "You are a helpful assistant."}, {"role": "user", "content": "who is amity blight?"}])
    result = get_weather_response(session['messages'])
    session['messages'].append({"role": "assistant", "content": result})
    if (len(session['messages']) > 11):
        session['messages'].pop(1)
        session['messages'].pop(1)
    session.modified = True
    html_result = markdown2.markdown(result)
    return html_result

from gevent.pywsgi import WSGIServer

if __name__ == "__main__":
    http_server = WSGIServer(('0.0.0.0', 8000), app)
    http_server.serve_forever()
    app.run(debug=True)