from random import randint
import sys, traceback, threading, socket

from VideoStream import VideoStream
from RtpPacket import RtpPacket

#NOTE: 'rtspSocket' is not closed yet

class ServerWorker:
    SETUP = 'SETUP'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'
    DESCRIBE = 'DESCRIBE'
    
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    OK_200 = 0
    FILE_NOT_FOUND_404 = 1
    CON_ERR_500 = 2
    
    clientInfo = {}
    
    def __init__(self, clientInfo):
        self.clientInfo = clientInfo
        
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
            #NOTE: return from the unused thread
            else:
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
            if self.state == self.INIT:
                # Update state
                print("processing SETUP\n")
                
                try:
                    video = VideoStream(filename)
                    # retrieve the size
                    size = video.getSize()
                    # calculate the total number of frames
                    while video.nextFrame():
                        pass
                    totalFrameNbr = video.frameNbr()
                    self.clientInfo['videoStream'] = VideoStream(filename)
                    self.state = self.READY
                except IOError:
                    self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
                    #NOTE: close the connection when there are errors
                    connSocket = self.clientInfo['rtspSocket'][0]
                    connSocket.close()
                
                # Generate a randomized RTSP session ID
                self.clientInfo['session'] = randint(100000, 999999)
                
                # Send RTSP reply
                self.replyRtsp(self.OK_200, seq[1], info=(totalFrameNbr,size))
                
                # Get the RTP/UDP port from the last line
                self.clientInfo['rtpPort'] = request[2].split(' ')[3]
        
        # Process DESCRIBE request
        elif requestType == self.DESCRIBE:
            self.replyRtsp(self.OK_200, seq[1], describe=True)

        # Process PLAY request         
        elif requestType == self.PLAY:
            if self.state == self.READY:
                print("processing PLAY\n")
                self.state = self.PLAYING
                
                # Create a new socket for RTP/UDP
                self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                
                self.replyRtsp(self.OK_200, seq[1])
                
                # Create a new thread and start sending RTP packets
                self.clientInfo['event'] = threading.Event()
                self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
                self.clientInfo['worker'].start()
        
        # Process PAUSE request
        elif requestType == self.PAUSE:
            if self.state == self.PLAYING:
                print("processing PAUSE\n")
                self.state = self.READY
                
                self.clientInfo['event'].set()
            
                self.replyRtsp(self.OK_200, seq[1])
        
        # Process TEARDOWN request
        elif requestType == self.TEARDOWN:
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

        return True
            
    def sendRtp(self):
        """Send RTP packets over UDP."""
        while True:
            self.clientInfo['event'].wait(0.05) 
            
            # Stop sending if request is PAUSE or TEARDOWN
            if self.clientInfo['event'].isSet(): 
                break 
                
            data = self.clientInfo['videoStream'].nextFrame()
            if data: 
                frameNumber = self.clientInfo['videoStream'].frameNbr()
                try:
                    address = self.clientInfo['rtspSocket'][1][0]
                    port = int(self.clientInfo['rtpPort'])
                    self.clientInfo['rtpSocket'].sendto(self.makeRtp(data, frameNumber),(address,port))
                except:
                    print("Connection Error")
                    #print('-'*60)
                    #traceback.print_exc(file=sys.stdout)
                    #print('-'*60)
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
        
    def replyRtsp(self, code, seq, describe=False, info=(0,())):
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
