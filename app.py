#!/usr/bin/env python

import os.path
import re
import tornado.auth
import tornado.database
import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import unicodedata
import tornado.websocket
import json
import hashlib, uuid

from tornado.options import define, options

define("port", default=8080, help="run on the given port", type=int)
define("mysql_host", default="127.0.0.1:3306", help="blog database host")
define("mysql_database", default="qnadb", help="blog database name")
define("mysql_user", default="root", help="blog database user")
define("mysql_password", default="3rdr3d", help="blog database password")

db = tornado.database.Connection(
            host=options.mysql_host, database=options.mysql_database,
            user=options.mysql_user, password=options.mysql_password)

class Application(tornado.web.Application):
	def __init__(self):
		handlers = [
			(r"/", RootHandler),
            (r"/chat/(\w+)", ChatHandler)
			# Add your routes here
		]
		settings = dict(
			app_name=u"Sena Chat",
			template_path=os.path.join(os.path.dirname(__file__), "templates"),
			static_path=os.path.join(os.path.dirname(__file__), "static"),
			xsrf_cookies=True,
		)
		tornado.web.Application.__init__(self, handlers, debug=True,**settings)
		# Have one global connection to the blog DB across all handlers
		

class ChatSession():

    def __init__(self, username1, username2):
        self.username1=username1
        self.username2=username2
        self.messages=[]

    def add_message(self, payload):
        self.messages.append(payload)

    def get_messages(self):
        import json
        json.dumps(self.messages)


