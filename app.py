from gevent import monkey

monkey.patch_all()

from openai import OpenAI
from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import DataRequired
from flask_login import login_required, logout_user, login_user, current_user, LoginManager, UserMixin
from werkzeug.security import check_password_hash, generate_password_hash
from flask_pymongo import PyMongo
from bson import ObjectId
import json, requests, markdown2, os, datetime

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
weatherurlc = "https://api.weatherapi.com/v1/current.json?key=" + os.getenv("WEATHER_API_KEY")
weatherurlf = "https://api.weatherapi.com/v1/forecast.json?key=" + os.getenv("WEATHER_API_KEY")
weatherurla = "https://api.weatherapi.com/v1/astronomy.json?key=" + os.getenv("WEATHER_API_KEY")
app.config["MONGO_URI"] = os.getenv("MONGODB_URI")
mongo = PyMongo(app)
chathistory = mongo.db.aarav_chat_history
users = mongo.db.aarav_chat_users
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "/"

# from werkzeug.middleware.proxy_fix import ProxyFix
#
# app.wsgi_app = ProxyFix(
#     app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1
# )

class User(UserMixin):
    def __init__(self, user):
        self.id = str(user['_id'])
        self.username = user['username']
        self.password_hash = user['password']

    def get_id(self):
        return str(self.id)

    @staticmethod
    def get(user_id):
        user = users.find_one({'_id': ObjectId(user_id)})
        if user:
            return User(user)
        else:
            return None

@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

class SignUpForm(FlaskForm):
    username = StringField("Enter a username: ", validators=[DataRequired()])
    password = PasswordField("Enter a password: ", validators=[DataRequired()])
    submit = SubmitField("Sign Up")

class SignInForm(FlaskForm):
    username = StringField("Enter your username: ", validators=[DataRequired()])
    password = PasswordField("Enter your password: ", validators=[DataRequired()])
    rememberme = BooleanField("Keep me logged in")
    submit = SubmitField("Log In")

def get_current_weather(location):
    response = requests.get(weatherurlc + "&q=" + location)
    data = response.json()
    return data

def get_weather_forecast(location, days):
    response = requests.get(weatherurlf + "&q=" + location + "&days=" + days)
    data = response.json()
    returninfo = {
        "location": data['location'],
        "forecast": {
            "forecastday": []
        }
    }
    for day in data['forecast']['forecastday']:
        tempdict = {
            "date": day['date'],
            "day": day['day'],
            "astro": day['astro']
        }
        returninfo['forecast']['forecastday'].append(tempdict)
    return returninfo

def get_astronomy_data(location, date):
    response = requests.get(weatherurla + "&q=" + location + "&dt=" + date)
    data = response.json()
    return data

def rag(query):
    from langchain_openai import ChatOpenAI
    from langchain_community.document_loaders import TextLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_chroma import Chroma
    from langchain_openai import OpenAIEmbeddings
    from langchain.chains.combine_documents import create_stuff_documents_chain
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from typing import Dict
    from langchain_core.runnables import RunnablePassthrough
    from langchain_core.messages import HumanMessage

    chat = ChatOpenAI(model="gpt-4o", temperature=1)
    loader = TextLoader("example.txt")
    data = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    all_splits = text_splitter.split_documents(data)
    vectorstore = Chroma.from_documents(documents=all_splits, embedding=OpenAIEmbeddings())
    retriever = vectorstore.as_retriever()

    SYSTEM_TEMPLATE = """
    Answer the user's questions based on the below context. 
    If the context doesn't contain any relevant information to the question, don't make something up and just say "I don't know":

    <context>
    {context}
    </context>
    """

    question_answering_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                SYSTEM_TEMPLATE,
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )

    document_chain = create_stuff_documents_chain(chat, question_answering_prompt)

    def parse_retriever_input(params: Dict):
        return params["messages"][-1].content

    retrieval_chain = RunnablePassthrough.assign(
        context=parse_retriever_input | retriever,
    ).assign(
        answer=document_chain,
    )

    response = retrieval_chain.invoke(
        {
        "messages": [
            HumanMessage(content=query)
        ],
    }
    )

    return response['answer']

