var next_results = "?count=50";

function sendSearch() {
    var base_url = "/feedback/search";
    var xhr = new XMLHttpRequest();
    xhr.open("GET", base_url + next_results, true);

    xhr.send();
    xhr.addEventListener("load", function(ev) {
	if (xhr.readyState == 4 && xhr.status == 200) {
	    processResponse(xhr.responseText);
	}
    });
}

function setStar(id_str, element, is_set) {
    if (is_set) {
	element.style.color = "orange";
	sendCommand(id_str, "star", function() {
	    element.style.color = "orange";
	    element.innerHTML = "★";
	});
    } else {
	element.style.color = "gray";
	sendCommand(id_str, "", function() {
	    element.style.color = "black";
	    element.innerHTML = "☆";
	});
    }
}


function sendCommand(id, name, callback) {
    var base_url = "/feedback/command";
    var command = "?id=" + id + "&name=" + name;
    var xhr = new XMLHttpRequest();
    xhr.open("GET", base_url + command, true);

    xhr.send();
    
    xhr.addEventListener("load", function(ev) {
	if (xhr.readyState == 4 && xhr.status == 200) {
	    callback();
	}
    });
}

function modifyTweet(tweet) {
    if (!tweet.entities) {
	return tweet.text;
    }

    var tweet_text = tweet.text;
    var footer = "";
    var image_regexp = /(\.jpg|\.jpeg|\.png|\.gif)$/;
    var urls_length = tweet.entities.urls ? tweet.entities.urls.length : 0;
    for (var i = 0; i < urls_length; ++i) {
	var url_dict = tweet.entities.urls[i];
	var expanded_url = url_dict.expanded_url;
	var url = expanded_url.replace("http://", "");
	if (url.length > 30) {
	    url = (url.substr(0, 20) + "..." + url.substr(-7));
	}
	var a_open = ('<a href="' + expanded_url +
		      '" rel="noreferrer" target="_blank">');
	tweet_text = tweet_text.replace(
            url_dict.url, (a_open + url + '</a>'));
	if (image_regexp.test(expanded_url)) {
	    footer += ('<div>' + a_open +
		       '<img class="tweet_image" src="' + expanded_url + '"/>' +
		       '</a></div>');
	}
    }
    var media_length = tweet.entities.media ? tweet.entities.media.length : 0;
    for (var i = 0; i < media_length; ++i) {
	var media_dict = tweet.entities.media[i];
	var media_url = media_dict.media_url;
	var url = media_url.replace("http://", "");
	if (url.length > 30) {
	    url = (url.substr(0, 20) + "..." + url.substr(-7));
	}
	tweet_text = tweet_text.replace(media_dict.url, '');
	var a_open = ('<a href="' + media_url +
		      '" rel="noreferrer" target="_blank">');
	footer += ('<div class="media">' + a_open +
		   '<img class="tweet_image" src="' + media_url + '"/>' +
		   '</a></div>');
    }
    
    return tweet_text + footer;
}

function appendTweet(tweet) {
    var template = document.getElementById("tweet_template")
    var new_node = template.cloneNode(true);
    new_node.id = "tweet_" + tweet.id_str;
    new_node.getElementsByClassName('profile_url')[0].href =
	("http://twitter.com/" + tweet.user.screen_name +
	 "/status/" + tweet.id_str);
    new_node.getElementsByClassName('profile_image')[0].src =
	tweet.user.profile_image_url;
    new_node.getElementsByClassName('text')[0].innerHTML =
	modifyTweet(tweet);
    new_node.getElementsByClassName('date')[0].innerHTML =
	new Date(Date.parse(tweet.created_at)).toString();
    new_node.getElementsByClassName('user')[0].innerHTML =
        tweet.user.screen_name;

    var star = new_node.getElementsByClassName('star')[0];
    if (tweet.x_label == "star") {
	star.innerHTML = "★";
    }
    star.addEventListener("click", function(ev) {
	if (star.innerHTML == "★") {
	    setStar(tweet.id_str, star, false);
	} else {
	    setStar(tweet.id_str, star, true);
	}
    });

    new_node.style.display = "block";
    template.parentNode.appendChild(new_node);
}

