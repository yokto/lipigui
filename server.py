#!/usr/bin/env python3
import tornado.ioloop
import tornado.web
import tornado.websocket
import os
import subprocess
import asyncore
import threading
import sys
import fcntl
import select
import io
import argparse

from uuid import uuid4
from string import Template

from html.parser import HTMLParser
from xml.sax.saxutils import escape

websocketDictionary = {}

secureID = None

# this will be a prefix to use for all calls that are hidden from the
# programmer. I.e. the address of the websocket for ICGI.
# since it contains an uuid() you don't have to worry about conflicting with it
randomID = "_ICGI_"+str(uuid4())

script=Template(
"""<script type="text/javascript">
var ICGI = function () {
	var object = { position: null }
	console.log("icgi enabled");
	var url_id = "$url_id";
	object.position = document.body
	object.write = 1
	
	// create websocket url
	var loc = window.location, new_uri;
	if (loc.protocol === "https:") {
		uri = "wss:";
	} else {
		uri = "ws:";
	}
	uri += "//" + loc.host;
	uri += loc.pathname + "/$url_id";
	console.log("websocket url: " + uri)
	// create websocket url done
	
	var websocket = new WebSocket(uri);
	console.log("websocket opened");
	websocket.onmessage = function (event) {
		var elem = document.createElement("span");
		elem.type=("application/xhtml+xml");
		elem.innerHTML = event.data;
		for (var i = 0; i < elem.childNodes.length ;) {
			el = elem.childNodes[i];
			if (el.tagName == "SCRIPT" && el.className == "ICGI_EVAL") {
				eval(el.textContent);
				i++
			} else {
				object.position.appendChild(el);
			}
		}
	}

	object.send = function(str) {
		websocket.send(str);
	};
	return object;
	}();
</script>""")

movePosition = Template(
'''<script type="text/javascript" class="ICGI_EVAL">
ICGI.position = ICGI.position$relation;
</script>''')

toParent = Template('''
<script type="text/javascript" class="ICGI_EVAL">
if (ICGI.position.tagName == "$tag") {
	ICGI.position = ICGI.position.parentNode;
} else {
alert("mismatched tag");
console.log("mismatched tag");
}
</script>''')

# create a subclass and override the handler methods
class MyHTMLParser(HTMLParser):
	inScript = False
	headDone = False
	websocketClosed = False
	getDone = None
	url = None
	stringio = None
	getHandler = None
	websocketOpened = None
	websocket = None
	tagStack = None
	process = None
	def __init__(self, handler, url, getDone, process):
		HTMLParser.__init__(self)
		self.getHandler = handler
		self.url = url
		self.getDone = getDone
		self.process = process
		self.stringio = io.StringIO()
		self.websocketOpened = threading.Semaphore(0)
		self.tagStack = []
	def write(self,string):
		#print(string)
		if (self.headDone):
			self.stringio.write(string)
		else:
			self.getHandler.write(string)
	def write_message(self, string):
		if(not self.websocketClosed):
			self.websocket.write_message(string)
	def writeTag(self,tag,args):
		self.write("<" + tag)
		for arg in args:
			self.write(" " + arg[0] + "=\"" + escape(arg[1]+"\""))
		self.write(">")
	def handle_starttag(self, tag, attrs):
		if self.headDone and tag == "script":
			self.flush()
			self.inScript = True
		self.tagStack.append(tag)
		self.writeTag(tag,attrs)
		if not self.headDone:
			if (tag == "body"):
				id_url = str(uuid4())
				websocketDictionary[id_url] = self
				self.write(script.substitute(url_id=id_url+randomID))
				self.handle_endtag("body")
				self.handle_endtag("html")
				self.getHandler.finish()
				self.getDone.release()
				self.headDone = True
				self.websocketOpened.acquire()
	def handle_endtag(self, tag):
		if (len(self.tagStack) == 0):
			self.flush()
			print("\n\n" + toParent.substitute(tag = tag.upper()))
			self.write_message(toParent.substitute(tag = tag.upper()))
			self.flush()
		elif (self.tagStack.pop() != tag):
			self.flush()
			self.write_message('''<script type="application/javascript" class="ICGI_EVAL">alert('mismatched tabs');</script>''')
			self.flush()
			# TODO: crash
		else:
			self.write("</" + tag + ">")

		if tag == "script" and self.headDone:
			self.inScript=False
			self.flush()
	def handle_data(self, data):
		self.write(escape(data))
	def handle_decl(self,data):
		self.write("<!" + data + ">")
	def handle_pi(self, data):
		self.write("<?" + data + ">")
	def flush(self):
		if self.inScript == True:
			print("cant flush in script");
			return
		unclosedTags = len(self.tagStack)
		for tag in self.tagStack:
			self.handle_endtag(tag)
		# print(self.stringio.getvalue()+"end")
		self.write_message(self.stringio.getvalue())
		if unclosedTags != 0:
			# print(movePosition.substitute(relation = ".lastChild"*unclosedTags))
			self.write_message(movePosition.substitute(relation = ".lastChild"*unclosedTags))
		self.stringio.close()
		self.stringio = io.StringIO()
		