tools=[
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
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
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather_forecast",
            "description": "Gets the forecasted weather at the specified location for a specified number of days up to 3",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The name of the town or city"
                    },
                    "days": {
                        "type": "string",
                        "description": "The number of days to get the forecast for"
                    }
                },
                "required": ["location", "days"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_astronomy_data",
            "description": "Gets the basic astronomy data such as sunrise, sunset, moonrise, moonset, moon phase, "
                           "and illumination at the specified location on the specified date",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The name of the town or city"
                    },
                    "date": {
                        "type": "string",
                        "description": "The date to get the data for in yyyy-mm-dd format"
                    }
                },
                "required": ["location", "date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "rag",
            "description": "Gets information about the plot of the movie Despicable Me 4",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user's query about the movie"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

def get_openai_response(messages):
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

    while (response.choices[0].message.tool_calls != None):
        name = response.choices[0].message.tool_calls[0].function.name
        match name:
            case "get_current_weather":
                arguments = response.choices[0].message.tool_calls[0].function.arguments
                data = json.loads(arguments)
                location = data['location']
                weather_data = get_current_weather(location)
                messages.append({"role": "system",
                                 "content": "Answer this weather information. If there is no information, say so to the user."})
                messages.append({"role": "user", "content": f"Here is the weather in {location}: {weather_data}"})
            case "get_weather_forecast":
                arguments = response.choices[0].message.tool_calls[0].function.arguments
                data = json.loads(arguments)
                location = data['location']
                days = data['days']
                weather_data = get_weather_forecast(location, days)
                messages.append({"role": "system",
                                 "content": "Answer this weather information. If there is no information, say so to the user."})
                messages.append({"role": "user", "content": f"Here is the weather forecast for {location}: {weather_data}"})
            case "get_astronomy_data":
                arguments = response.choices[0].message.tool_calls[0].function.arguments
                data = json.loads(arguments)
                location = data['location']
                date = data['date']
                astronomy_data = get_astronomy_data(location, date)
                messages.append({"role": "system",
                                 "content": "Answer this astronomy information. If there is no information, say so to the user."})
                messages.append({"role": "user", "content": f"Here is the astronomy data for {location}: {astronomy_data}"})
            case "rag":
                arguments = response.choices[0].message.tool_calls[0].function.arguments
                data = json.loads(arguments)
                query = data['query']
                result = rag(query)
                print(result)
                messages.append({"role": "system",
                                 "content": "Answer this movie information. If there is no information, say so to the user."})
                messages.append(
                    {"role": "user", "content": f"Here is the query result for {query}: {result}"})

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

@app.route("/")
def index():
    previous_messages = []

    if current_user.is_authenticated:
        chats = chathistory.find_one({'username': current_user.username})
        if chats is None:
            newchat = {
                'username': current_user.username,
                'chats': [[{"role": "system", "content": "You are a helpful assistant."}]],
                'last_updated': [datetime.datetime.utcnow()],
                'titles': ["New Chat"]
            }
            chathistory.insert_one(newchat)
            session['currentchat'] = 0
            chattitles = ["New Chat"]
        else:
            if session['currentchat'] == "None":
                maxtime = datetime.datetime(1970, 1, 1, 0, 0, 0, 0)
                maxindex = 0
                for i in range(len(chats['last_updated'])):
                    if chats['last_updated'][i] > maxtime:
                        maxtime = chats['last_updated'][i]
                        maxindex = i
                session['currentchat'] = maxindex
            messages = chats['chats'][session['currentchat']]
            i = 1
            for msg in messages[1:]:
                if msg['role'] == "system":
                    i = 0
                elif i < 1:
                    i = i + 1
                else:
                    i = 1
                    previous_messages.append(markdown2.markdown(msg['content'])[3:-5])
            chattitles = chats['titles']
    else:
        session['currentchat'] = "None"
        session['messages'] = [{"role": "system", "content": "You are a helpful assistant."}]
        chattitles = []

    return render_template("index.html", previous_messages=previous_messages,
                           len=len(previous_messages), chats=chattitles, chatlength=len(chattitles),
                           current=session['currentchat'])

@app.route("/message", methods=["POST"])
def message():
    if current_user.is_authenticated:
        recentmessages = [{"role": "system", "content": "You are a helpful assistant."}]
        chatentry = chathistory.find_one({'username': current_user.username})
        chat = chatentry['chats'][session['currentchat']]
        for msg in chat[-10:]:
            if msg != {"role": "system", "content": "You are a helpful assistant."}:
                recentmessages.append(msg)
    else:
        recentmessages = session['messages']

    query = request.get_json()['message']
    recentmessages.append({"role": "user", "content": query})
    result = get_weather_response(recentmessages)
    recentmessages.append({"role": "assistant", "content": result})
    title = ""

    if len(recentmessages) > 11:
        recentmessages.pop(1)
        if recentmessages[1]['role'] == "system":
            while recentmessages[1]['role'] == "system":
                recentmessages.pop(1)
                recentmessages.pop(1)
            recentmessages.pop(1)
        else:
            recentmessages.pop(1)

    if current_user.is_authenticated:
        if len(recentmessages) > 4 and recentmessages[-3]['role'] == "system":
            i=4
            while len(recentmessages) > i and recentmessages[-i+1]['role'] == "system":
                i = i+2
            i = i-2
            while i > 0:
                chat.append(recentmessages[-i])
                i = i-1
        else:
            chat.append(recentmessages[-2])
            chat.append(recentmessages[-1])
        newchatlist = chatentry['chats']
        newchatlist[session['currentchat']] = chat
        newupdatedlist = chatentry['last_updated']
        newupdatedlist[session['currentchat']] = datetime.datetime.utcnow()
        chathistory.update_one({'username': current_user.username},
                               {"$set": {'chats': newchatlist, 'last_updated': newupdatedlist}})
        if (len(chat) == 3) or (len(chat) == 5) or ((len(chat) % 12) == 1):
            temp = recentmessages.copy()
            temp.append({"role": "user",
                         "content": "Give this conversation a name, and say only the name and nothing else, and without quotations"})
            title = get_weather_response(temp)
            newtitlelist = chatentry['titles']
            newtitlelist[session['currentchat']] = title
            chathistory.update_one({'username': current_user.username}, {"$set": {'titles': newtitlelist}})
    else:
        session['messages'] = recentmessages
        session.modified = True

    html_result = markdown2.markdown(result)
    response = {
        "result": html_result,
        "title": title,
        "index": str(session['currentchat'])
    }
    return jsonify(response)

@app.route("/signup", methods=["GET", "POST"])
def signup():
    form = SignUpForm()

    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        user = users.find_one({'username': username})
        if user is None:
            users.insert_one({'username': username, 'password': generate_password_hash(password)})
            return redirect(url_for('login'))
        else:
            flash("Username already exists!")

    return render_template("signup.html", form=form)

@app.route("/login", methods=["GET", "POST"])
def login():
    form = SignInForm()

    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        user = users.find_one({'username': username})
        if user is None:
            flash("User does not exist")
        elif check_password_hash(user['password'], password):
            user_obj = User(user)
            login_user(user_obj, form.rememberme.data)
            session['messages'] = []
            return redirect(url_for('index'))
        else:
            flash("Incorrect password")

    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    session['currentchat'] = "None"
    return redirect(url_for('index'))

@app.route("/delete", methods=["DELETE"])
@login_required
def delete():
    chats = chathistory.find_one({'username': current_user.username})
    chats['chats'].pop(session['currentchat'])
    chats['titles'].pop(session['currentchat'])
    chats['last_updated'].pop(session['currentchat'])
    chathistory.update_one({'username': current_user.username},
                           {"$set": {'chats': chats['chats'],
                                     'titles': chats['titles'],
                                     'last_updated': chats['last_updated']}})

    previous_messages = []
    if len(chats['chats']) > 0:
        maxtime = datetime.datetime(1970, 1, 1, 0, 0, 0, 0)
        maxindex = 0
        for i in range(len(chats['last_updated'])):
            if chats['last_updated'][i] > maxtime:
                maxtime = chats['last_updated'][i]
                maxindex = i
        session['currentchat'] = maxindex
        messages = chats['chats'][session['currentchat']]
        i = 1
        for msg in messages[1:]:
            if msg['role'] == "system":
                i = 0
            elif i < 1:
                i = i + 1
            else:
                i = 1
                previous_messages.append(markdown2.markdown(msg['content'])[3:-5])
        chattitles = chats['titles']
    else:
        chattitles = ["New Chat"]
        chathistory.update_one({'username': current_user.username},
                               {"$set": {'chats': [[{"role": "system", "content": "You are a helpful assistant."}]],
                                         'titles': chattitles,
                                         'last_updated': [datetime.datetime.utcnow()]}})
    response = {
        "messages": previous_messages,
        "titles": chattitles,
        "index": str(session['currentchat'])
    }
    return jsonify(response)

@app.route("/update")
@login_required
def update():
    num = int(request.args.get("index"))
    session['currentchat'] = num
    previous_messages = []
    chats = chathistory.find_one({'username': current_user.username})
    messages = chats['chats'][session['currentchat']]
    i = 1
    for msg in messages[1:]:
        if msg['role'] == "system":
            i = 0
        elif i < 1:
            i = i + 1
        else:
            i = 1
            previous_messages.append(markdown2.markdown(msg['content'])[3:-5])

    response = {
        "messages": previous_messages,
    }
    return jsonify(response)

@app.route("/create")
@login_required
def create():
    chats = chathistory.find_one({'username': current_user.username})
    session['currentchat'] = len(chats['chats'])
    chats['chats'].append([{"role": "system", "content": "You are a helpful assistant."}])
    chats['titles'].append("New Chat")
    chats['last_updated'].append(datetime.datetime.utcnow())
    chathistory.update_one({'username': current_user.username},
                           {"$set": {'chats': chats['chats'],
                                     'titles': chats['titles'],
                                     'last_updated': chats['last_updated']}})
    response = {
        "index": str(session['currentchat'])
    }
    return jsonify(response)