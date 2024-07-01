const xhttp = new XMLHttpRequest();

xhttp.onload = function() {
    response = this.responseText
    response = response.slice(3)
    response = "<p>Bot: " + response
    document.getElementById("chat").innerHTML += response + "\n"
};

document.getElementById("submit").onclick = function(e) {
    message = document.getElementById("message").value;
    document.getElementById("chat").innerHTML += "<p>User: " + message + "</p>\n"
    xhttp.open("POST", "/message", true);
    xhttp.send(message);
    document.getElementById("message").value = ""
};