Simple chatbot using GPT-4 with with tools integrated to directly access weather forecasts. The website also has user accounts and keeps a log of chats per user in a database. Users can create and switch between multiple different chats and the website can be run with gunicorn to function asychronously.

There is a RAG system implmented, which currently requires the code to be modified per document but allows for the chatbot to access and retrieve specific details from files.
