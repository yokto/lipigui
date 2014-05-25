# lipigui

Language Independent, Platform Independent GUI took kit

## Motivation

The idea of using the browsers capabilities to add a platform independent gui to you program is not new. However, it hasn't had a lot of success so far the only program I know that uses it is git-annex. I think the reason for this is that web development is complicated, and so are the frameworks you might use. Additionally, most frameworks are created with thoughts like restful and webstore in mind. Those are good concepts, but if you are doing something interactive it's hard to think about all the things you would have to update in one tab if something changes in an other or on the server.

## Solution

Surely you have been wondering how a gui tool kit/web framework could ever be programming language independent. We did have CGI (just forwarding the standard output to the browser) that was language independent, but it wasn't very interactive. So what we will try to do is make CGI interactive. When a client connects to the webserver with a specific url or a specific prefix the server will execute our program *myapp*.

The webserver will read from *myapp*'s standard output until it blocks if the opening tag of <body> has not been reached, it waits. other wise it will close all unclosed tags and send the it off to the browser. It will also insert a little script in the meta section that will open a websocket to connect to the webserver and that will place assign to *position* variable with the innermost unclosed element.

As soon as more, output of *myapp* is available it will be sent through the websocket and appended to the website. When encountering a closing tag that was not opened in that part, will tell the browser to set *position* to the parent of the current element if the tag is correct and call an error otherwise. If a script tag is reached it will be sent to the browser and executed. Since the server doesn't keep track of opening/closing tags, you can also set *position* to wherever you want and start adding data there. Of course to delete something you have to send a script tag or use javascript some other way.

As stdin of *myapp* you will receive anything that is written to the browser writes to the websocket.

## Implementation

There is some very basic python code ./server.py that just runs a icgi server in the current directory on port 8888. There is also a very basic chat program written in Bash that you can test if the server runs.
(localhost:8888/chat.icgi)

You will need to install

	apt-get install python3-tornado

## Comments

I haven't written any code yet but comments suggestions are welcome yokto.reports*at*gmail.com.