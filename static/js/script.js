window.onload = function() {
    document.getElementById("chat").scrollTop = document.getElementById("chat").scrollHeight;
};

function sendMessage() {
    const xhttp = new XMLHttpRequest();

    xhttp.onload = function() {
    let response = JSON.parse(this.responseText);
    result = response.result
    result = result.slice(3, -5);
    result = "<p>Bot: " + result + "</p>";
    document.getElementById("chat").innerHTML += result;
    document.getElementById("chat").scrollTop = document.getElementById("chat").scrollHeight;
    if (response.title != "") {
        let i = JSON.parse(this.responseText).index;
        document.getElementById("chat" + i).innerHTML = response.title
    }
    };

    let message = document.getElementById("message").value;
    if (message.trim() !== "") {
        document.getElementById("chat").innerHTML += "<p>User: " + message + "</p>";
        xhttp.open("POST", "/message", true);
        xhttp.setRequestHeader("Content-Type", "application/json;charset=UTF-8");
        xhttp.send(JSON.stringify({message: message}));
        document.getElementById("message").value = "";
        document.getElementById("chat").scrollTop = document.getElementById("chat").scrollHeight;
    }
}

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

function deleteChat() {
    const xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
        if (this.status === 200) {
            document.getElementById("chat").innerHTML = "";
            document.getElementById("chats").innerHTML = "";
            let response = JSON.parse(this.responseText);
            for (let i=0; i < response.messages.length; i=i+2) {
                document.getElementById("chat").innerHTML += "<p>User: " + response.messages[i] + "</p>";
                document.getElementById("chat").innerHTML += "<p>Bot: " + response.messages[i+1] + "</p>";
            }
            for (let i=0; i < response.titles.length; i++) {
                document.getElementById("chats").innerHTML += "<option id='chat" + i + "' value='" + i + "'>" +
                response.titles[i] + "</option>";
                document.getElementById("chats").value = response.index
            }
        } else {
            alert("Failed to delete chat.");
        }
    };
    xhttp.open("DELETE", "/delete", true);
    xhttp.send();
}

function updateChat() {
    const xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
        if (this.status === 200) {
            document.getElementById("chat").innerHTML = "";
            let response = JSON.parse(this.responseText);
            for (let i=0; i < response.messages.length; i=i+2) {
                document.getElementById("chat").innerHTML += "<p>User: " + response.messages[i] + "</p>";
                document.getElementById("chat").innerHTML += "<p>Bot: " + response.messages[i+1] + "</p>";
            }
        } else {
            alert("Failed to select chat.");
        }
    };
    xhttp.open("GET", "/update?index=" + document.getElementById("chats").value, true);
    xhttp.send();
}

function newChat() {
    const xhttp = new XMLHttpRequest();
    xhttp.onload = function() {
        if (this.status === 200) {
            document.getElementById("chat").innerHTML = "";
            let i = JSON.parse(this.responseText).index;
            document.getElementById("chats").innerHTML += "<option id='chat" + i + "' value='" + i + "'>New Chat</option>";
            document.getElementById("chats").value = i
        } else {
            alert("Failed to create new chat.");
        }
    };
    xhttp.open("GET", "/create", true);
    xhttp.send();
}