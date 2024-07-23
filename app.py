from gevent import monkey

monkey.patch_all()

from openai import OpenAI
from flask import Flask, render_template, request, session, redirect, url_for, flash
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
        chats = chathistory.find({'username': current_user.username}).sort("last_updated", -1)
        if chathistory.count_documents({'username': current_user.username}) == 0:
            newchat = {
                'username': current_user.username,
                'messages': [{"role": "system", "content": "You are a helpful assistant."}],
                'last_updated': datetime.datetime.utcnow()
            }
            insert = chathistory.insert_one(newchat)
            session['currentchat'] = str(insert.inserted_id)
        else:
            messages = chats[0]['messages']
            session['currentchat'] = str(chats[0]['_id'])
            i = 1
            for msg in messages[1:]:
                if msg['role'] == "system":
                    i = 0
                elif i < 1:
                    i = i + 1
                else:
                    i = 1
                    previous_messages.append(markdown2.markdown(msg['content'])[3:-5])
    else:
        session['currentchat'] = "None"
        session['messages'] = [{"role": "system", "content": "You are a helpful assistant."}]

    session.modified = True
    return render_template("index.html", previous_messages=previous_messages,
                           len=len(previous_messages))

@app.route("/message", methods=["POST"])
def message():
    if current_user.is_authenticated:
        recentmessages = [{"role": "system", "content": "You are a helpful assistant."}]
        chatentry = chathistory.find_one({'_id': ObjectId(session['currentchat'])})
        for msg in chatentry['messages'][-10:]:
            if msg != {"role": "system", "content": "You are a helpful assistant."}:
                recentmessages.append(msg)
    else:
        recentmessages = session['messages']

    query = request.get_json()['message']
    recentmessages.append({"role": "user", "content": query})
    result = get_weather_response(recentmessages)
    recentmessages.append({"role": "assistant", "content": result})
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
            chatentry['messages'].append(recentmessages[-4])
            chatentry['messages'].append(recentmessages[-3])
            chatentry['messages'].append(recentmessages[-2])
            chatentry['messages'].append(recentmessages[-1])
        else:
            chatentry['messages'].append(recentmessages[-2])
            chatentry['messages'].append(recentmessages[-1])
        chathistory.update_one({'_id': ObjectId(session['currentchat'])},
                               {"$set": {'messages': chatentry['messages'], 'last_updated': datetime.datetime.utcnow()}})
    else:
        session['messages'] = recentmessages
    html_result = markdown2.markdown(result)
    return html_result

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
    chathistory.update_one({'_id': ObjectId(session['currentchat'])},
                           {"$set": {'messages': [{"role": "system", "content": "You are a helpful assistant."}],
                                     'last_updated': datetime.datetime.utcnow()}})
    return {}