function showTweetsOld(response) {
    var id = document.getElementById("result");
    var resultHTML = "";
    var resultObj = JSON.parse(response);
    for (var i = 0; i < resultObj.statuses.length; ++i) {
	resultHTML += ("<div class='tweet'>" + resultObj.statuses[i].text +
		       "</div>");
    }
    id.innerHTML += resultHTML;
}

function showTweets(response) {
    var resultObj = JSON.parse(response);
    for (var i = 0; i < resultObj.statuses.length; ++i) {
	appendTweet(resultObj.statuses[i]);
    }
}

function clearTweets() {
    var template = document.getElementById("tweet_template")
    var new_node = template.cloneNode(true);

    // TODO(komatsu): There would be more clear way to delete nodes
    // except "tweet_template".
    var result = document.getElementById("result");
    result.innerHTML = "";
    result.appendChild(new_node);
}

function processResponse(response) {
    showTweets(response);
    var resultObj = JSON.parse(response);
    next_results = resultObj.search_metadata.next_results;
    if (typeof next_results === "undefined") {
	document.getElementById("more").disabled = true;
    }
}

function sendSearch() {
    var base_url = "/feedback/search";
    var xhr = new XMLHttpRequest();
    xhr.open("GET", base_url + next_results, true);

    xhr.send();
    xhr.addEventListener("load", function(ev) {
	if (xhr.readyState == 4 && xhr.status == 200) {
	    processResponse(xhr.responseText);
	}
    });
}

function sendNext(callback) {
    var base_url = "/feedback/next";
    var xhr = new XMLHttpRequest();
    xhr.open("GET", base_url + next_results, true);

    xhr.send();
    xhr.addEventListener("load", function(ev) {
	if (xhr.readyState == 4 && xhr.status == 200) {
	    processResponse(xhr.responseText);
	    callback();
	}
    });
}

function sendUpdate(callback) {
    var base_url = "/feedback/update";
    var xhr = new XMLHttpRequest();
    xhr.open("GET", base_url + next_results, true);

    xhr.send();
    xhr.addEventListener("load", function(ev) {
	if (xhr.readyState == 4 && xhr.status == 200) {
	    callback();
	}
    });
}

function sendDownload() {
    var base_url = "/feedback/download";
    var xhr = new XMLHttpRequest();
    xhr.open("GET", base_url + next_results, true);

    xhr.send();
    xhr.addEventListener("load", function(ev) {
	if (xhr.readyState == 4 && xhr.status == 200) {
	    processResponse(xhr.responseText);
	}
    });
}

function processAccount(response_text) {
    var response = JSON.parse(response_text);
    var account = document.getElementById("account");
    var login = document.getElementById("login");
    if (response.login) {
	account.innerHTML = response.email;
	login.href = response.logout_url;
	login.innerHTML = "Logout";
    } else {
	account.innerHTML = "Guest";
	login.href = response.login_url;
	login.innerHTML = "Login";
    }
}


function updateAccount() {
    var xhr = new XMLHttpRequest();
    xhr.open("GET", "/feedback/account", true);
    xhr.send();
    xhr.addEventListener("load", function(ev) {
	if (xhr.readyState == 4 && xhr.status == 200) {
	    processAccount(xhr.responseText);
	}
    });
}

function setOnButton(elementId, onFunction) {
    // More
    var element = document.getElementById(elementId);
    var brokerFunction = function() {
	element.style.backgroundColor = "gray";

	onFunction(function() {
	    element.style.backgroundColor = "";
	});
    };
    element.addEventListener("click", brokerFunction, false);
}

function onLoad() {
    // Account
    updateAccount();

    // Tweets
    var template = document.getElementById("tweet_template");
    template.style.display = "none";

    // More
    setOnButton("more", sendNext);

    // Update
    setOnButton("update", sendUpdate);
}

function onStared() {
    sendDownload();
}

function onQuery() {
    if (event.keyCode != 13) {
	return;
    }
    var query = document.getElementById("query").value;
    next_results = "?q=" + query + "&count=25";
    clearTweets();
    sendSearch();
}


window.addEventListener("load", onLoad, false);