class ChatHandler(tornado.websocket.WebSocketHandler):
    waiters=set()
    users=dict()
    cache=[]
    cache_size=200
    sessions=dict()
    user_sessions=dict()

    def allow_draft76(self):
        return True

    def open(self,username):
        self.username=username

        for con in ChatHandler.waiters:
            con.write_message(json.dumps({"type":"presence","from":self.username, "status":"1","fullname":self.username}))
            self.write_message(json.dumps({"type":"presence","from":con.username, "status":"1","fullname":con.username}))
        ChatHandler.waiters.add(self)
        ChatHandler.users[username]=self
        ChatHandler.user_sessions[username]=[]

        self.write_message(json.dumps({'message':'welcome','from':'admin'}))
        #send presence

        print "chat connection received from {0}".format(username)

    def on_close(self):
        print "chat connection closing"
        try:
            ChatHandler.waiters.remove(self)
            del(ChatHandler.users[self.username])
            del(ChatHandler.user_sessions[self.username])
        except Exception, e:
             print "error closing connection for client: {0}, error: {1}".format(self.username,e)
        
        for con in ChatHandler.waiters:
            con.write_message(json.dumps({"type":"presence","from":self.username, "status":"0","fullname":self.username}))

    def error_msg(self, error_code):
        if not error_code is None:
            
            json_string=json.dumps({"type":"error","code":error_code})
            print "sending error to client: {0}, error: {1}".format(self.username,json_string)
            self.write_message("{0}".format(json_string))
        else:
            print "Eror code not found"

    @classmethod
    def get_user_sessions(cls, username):
        if not username is None:
            if username in cls.user_sessions:
                sessions=cls.user_sessions[username]
                return sessions
        return []


    @classmethod
    def start_session(cls,from_user, to_user, payload):
        try:
            if from_user in cls.users and to_user in cls.users:
                print "starting chat session for user: {0} and user {1}".format(from_user, to_user)
                session_key="{0}-{1}".format(from_user.lower().strip(),to_user.lower().strip())
                if session_key in cls.sessions or session_key[::-1] in cls.sessions:
                    print "session already exists, sending notification to user"
                    if not session_key in cls.sessions:
                        session_key=session_key[::-1]

                    join_msg={"type":"chatsession","sessionkey":session_key, "from":to_user,"to":from_user,'history':cls.sessions[session_key].messages}
                    cls.users[from_user].write_message(json.dumps(join_msg))
                    join_msg['from']=from_user
                    join_msg["to"]=to_user
                    cls.users[to_user].write_message(json.dumps(join_msg))

                    history=cls.sessions[sessionkey].messages
                    if not history is None and len(history)>0:
                        for i in history:
                            #cls.users[to_user].write_message(json.dumps(history[i]))
                            #cls.users[to_user].write_message(json.dumps(history[i]))
                            pass

                    return

                session=ChatSession(from_user,to_user)
                cls.sessions[session_key]=session


                join_msg={"type":"chatsession","sessionkey":session_key, "from":to_user,"to":from_user,'history':cls.sessions[session_key].messages}
                cls.users[from_user].write_message(json.dumps(join_msg))
                join_msg['from']=from_user
                join_msg['type']="chatinvite"
                join_msg["to"]=to_user
                cls.users[to_user].write_message(json.dumps(join_msg))
            else:


                json_data={"to":from_user, "from":"admin", "type":"offline", "from":to_user }
                cls.users[from_user].write_message(json.dumps(json_data))

        except Exception, e:
            print "error while starting chat session {0}".format(e);

    def on_message(self, message):
        print "received message: {0} from {1}".format(message,self.username)
        try:
            json_data=json.loads(message)
            if "type" in json_data:

                message_type=json_data['type']
                if message_type=='chatmessage':
                    from_user = json_data['from']
                    to_user = json_data['to']
                    sessionkey=json_data['sessionkey']
                    message=json_data["message"]

                    if sessionkey in ChatHandler.sessions:
                        ChatHandler.sessions[sessionkey].messages.append(json_data)

                    print "chat message received from {0} to {1}".format(from_user,to_user)
                    #ChatHandler.send_message_to_user(to_user, message)
                    try:
                        if to_user in ChatHandler.users :
                            ChatHandler.users[to_user].write_message(json.dumps({"from":from_user,"to":to_user,"sessionkey":sessionkey, "message":message, "type":"chatmessage"}))


                    except Exception, e:
                        print "error while sending message"

                elif message_type == "startsession":
                    if "to" in json_data:
                        to_user = json_data['to']
                        print "starting chat session for user: {0} and {1}".format(self.username,json_data['to'])
                        ChatHandler.start_session(self.username,to_user,json_data)

                elif message_type=='presence':
                    print "presence from {0} status {1}".format(from_user,message['status'])
                    ChatHandler.send_presence()
        except Exception, e:
            print "Error occurred during message received {0}".format(e)
            self.error_msg("100")
        

    @classmethod
    def send_presence(cls, from_user, payload):
        print "sending presence from user {0} to his/her friends ".format(from_user)
        #get friends
        friends=db.query("select u.username, c.userid from chatusercontacts c, chatuser where c.userid=u.id and c.userid=%s",from_user)
        if not friends is None and len(friends)>0:
            for friend in friends:
                try:
                    con=cls.users[friend['username']]
                    con.write_message("{0}".format(payload))
                except Exception, e:
                    pass


    @classmethod
    def send_message_to_user(cls, username, payload):
        print "sending chat message to client {0}".format(username)
        if not username is None and not payload is None :
            try:
                cls.users[username].write_message("{0}".format(json.dumps(payload)))
                return True
            except Exception, e:
                print "error while sending mesage to user {0}, error: {1}".format(username,e)

        return False


    def send_message_to_users(cls, usernames_array, payload):
        print "sending chat message to clients {0}".format(",".join(usernames_array))
        if not usernames_array is None and not payload is None:
            for con in cls.waiters:
                if con.username in usernames_array:
                    try:
                        con.write_message("{0}".format(json.dumps(payload)))
                    except Exception, e:
                        pass
            return True

        return False

    def create_chat_session(cls, username1, username2):
        pass


class BaseHandler(tornado.web.RequestHandler):
	@property
	def db(self):
		return self.application.db
	
class RootHandler(BaseHandler):
	def get(self):
		self.render("root.html")

def main():
	tornado.options.parse_command_line()
	http_server = tornado.httpserver.HTTPServer(Application())
	http_server.listen(options.port)
	tornado.ioloop.IOLoop.instance().start()

if __name__ == "__main__":
	main()
