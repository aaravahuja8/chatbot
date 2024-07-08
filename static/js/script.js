const xhttp = new XMLHttpRequest();

window.onload = function() {
    document.getElementById("chat").scrollTop = document.getElementById("chat").scrollHeight;
}

xhttp.onload = function() {
    let response = this.responseText;
    response = response.slice(3, -5);
    response = "<p>Bot: " + response + "</p>";
    document.getElementById("chat").innerHTML += response;
    document.getElementById("chat").scrollTop = document.getElementById("chat").scrollHeight;
};

function sendMessage() {
    let message = document.getElementById("message").value;
    if (message.trim() !== "") {
        document.getElementById("chat").innerHTML += "<p>User: " + message + "</p>";
        xhttp.open("POST", "/message", true);
        xhttp.setRequestHeader("Content-Type", "application/json;charset=UTF-8");
        xhttp.send(JSON.stringify({message: message}));
        document.getElementById("message").value = "";
        document.getElementById("chat").scrollTop = document.getElementById("chat").scrollHeight;
    }
};

document.getElementById("submit").onclick = function(e) {
    e.preventDefault();
    sendMessage();
};

document.getElementById("message").addEventListener("keypress", function(e) {
    if (e.key === "Enter") {
        e.preventDefault();
        sendMessage();
    }
});