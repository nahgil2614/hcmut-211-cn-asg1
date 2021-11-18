from random import randint
import sys, traceback, threading, socket, os, time

from VideoStream import VideoStream
from RtpPacket import RtpPacket
from Youtube2Mjpeg import Youtube2Mjpeg

#NOTE: 'rtspSocket' is not closed yet

class ServerWorker:
    SETUP = 'SETUP'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'
    DESCRIBE = 'DESCRIBE'
    SWITCH = 'SWITCH'
    CLOSE = 'CLOSE'
    SPEED = 'SPEED'
    ADD = 'ADD'
    
    INIT = 0
    READY = 1
    PLAYING = 2
    SWITCHING = 3

    OK_200 = 0
    FILE_NOT_FOUND_404 = 1
    CON_ERR_500 = 2
    
    clientInfo = {}
    
    def __init__(self, clientInfo):
        self.state = self.INIT
        self.clientInfo = clientInfo
        self.framePos = [0]
        self.frameReceived = threading.Event()
        self.clientInfo['event'] = threading.Event()

        # exponentially decaying average of sending interval's length
        # for dynamically adapt the sending rate for better timing
        self.processingInterval = 0
        
    def run(self):
        threading.Thread(target=self.recvRtspRequest).start()
    
    def recvRtspRequest(self):
        """Receive RTSP request from the client."""
        connSocket = self.clientInfo['rtspSocket'][0]
        while True:
            try:
                data = connSocket.recv(256)
            except: # the session is ended
                break
            if data:
                print("Data received:\n" + data.decode("utf-8"))
                self.processRtspRequest(data.decode("utf-8"))
    
    def processRtspRequest(self, data):
        """Process RTSP request sent from the client."""
        # Get the request type
        request = data.split('\n')
        line1 = request[0].split(' ')
        requestType = line1[0]
        
        # Get the media file name
        filename = line1[1]
        
        # Get the RTSP sequence number 
        seq = request[1].split(' ')
        
        # Process SETUP request
        if requestType == self.SETUP:
            if self.state == self.INIT or self.state == self.SWITCHING:
                # Update state
                print("processing SETUP\n")
                if self.state == self.SWITCHING:
                    self.framePos.clear()
                    self.framePos = [0]
                try:
                    video = VideoStream('movies\\' + filename)
                    # retrieve the size
                    size, data = video.getSize()
                    # calculate the total number of frames
                    while data:
                        self.framePos.append(self.framePos[~0]+5+len(data))
                        data = video.nextFrame()

                    totalFrameNbr = video.frameNbr()
                    self.clientInfo['videoStream'] = VideoStream('movies\\' + filename)
                except IOError:
                    self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
                    #NOTE: close the connection when there are errors
                    connSocket = self.clientInfo['rtspSocket'][0]
                    connSocket.close()
                
                # Generate a randomized RTSP session ID
                if self.state == self.INIT:
                    self.clientInfo['session'] = randint(100000, 999999)
                
                # Update the state
                self.state = self.READY

                # Send RTSP reply
                self.replyRtsp(self.OK_200, seq[1], info=(totalFrameNbr,size))
                
                # Get the RTP/UDP port from the last line
                self.clientInfo['rtpPort'] = request[2].split(' ')[3]

                # Set the playback speed to normal
                self.waitInterval = 0.05
        
        # Process DESCRIBE request
        elif requestType == self.DESCRIBE:
            assert(int(request[2].split(' ')[1]) == self.clientInfo['session'])
            self.replyRtsp(self.OK_200, seq[1], describe=True)

        # Process PLAY request         
        elif requestType == self.PLAY:
            assert(int(request[2].split(' ')[1]) == self.clientInfo['session'])
            if len(request) == 5 or self.state == self.READY or self.state == self.SWITCHING: # SWITCHING back to the original movie
                print("processing PLAY\n")
                num = int(request[3].split(' ')[1])
                self.replyRtsp(self.OK_200, seq[1])

                if len(request) == 4:
                    self.state = self.PLAYING

                    # Create a new socket for RTP/UDP
                    self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    
                    # Create a new thread and start sending RTP packets
                    self.clientInfo['event'].clear()
                    self.clientInfo['worker'] = threading.Thread(target=self.sendRtp, args=(num,))
                    self.clientInfo['worker'].start()

                else: # the scrollbar
                    self.scrollFrameNbr = num
                    self.frameReceived.set()
        
        # Process PAUSE request
        elif requestType == self.PAUSE:
            assert(int(request[2].split(' ')[1]) == self.clientInfo['session'])
            if len(request) == 4 or self.state == self.PLAYING:
                print("processing PAUSE\n")
                self.clientInfo['event'].set()
                self.replyRtsp(self.OK_200, seq[1])

                if len(request) != 4:
                    self.state = self.READY
                elif request[3].split(' ')[1] == '0':
                    self.clientInfo['event'].clear()
                    self.frameReceived.clear()
                    self.clientInfo['worker'] = threading.Thread(target=self.scrollSendRtp)
                    self.clientInfo['worker'].start()
                elif request[3].split(' ')[1] == '1':
                    self.frameReceived.set()
                elif request[3].split(' ')[1] == '2':
                    self.frameReceived.set()
                    self.state = self.READY
        
        # Process TEARDOWN request
        elif requestType == self.TEARDOWN:
            assert(int(request[2].split(' ')[1]) == self.clientInfo['session'])
            if self.state == self.READY or self.state == self.PLAYING:
                print("processing TEARDOWN\n")
                try: #NOTE: SETUP -> TEARDOWN : exception
                    self.clientInfo['event'].set()
                    # the RTP socket would be closed due to timeout
                    # we would send any images remaining in the buffer
                except:
                    pass

                self.replyRtsp(self.OK_200, seq[1])

        # Process SWITCH request
        elif requestType == self.SWITCH:
            assert(int(request[2].split(' ')[1]) == self.clientInfo['session'])
            if self.state == self.READY or self.state == self.PLAYING:
                print("processing SWITCH\n")
                self.state = self.SWITCHING
                
                try:
                    self.clientInfo['event'].set()
                except:
                    pass
            
                self.replyRtsp(self.OK_200, seq[1], switch=True)

        # Process CLOSE request
        elif requestType == self.CLOSE:
            assert(int(request[2].split(' ')[1]) == self.clientInfo['session'])
            print("processing CLOSE\n")            
            try:
                self.clientInfo['event'].set()
            except:
                pass
        
            self.replyRtsp(self.OK_200, seq[1])
            connSocket = self.clientInfo['rtspSocket'][0]
            connSocket.close()

        # Process SPEED request
        elif requestType == self.SPEED:
            assert(int(request[2].split(' ')[1]) == self.clientInfo['session'])
            print("processing SPEED\n")
            self.waitInterval = 0.025 * 2**int(request[3].split(' ')[1])
            self.replyRtsp(self.OK_200, seq[1])

        # Process ADD request
        elif requestType == self.ADD:
            assert(int(request[2].split(' ')[1]) == self.clientInfo['session'])
            print("processing ADD\n")
            url = request[3].split(' ')[1]
            videoName = request[4].split(' ')[1]
            Youtube2Mjpeg(url, videoName, self.clientInfo['session']).run()
            self.replyRtsp(self.OK_200, seq[1])
            
    def sendRtp(self, num):
        """Send RTP packets over UDP."""
        address = self.clientInfo['rtspSocket'][1][0]
        port = int(self.clientInfo['rtpPort'])
        
        while True:
            # not 0.05 because we have to count the processing time also
            # assume that the total processing time < 0.05 (time for 1 frame)
            # assuming stable network + no queuing delay
            # IRL: queuing delay due to the OS scheduler would make it slower in the client
            # => buffer in Client is the solution (but it would ruin the goal of this assignment, which is the images on user's screen is gotten from the server in real-time)
            # so we didn't implement it
            self.clientInfo['event'].wait(self.waitInterval - self.processingInterval/1000000000)
            
            start = time.perf_counter_ns() # best possible precision
            # Stop sending if request is PAUSE or TEARDOWN
            if self.clientInfo['event'].isSet():
                break 
            
            data = self.clientInfo['videoStream'].getFrame(self.framePos[num], num)
            if data:
                try:
                    self.clientInfo['rtpSocket'].sendto(self.makeRtp(data, num),(address,port))
                    num += 1
                except:
                    print("Connection Error")
            #NOTE: end the finished video
            else:
                break

            # for better timing
            self.processingInterval = 0.85*self.processingInterval - 0.15*start
            self.processingInterval += 0.15*time.perf_counter_ns()

    def scrollSendRtp(self):
        """Send RTP packets for the scrolling client"""
        address = self.clientInfo['rtspSocket'][1][0]
        port = int(self.clientInfo['rtpPort'])
        
        while True:
            self.frameReceived.wait()
            self.clientInfo['event'].wait(0.025) # don't use self.processingInterval as there's no need for natural timing
            
            # Stop sending if request is PAUSE or TEARDOWN
            if self.clientInfo['event'].isSet():
                break 

            data = self.clientInfo['videoStream'].getFrame(self.framePos[self.scrollFrameNbr], self.scrollFrameNbr)
            if data:
                try:
                    self.clientInfo['rtpSocket'].sendto(self.makeRtp(data, self.scrollFrameNbr),(address,port))
                except:
                    print("Connection Error")
            #NOTE: end the finished video
            else:
                break

    def makeRtp(self, payload, frameNbr):
        """RTP-packetize the video data."""
        version = 2
        padding = 0
        extension = 0
        cc = 0
        marker = 0
        pt = 26 # MJPEG type
        seqnum = frameNbr
        ssrc = 0 
        
        rtpPacket = RtpPacket()
        
        rtpPacket.encode(version, padding, extension, cc, seqnum, marker, pt, ssrc, payload)
        
        return rtpPacket.getPacket()
        
    def replyRtsp(self, code, seq, describe=False, info=(0,()), switch=False):
        """Send RTSP reply to the client."""
        connSocket = self.clientInfo['rtspSocket'][0]

        if code == self.OK_200:
            print("200 OK")
            reply = 'RTSP/1.0 200 OK\n' +\
                    'CSeq: ' + seq + '\n' +\
                    'Session: ' + str(self.clientInfo['session'])
            if describe:
                reply += '\nDescription: <kinds_of_streams> <encoding>'
            elif info[0]:
                reply += '\nInfo: ' + str(info[0]) + ' ' + str(info[1][0]) + ' ' + str(info[1][1])
            elif switch:
                movies = [file for file in os.listdir('movies') if file.endswith('.Mjpeg')]
                reply += '\nMovies: ' + ' '.join(movies)
        
        # Error messages
        #NOTE: server always reply to client
        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
            reply = 'RTSP/1.0 404 Not Found\n' +\
                    'CSeq: ' + seq + '\n' +\
                    'Session: ' + str(self.clientInfo['session'])

        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")
            reply = 'RTSP/1.0 500 Internal Server Error\n' +\
                    'CSeq: ' + seq + '\n' +\
                    'Session: ' + str(self.clientInfo['session'])
        
        connSocket.send(reply.encode())
