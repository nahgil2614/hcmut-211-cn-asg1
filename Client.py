from tkinter import *
import tkinter.font
import tkinter.messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os, platform

from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

#NOTE: rmb to close rtsp socket (the exit logic) => DONE!
#NOTE: implement a buffer (queue)?
#NOTE: implement the preview when scrolling
#NOTE: what if the packets are lost? (currently assuming no losses)
#LESSON LEARNT: we have to make sure that the state on Client and ServerWorker are the same at everytime

class Client:
    INIT = 0
    READY = 1
    PLAYING = 2
    SWITCHING = 3
    state = INIT
    
    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3
    DESCRIBE = 4
    SWITCH = 5

    TORNDOWN = False
    
    # Initiation..
    def __init__(self, master, serveraddr, serverport, rtpport, filename):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)

        if platform.system() == 'Windows':
            self.describeText = 'Describe ⓘ'
            self.playText = 'Play ▶'
            self.pauseText = 'Pause ⏸'
            self.switchText = 'Switch'
            self.teardownText = 'Teardown ■'
        elif platform.system() == 'Linux': # linux host having font issue
            self.describeText = 'Describe'
            self.playText = 'Play'
            self.pauseText = 'Pause'
            self.switchText = 'Switch'
            self.teardownText = 'Teardown'

        self.frameNbr = IntVar()
        self.totalFrameNbr = 0
        self.elapsedTime = StringVar(value='00:00')
        self.remainingTime = StringVar(value='00:00')
        self.playPauseText = StringVar(value=self.playText)
        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.fileName = filename
        self.createWidgets()
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1 #NOTE: what is it?
        self.teardownAcked = 0 #NOTE: what is it?
        self.connectToServer()
        # width and height of the video
        self.width = 0
        self.height = 0
        # SETUP is mandatory in an RTSP interaction
        self.setupMovie()
        
    # THIS GUI IS JUST FOR REFERENCE ONLY, STUDENTS HAVE TO CREATE THEIR OWN GUI     
    def createWidgets(self):
        """Build GUI."""
        # Create a label to display the movie
        # dummy photo
        photo = ImageTk.PhotoImage(data=bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010100000000376ef9240000000a49444154789c636000000002000148afa4710000000049454e44ae426082'))
        self.label = Label(self.master, height=275, image=photo, bg="black")
        self.label.image = photo
        self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5)

        # Create a label to display the elapsed time
        self.eTimeLabel = Label(self.master, anchor=W, width=12, padx=3, pady=3, bg="white")
        self.eTimeLabel["textvariable"] = self.elapsedTime
        self.eTimeLabel.grid(row=1, column=0, padx=2, pady=2)

        # Create a label to display the remaining time
        self.eTimeLabel = Label(self.master, anchor=E, width=12, padx=3, pady=3, bg="white")
        self.eTimeLabel["textvariable"] = self.remainingTime
        self.eTimeLabel.grid(row=1, column=3, padx=2, pady=2)

        # Create Describe button
        self.describe = Button(self.master, width=10, padx=10, pady=3)
        self.describe["text"] = self.describeText
        self.describe["command"] = self.describeMovie
        self.describe.grid(row=2, column=0, padx=10, pady=2)

        # Create Play/Pause button
        self.playPause = Button(self.master, width=20, padx=10, pady=3)
        self.playPause["textvariable"] = self.playPauseText
        self.playPause["command"] = self.playPauseMovie
        self.playPause.grid(row=2, column=1, padx=10, pady=2)
        
        # Create Switch button
        self.switch = Button(self.master, width=20, padx=10, pady=3)
        self.switch["text"] = self.switchText
        self.switch["command"] = self.switchMovie
        self.switch.grid(row=2, column=2, padx=10, pady=2)
        
        # Create Teardown button
        self.teardown = Button(self.master, width=10, padx=10, pady=3)
        self.teardown["text"] = self.teardownText
        self.teardown["command"] =  self.exitClient
        self.teardown.grid(row=2, column=3, padx=10, pady=2)
    
    def setupMovie(self):
        """Setup function handler."""
        if self.state == self.INIT or self.state == self.SWITCHING:
            self.sendRtspRequest(self.SETUP)
            data = self.recvRtspReply()
            if not self.parseRtspReply(data):
                return
            self.label.update()
            ratio = min(self.label.winfo_width()/self.width, self.label.winfo_height()/self.height)
            self.width = int(self.width * ratio)
            self.height = int(self.height * ratio)

            if self.state == self.INIT:
                # Create the scrollbar
                def press(event):
                    if not self.TORNDOWN and self.scrollbar["state"] != DISABLED:
                        self.scrollbar["variable"] = 0
                        self.scrollbar.set(self.frameNbr.get())

                # return the control back to self.frameNbr
                def release(event):
                    if not self.TORNDOWN and self.scrollbar["state"] != DISABLED:
                        self.frameNbr.set(self.scrollbar.get())
                        self.scrollbar["variable"] = self.frameNbr
                        if self.state == self.PLAYING:
                            self.sendRtspRequest(self.PAUSE)
                            data = self.recvRtspReply()
                            self.parseRtspReply(data)
                            # buttons' states
                            if self.playPause["state"] == DISABLED:
                                self.playPause["state"] = NORMAL
                        self.sendRtspRequest(self.PLAY)
                        data = self.recvRtspReply()
                        self.parseRtspReply(data)
                        if self.state == self.READY:
                            self.sendRtspRequest(self.PAUSE)
                            data = self.recvRtspReply()
                            self.parseRtspReply(data)
                            # buttons' states
                            if self.playPause["state"] == DISABLED:
                                self.playPause["state"] = NORMAL

                def spress(event):
                    if not self.TORNDOWN:
                        self.openRtpPort(None)
                        self.interrupt.clear()
                        self.worker = threading.Thread(target=self.listenRtp)
                        self.worker.start()

                        self.sendRtspRequest(self.PAUSE, timeout='0')
                        data = self.recvRtspReply()
                        self.parseRtspReply(data)

                def scroll(event):
                    if not self.TORNDOWN:
                        self.sendRtspRequest(self.PLAY, timeout='0')
                        data = self.recvRtspReply()
                        self.parseRtspReply(data)
                
                def srelease(event):
                    if not self.TORNDOWN:
                        if self.state == self.READY:
                            self.sendRtspRequest(self.PAUSE, timeout='1')
                        elif self.state == self.PLAYING: # the become READY on the server
                            self.sendRtspRequest(self.PAUSE, timeout='2')
                        data = self.recvRtspReply()
                        self.parseRtspReply(data)
                        self.rtpSocket.shutdown(socket.SHUT_RDWR)
                        self.rtpSocket.close()
                        # buttons' states
                        if self.playPause["state"] == DISABLED:
                            self.playPause["state"] = NORMAL
                            
                        if self.state == self.PLAYING:
                            self.state = self.READY
                            self.playMovie()

                self.scrollbar = Scale(self.master, from_=0, to=self.totalFrameNbr-1, length=self.label.winfo_width()*0.8, orient=HORIZONTAL, showvalue=0, sliderlength=15, activebackground="red", bg="gray", troughcolor="black")
                self.scrollbar["variable"] = self.frameNbr
                # self.scrollbar.bind("<Button-1>", press)
                # self.scrollbar.bind("<ButtonRelease-1>", release)
                self.scrollbar.bind("<Button-1>", spress)
                self.scrollbar.bind("<ButtonRelease-1>", srelease)
                self.scrollbar["command"] = scroll
                self.scrollbar.grid(row=1, column=0, columnspan=4, padx=2, pady=2)
            elif self.state == self.SWITCHING:
                self.scrollbar["variable"] = self.frameNbr
                self.scrollbar.set(0)
                self.scrollbar["to"] = self.totalFrameNbr-1
                self.scrollbar["length"] = self.label.winfo_width()*0.8

            self.state = self.READY
            self.interrupt = threading.Event()

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
                # buttons' style
                self.playPauseText.set(self.pauseText)
                # Create a new thread and start receiving RTP packets
                self.interrupt.clear()
                self.worker = threading.Thread(target=self.listenRtp)
                self.worker.start()

    def pauseMovie(self):
        """Pause button handler."""
        if not self.TORNDOWN and self.state == self.PLAYING:
            self.interrupt.set()
            self.sendRtspRequest(self.PAUSE)
            data = self.recvRtspReply()
            if self.parseRtspReply(data):
                self.state = self.READY
                # buttons' style
                self.playPauseText.set(self.playText)

    def playPauseMovie(self):
        """Play/Pause button handler."""
        if self.playPauseText.get().startswith("Play"):
            self.playMovie()
        elif self.playPauseText.get().startswith("Pause"):
            self.pauseMovie()

    def switchMovie(self):
        if not self.TORNDOWN:
            self.interrupt.set()
            self.sendRtspRequest(self.SWITCH)
            data = self.recvRtspReply()
            if self.parseRtspReply(data):
                # in case the user just choose the current movie
                oldState = self.state
                oldFrameNbr = self.frameNbr.get()

                self.state = self.SWITCHING
                self.switch["state"] = DISABLED
                self.playPause["state"] = DISABLED
                self.scrollbar["state"] = DISABLED
                self.frameNbr.set(0)
                self.playPauseText.set(self.playText)

                def finish():
                    if chosen.get() == -1:
                        tkinter.messagebox.showerror('Error', 'Please choose a movie!')
                        chooseMovie.lift()
                    else:
                        chooseMovie.destroy()

                chooseMovie = Toplevel(self.master)
                chooseMovie.protocol("WM_DELETE_WINDOW", finish)
                label = Label(chooseMovie, text="Choose a movie:", anchor=W, width=15)
                label.grid(row=0, column=0, padx=2, pady=2)
                chosen = IntVar(value=-1)
                for i in range(len(self.availableMovies)):
                    R = Radiobutton(chooseMovie, text=self.availableMovies[i].split('.')[0], variable=chosen, value=i, anchor=W, width=15)
                    R.grid(row=i+1, column=0, padx=2, pady=2)
                # Create Done button
                done = Button(chooseMovie, anchor=CENTER, padx=3, pady=3)
                done["text"] = "Done"
                done["command"] = finish
                done.grid(row=i+2, column=0, padx=2, pady=2)

                self.master.wait_window(chooseMovie)
                self.switch["state"] = NORMAL
                self.playPause["state"] = NORMAL
                self.scrollbar["state"] = NORMAL
                if self.fileName == self.availableMovies[chosen.get()]:
                    tkinter.messagebox.showwarning('Same movie', 'You have chosen the same movie again!')
                    self.frameNbr.set(oldFrameNbr)
                    if oldState == self.PLAYING:
                        self.state = self.READY
                        self.playMovie()
                    elif oldState == self.READY:
                        self.state = self.READY
                        self.playMovie()
                        self.pauseMovie()
                else:
                    self.fileName = self.availableMovies[chosen.get()]
                    self.master.title("Now streaming " + self.fileName + "...")
                    # SETUP is mandatory in an RTSP interaction
                    self.setupMovie()

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
                self.master.destroy()

    def listenRtp(self):
        """Listen for RTP packets."""
        while True:
            #self.interrupt.wait(0.01)

            if self.interrupt.isSet():
                break

            exc = False
            try:
                data, _ = self.rtpSocket.recvfrom(1 << 16)
                assert(data)
            except: # timeout
                self.rtpSocket.close()
                exc = True

            if exc:
                try:
                    os.remove(self.imageFile)
                except:
                    pass
                break

            # packet received sucessfully
            packet = RtpPacket()
            packet.decode(data)
            self.frameNbr.set(packet.seqNum())
            #assert(packet.seqNum() == self.frameNbr.get()) #NOTE: try-except right here to count number of errors ...
            frame = packet.getPayload()
            self.writeFrame(frame)
            self.updateMovie()

    def writeFrame(self, data):
        """Write the received frame to a temp image file. Return the image file."""
        file = open(self.imageFile, 'wb')
        file.write(data)
        file.close()

    def updateMovie(self):
        if self.frameNbr.get() == self.totalFrameNbr-1:
            self.pauseMovie()
            # buttons' states
            self.playPause["state"] = DISABLED
            return
        """Update the image file as video frame in the GUI."""
        image = Image.open(self.imageFile)
        image = image.resize((self.width, self.height), Image.ANTIALIAS)
        photo = ImageTk.PhotoImage(image)
        self.label.configure(image=photo, height=275)
        self.label.image = photo

        # Update the times
        self.elapsedTime.set(self.sec2time(int(self.frameNbr.get() * 0.05)))
        self.remainingTime.set(self.sec2time(int((self.totalFrameNbr - self.frameNbr.get()) * 0.05)))

    def connectToServer(self):
        """Connect to the Server. Start a new RTSP/TCP session."""
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rtspSocket.connect((self.serverAddr, self.serverPort))

    def sendRtspRequest(self, requestCode, timeout=''):
        """Send RTSP request to the server.""" 
        self.rtspSeq += 1
        if requestCode == self.SETUP:
            msg = 'SETUP ' + self.fileName + ' RTSP/1.0\n' +\
                  'CSeq: ' + str(self.rtspSeq) + '\n' +\
                  'Transport: RTP/UDP; client_port= ' + str(self.rtpPort)
        elif requestCode == self.PLAY:
            msg = 'PLAY ' + self.fileName + ' RTSP/1.0\n' +\
                  'CSeq: ' + str(self.rtspSeq) + '\n' +\
                  'Session: ' + str(self.sessionId) + '\n' +\
                  'Frame: ' + str(self.frameNbr.get())
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
        elif requestCode == self.SWITCH:
            msg = 'SWITCH RTSP/1.0\n' +\
                  'CSeq: ' + str(self.rtspSeq) + '\n' +\
                  'Session: ' + str(self.sessionId)

        if timeout:
            msg += '\nTimeout: ' + timeout

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
            # path name convention difference
            if platform.system() == 'Windows':
                self.imageFile = 'cache\\' + CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
            elif platform.system() == 'Linux':
                self.imageFile = 'cache/' + CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
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
            elif reply[3][0] == 'Movies:':
                self.availableMovies = reply[3][1:]

        return True
    
    def openRtpPort(self, timeout=0.5):
        """Open RTP socket binded to a specified port."""
        exc = False
        try:
            # Create a new datagram socket to receive RTP packets from the server
            rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            rtpSocket.bind(('', self.rtpPort))
        except: # socket already in use
            exc = True
        else:
            self.rtpSocket = rtpSocket
            # Set the timeout value of the socket to 0.5sec
            self.rtpSocket.settimeout(timeout)

        if exc:
            try:
                self.rtpSocket.settimeout(timeout)
            except: # bad file description => timeouted
                self.rtpSocket = rtpSocket
                self.rtpSocket.bind(('', self.rtpPort))
                self.rtpSocket.settimeout(timeout)

        # Set the timeout value of the socket to 0.5sec
        self.rtpSocket.settimeout(timeout)

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        oldState = self.state
        self.pauseMovie()
        if tkinter.messagebox.askyesno("Quit", "Do you want to quit?"):
            try: # close at the beginning
                self.rtpSocket.shutdown(socket.SHUT_RDWR) # stop `recvfrom` function in `listenRtp` => would trigger self.rtpSocket.close()
                self.worker.join()
            except:
                pass
            self.rtspSocket.close()
            self.master.destroy()
        elif oldState == self.PLAYING:
            self.playMovie()

    def sec2time(self, sec): # assuming the length is always < 1 hour
        return str(sec//60).rjust(2,'0') + ':' + str(sec%60).rjust(2,'0')
