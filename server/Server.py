import sys, socket

from ServerWorkerLocal import ServerWorker as ServerWorkerLocal
from ServerWorkerRemote import ServerWorker as ServerWorkerRemote

class Server:	
	
	def main(self):
		try:
			SERVER_PORT = int(sys.argv[1])
		except:
			print("[Usage: Server.py Server_port]\n")
			sys.exit() #NOTE: no need to continue
		# a socket using IPv4 and TCP
		rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		# bind this socket to all interfaces
		rtspSocket.bind(('', SERVER_PORT))
		rtspSocket.listen(5)

		# Receive client info (address,port) through RTSP/TCP session
		while True:
			clientInfo = {}
			clientInfo['rtspSocket'] = rtspSocket.accept()

			s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			s.connect(clientInfo['rtspSocket'][1])
			myAddr = s.getsockname()[0]
			s.close()

			if clientInfo['rtspSocket'][1][0] == 'localhost' or clientInfo['rtspSocket'][1][0] == '127.0.0.1' or clientInfo['rtspSocket'][1][0] == myAddr:
				# debug mode for local test
				ServerWorkerLocal(clientInfo).run()
			else:
				# release mode with more robustness - like Twitch
				ServerWorkerRemote(clientInfo).run()

if __name__ == "__main__":
	(Server()).main()


