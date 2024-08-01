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
weatherurl = "https://api.weatherapi.com/v1/current.json?key=" + os.getenv("WEATHER_API_KEY")
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

def get_weather(location):
    response = requests.get(weatherurl + "&q=" + location)
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
            recentmessages.pop(1)
            recentmessages.pop(1)
            recentmessages.pop(1)
        else:
            recentmessages.pop(1)

    if current_user.is_authenticated:
        if len(recentmessages) > 4 and recentmessages[-3]['role'] == "system":
            chat.append(recentmessages[-4])
            chat.append(recentmessages[-3])
            chat.append(recentmessages[-2])
            chat.append(recentmessages[-1])
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