def parseXML(process,parser):
	while True:
		str = os.read(process.stdout.fileno(), 2048)
		if str == None or str == b"":
			break
		parser.feed(str.decode())
		if parser.headDone:
			parser.flush()

class ICGIHandler(tornado.web.RequestHandler):
	def get(self, url, ignore):
		environment = os.environ.copy()
		for key in self.request.arguments:
			environment["ICGI_ARG_"+key]=self.request.arguments[key][0].decode()
		environment["ICGI_URI"] = self.request.uri
		# TODO: test executable
		process = subprocess.Popen(["./"+url], stdout=subprocess.PIPE, stdin=subprocess.PIPE,env=environment)
		mime = process.stdout.readline()
		if mime != b"application/icgi\n":
			sys.stderr.write('anything other than application/icgi is not implemented yet')
			self.set_status(400)
			self.finish("<html><body>anything other than application/icgi is not implemented yet</body></body>")
			return

		getDone = threading.Semaphore(0)
		parser=MyHTMLParser(self, url, getDone,process)
		thread = threading.Thread(target=parseXML, args = (process,parser))
		thread.daemon = True
		thread.start()
		parser.thread = thread
		getDone.acquire()

class WSHandler(tornado.websocket.WebSocketHandler):
	parser = None
	def open(self,url):
		print("websocket connected: " + url.decode())
		self.parser = websocketDictionary[os.path.basename(url.decode())]
		self.parser.websocket = self
		self.parser.websocketOpened.release()
		return
	def on_message(self, msg):
		self.parser.process.stdin.write(msg.encode())
		self.parser.process.stdin.flush()
		#sys.stdout.write(msg)
		#sys.stdout.flush()
	def on_close(self):
		print("closing socket")
		self.parser.websocketClosed = True
		self.parser.process.stdin.close()
		print("waiting for termination")
		self.parser.process.wait()
		print("terminated")

application = tornado.web.Application([
	(r"/(.*)"+randomID, WSHandler),
	(r"/(.*\.icgi(\.[^/.]*)*)", ICGIHandler), # concession to operatingsystems that don't support shebang
	(r"/(.*)", tornado.web.StaticFileHandler, {"path": os.getcwd()}),
	])

if __name__ == "__main__":
	parser = argparse.ArgumentParser(description='Simple ICGI Server')
	parser.add_argument('-d', "--directory", dest='directory', action='store', default=os.getcwd(),
		help='this is the directory in which the server will be executed and from which it will serve files')
	parser.add_argument('-s', "--secure", dest='secure', action='store_true',
		help='this opens the default browser in such a way that only that session can access any url of the server')
	args = parser.parse_args()
	
	# working dir
	print("starting server in " + os.path.abspath(args.directory))
	os.chdir(os.path.abspath(args.directory))
	
	# secure ID
	if args.secure:
		secureID = str(uuid4())
		print("secure token is: " + secureID)

	application.listen(8888)
	tornado.ioloop.IOLoop.instance().start()