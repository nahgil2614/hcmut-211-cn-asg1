from tkinter import *
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os

from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

#NOTE: rmb to close rtsp socket
#NOTE: how to handle the end of the video
#NOTE: implement a buffer (queue)
#NOTE: what if the packets are lost? (currently assuming no losses)

class Client:
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT
    
    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3
    DESCRIBE = 4

    TORNDOWN = False
    
    # Initiation..
    def __init__(self, master, serveraddr, serverport, rtpport, filename):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)
        self.createWidgets()
        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.fileName = filename
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1 #NOTE: what is it?
        self.teardownAcked = 0 #NOTE: what is it?
        self.connectToServer()
        self.frameNbr = 0
        self.totalFrameNbr = 0
        # width and height of the video
        self.width = 0
        self.height = 0
        # SETUP is mandatory in an RTSP interaction
        self.setupMovie()
        
    # THIS GUI IS JUST FOR REFERENCE ONLY, STUDENTS HAVE TO CREATE THEIR OWN GUI     
    def createWidgets(self):
        """Build GUI."""        
        # Create a label to display the movie
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 
        
        # self.text = Text(self.master, height=10)
        # self.text.grid(row=0, column=0, sticky='ns')
        # # Create the scrollbar
        # self.scrollbar = Scrollbar(self.master, orient=HORIZONTAL)
        # self.scrollbar["command"] = self.text.xview
        # self.scrollbar.grid(row=1, column=0, columnspan=3, padx=2, pady=2, sticky='ew')

        # self.text['xscrollcommand'] = self.scrollbar.set

        # Create a label to display the total and remaining time
        self.time = Label(self.master, width=20, padx=3, pady=3)
        self.time["text"] = "00:00 / 00:00"
        self.time.grid(row=1, column=3, padx=2, pady=2)

        # Create Describe button        
        self.describe = Button(self.master, width=20, padx=3, pady=3)
        self.describe["text"] = "Describe"
        self.describe["command"] = self.describeMovie
        self.describe.grid(row=2, column=0, padx=2, pady=2)

        # Create Play button        
        self.start = Button(self.master, width=20, padx=3, pady=3)
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start.grid(row=2, column=1, padx=2, pady=2)
        
        # Create Pause button            
        self.pause = Button(self.master, width=20, padx=3, pady=3)
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause.grid(row=2, column=2, padx=2, pady=2)
        
        # Create Teardown button
        self.teardown = Button(self.master, width=20, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["command"] =  self.exitClient
        self.teardown.grid(row=2, column=3, padx=2, pady=2)
    
    def setupMovie(self):
        """Setup function handler."""
        self.sendRtspRequest(self.SETUP)
        data = self.recvRtspReply()
        if self.parseRtspReply(data):
            self.state = self.READY
        self.label.update()
        ratio = min(self.label.winfo_width()/self.width, self.label.winfo_height()/self.height)
        self.width = int(self.width * ratio)
        self.height = int(self.height * ratio)

    def describeMovie(self):
        """Describe function handler."""
        if not self.TORNDOWN:
            self.sendRtspRequest(self.DESCRIBE)
            data = self.recvRtspReply()
            self.parseRtspReply(data)
    
    def playMovie(self):
        """Play button handler."""
        if not self.TORNDOWN and self.state == self.READY:
            self.sendRtspRequest(self.PLAY)
            #NOTE: open the port here to decrease the lost datagram numbers
            #if we open after parsing, we can open after when the server have sent the first frame
            self.openRtpPort()
            data = self.recvRtspReply()
            if self.parseRtspReply(data):
                self.state = self.PLAYING
                # Create a new thread and start receiving RTP packets
                self.worker = threading.Thread(target=self.listenRtp) 
                self.worker.start()

    def pauseMovie(self):
        """Pause button handler."""
        if not self.TORNDOWN and self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)
            data = self.recvRtspReply()
            if self.parseRtspReply(data):
                self.state = self.READY

    def exitClient(self):
        """Teardown button handler."""
        # This command terminates the session and closes the connection
        if not self.TORNDOWN and (self.state == self.READY or self.state == self.PLAYING):
            self.sendRtspRequest(self.TEARDOWN)
            data = self.recvRtspReply()
            if self.parseRtspReply(data):
                self.rtspSocket.close()
                # the RTP socket (if there is) would be closed due to timeout
                # we would send any images remaining in the buffer
                self.TORNDOWN = True

    def listenRtp(self):        
        """Listen for RTP packets."""
        while True:
            try:
                data, _ = self.rtpSocket.recvfrom(1 << 16)
                assert(data)
            except: # timeout
                self.rtpSocket.close()
                os.remove(imageFile)
                break
            # packet received sucessfully
            self.frameNbr += 1
            packet = RtpPacket()
            packet.decode(data)
            assert(packet.seqNum() == self.frameNbr) #NOTE: try-except right here to count number of errors ...
            frame = packet.getPayload()
            imageFile = self.writeFrame(frame)
            self.updateMovie(imageFile)
                    
    def writeFrame(self, data):
        """Write the received frame to a temp image file. Return the image file."""
        imageFile = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        file = open(imageFile, 'wb')
        file.write(data)
        file.close()
        return imageFile
    
    def updateMovie(self, imageFile):
        """Update the image file as video frame in the GUI."""
        image = Image.open(imageFile)
        image = image.resize((self.width, self.height), Image.ANTIALIAS)
        photo = ImageTk.PhotoImage(image)
        self.label = Label(self.master, height=19, image=photo)
        self.label.image = photo
        self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 

        # Update the total and remaining time
        self.time = Label(self.master, width=20, padx=3, pady=3)
        self.time["text"] = self.sec2time(int((self.totalFrameNbr - self.frameNbr) * 0.05)) + ' / ' + self.sec2time(int(self.totalFrameNbr * 0.05))
        self.time.grid(row=1, column=3, padx=2, pady=2)
        
    def connectToServer(self):
        """Connect to the Server. Start a new RTSP/TCP session."""
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rtspSocket.connect((self.serverAddr, self.serverPort))
    
    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server.""" 
        self.rtspSeq += 1
        if requestCode == self.SETUP:
            msg = 'SETUP ' + self.fileName + ' RTSP/1.0\n' +\
                  'CSeq: ' + str(self.rtspSeq) + '\n' +\
                  'Transport: RTP/UDP; client_port= ' + str(self.rtpPort)
        elif requestCode == self.PLAY:
            msg = 'PLAY ' + self.fileName + ' RTSP/1.0\n' +\
                  'CSeq: ' + str(self.rtspSeq) + '\n' +\
                  'Session: ' + str(self.sessionId)
        elif requestCode == self.PAUSE:
            msg = 'PAUSE ' + self.fileName + ' RTSP/1.0\n' +\
                  'CSeq: ' + str(self.rtspSeq) + '\n' +\
                  'Session: ' + str(self.sessionId)
        elif requestCode == self.TEARDOWN:
            msg = 'TEARDOWN ' + self.fileName + ' RTSP/1.0\n' +\
                  'CSeq: ' + str(self.rtspSeq) + '\n' +\
                  'Session: ' + str(self.sessionId)
        elif requestCode == self.DESCRIBE:
            msg = 'DESCRIBE RTSP/1.0\n' +\
                  'CSeq: ' + str(self.rtspSeq) + '\n' +\
                  'Session: ' + str(self.sessionId)

        self.rtspSocket.send(msg.encode())
    
    def recvRtspReply(self):
        """Receive RTSP reply from the server."""
        data = self.rtspSocket.recv(2048).decode()
        print("Response received: " + data)
        return data
    
    def parseRtspReply(self, data):
        """Parse the RTSP reply from the server."""
        reply = data.split('\n')
        reply = [line.split(' ') for line in reply]
        if not self.sessionId:
            self.sessionId = int(reply[2][1])
        #NOTE: close the connection if there are errors
        try:
            assert(reply[0][1] == '200')
            assert(int(reply[1][1]) == self.rtspSeq)
            assert(int(reply[2][1]) == self.sessionId)
        except:
            self.rtspSocket.close()
            return False

        if len(reply) == 4:
            if reply[3][0] == 'Description:':
                msg = 'Stream types: ' + reply[3][1] + '\n'\
                      'Encoding: ' + reply[3][2]
                tkinter.messagebox.showinfo('Session description', msg)
            elif reply[3][0] == 'Info:':
                self.totalFrameNbr = int(reply[3][1])
                self.width = int(reply[3][2])
                self.height = int(reply[3][3])

        return True
    
    def openRtpPort(self):
        """Open RTP socket binded to a specified port."""
        # Create a new datagram socket to receive RTP packets from the server
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rtpSocket.bind(('', self.rtpPort))
        
        # Set the timeout value of the socket to 0.5sec
        self.rtpSocket.settimeout(0.5)        

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        if tkinter.messagebox.askokcancel("Quit", "Do you want to quit?"):
            self.rtspSocket.close()
            self.master.destroy()

    def sec2time(self, sec): # assuming the length is always < 1 hour
        return str(sec//60).rjust(2,'0') + ':' + str(sec%60).rjust(2,'0')
