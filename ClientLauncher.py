import sys, socket
from tkinter import Tk
from ClientLocal import Client as ClientLocal
from ClientRemote import Client as ClientRemote

if __name__ == "__main__":
	try:
		serverAddr = sys.argv[1]
		serverPort = sys.argv[2]
		rtpPort = sys.argv[3]
		fileName = sys.argv[4]	
	except:
		print("[Usage: ClientLauncher.py Server_name Server_port RTP_port Video_file]\n")
		sys.exit() #NOTE: no need to continue
	
	root = Tk()
	root.config(background="white")
	
	# Create a new client
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	s.connect((serverAddr, int(serverPort)))
	myAddr = s.getsockname()[0]
	s.close()
	if serverAddr == 'localhost' or serverAddr == '127.0.0.1' or serverAddr == myAddr:
		# debug mode for local test
		app = ClientLocal(root, serverAddr, serverPort, rtpPort, fileName)
	else:
		# release mode with more robustness
		app = ClientRemote(root, serverAddr, serverPort, rtpPort, fileName)
	
	app.master.title("Now streaming " + fileName + "...")
	root.mainloop()
	