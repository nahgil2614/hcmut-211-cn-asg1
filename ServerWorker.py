from random import randint
import sys, traceback, threading, socket, os

from VideoStream import VideoStream
from RtpPacket import RtpPacket

#NOTE: 'rtspSocket' is not closed yet

class ServerWorker:
    SETUP = 'SETUP'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'
    DESCRIBE = 'DESCRIBE'
    SWITCH = 'SWITCH'
    
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
        
    def run(self):
        threading.Thread(target=self.recvRtspRequest).start()
    
    def recvRtspRequest(self):
        """Receive RTSP request from the client."""
        connSocket = self.clientInfo['rtspSocket'][0]
        while True:            
            data = connSocket.recv(256)
            if data:
                print("Data received:\n" + data.decode("utf-8"))
                # if there is a TEARDOWN
                if not self.processRtspRequest(data.decode("utf-8")):
                    connSocket.close()
                    break
    
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
                    video = VideoStream(filename)
                    # retrieve the size
                    size, data = video.getSize()
                    # calculate the total number of frames
                    while data:
                        self.framePos.append(self.framePos[~0]+5+len(data))
                        data = video.nextFrame()

                    totalFrameNbr = video.frameNbr()
                    self.clientInfo['videoStream'] = VideoStream(filename)
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
        
        # Process DESCRIBE request
        elif requestType == self.DESCRIBE:
            assert(int(request[2].split(' ')[1]) == self.clientInfo['session'])
            self.replyRtsp(self.OK_200, seq[1], describe=True)

        # Process PLAY request         
        elif requestType == self.PLAY:
            assert(int(request[2].split(' ')[1]) == self.clientInfo['session'])
            if self.state == self.READY or self.state == self.SWITCHING: # SWITCHING back to the original movie
                print("processing PLAY\n")
                if len(request) == 4:
                    self.state = self.PLAYING
                num = int(request[3].split(' ')[1])
                
                # Create a new socket for RTP/UDP
                self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                
                self.replyRtsp(self.OK_200, seq[1])
                
                # Create a new thread and start sending RTP packets
                self.clientInfo['event'] = threading.Event()
                self.clientInfo['worker']= threading.Thread(target=self.sendRtp, args=(num,))
                self.clientInfo['worker'].start()

            elif self.state == self.PLAYING: # the scrollbar
                num = int(request[3].split(' ')[1])
                #self.replyRtsp(self.OK_200, seq[1]) # currently no reply yet

                self.clientInfo['event'].set()
                self.clientInfo['event'] = threading.Event()
                self.clientInfo['worker']= threading.Thread(target=self.sendRtp, args=(num,))
                self.clientInfo['worker'].start()
        
        # Process PAUSE request
        elif requestType == self.PAUSE:
            assert(int(request[2].split(' ')[1]) == self.clientInfo['session'])
            if self.state == self.PLAYING:
                print("processing PAUSE\n")
                self.state = self.READY
                
                self.clientInfo['event'].set()
            
                self.replyRtsp(self.OK_200, seq[1])
        
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
                # close the connection socket
                return False

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

        return True
            
    def sendRtp(self, num):
        """Send RTP packets over UDP."""
        address = self.clientInfo['rtspSocket'][1][0]
        port = int(self.clientInfo['rtpPort'])
        
        while True:
            self.clientInfo['event'].wait(0.05) 
            
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
                movies = [file for file in os.listdir() if file.endswith('.Mjpeg')]
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
