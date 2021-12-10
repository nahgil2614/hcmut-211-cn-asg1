import threading, os, cv2

from PIL import Image
from pytube import YouTube

class Youtube2Mjpeg:
    def __init__(self, url, fileName, session):
        self.url = url
        self.fileName = fileName
        self.path = './tmp/' + str(session)

    def run(self, noticeEvent, invalidLinkEvent):
        threading.Thread(target=self.process, args=(noticeEvent, invalidLinkEvent)).start()

    def process(self, noticeEvent, invalidLinkEvent):        
        self.download(noticeEvent, invalidLinkEvent)
        if not invalidLinkEvent.isSet():
            os.mkdir(self.path+'/frames')
            self.totalFrameNbr = self.mp4ToJpg()
            self.resizeJpg()
            self.changeQuality()
            self.makeMjpeg()
            self.collectGarbage()

    def download(self, noticeEvent, invalidLinkEvent):
        yt = YouTube(self.url)
        try:
            video = yt.streams.get_highest_resolution()
        except:
            invalidLinkEvent.set()
            noticeEvent.set()
            return
        noticeEvent.set()
        video.download(self.path, filename=self.fileName+'.mp4')

    def mp4ToJpg(self):
        count = 0
        vidcap = cv2.VideoCapture(self.path+'/'+self.fileName+'.mp4')
        while True:
            vidcap.set(cv2.CAP_PROP_POS_MSEC,(count*50))
            success, image = vidcap.read()
            if not success:
                break
            cv2.imwrite(self.path+'/frames/%d.jpg' % int(count), image)     # save frame as JPEG file
            count = count + 1
        return count

    def resizeJpg(self):
        img = Image.open(self.path+'/frames/0.jpg')
        w,h = img.size
        img.close()

        ratio = min(600/w, 300/h)
        w = int(w * ratio)
        h = int(h * ratio)
        for i in range(self.totalFrameNbr):
            img = Image.open(self.path+'/frames/'+str(i)+'.jpg')
            img = img.resize((w,h), Image.ANTIALIAS)
            img.save(self.path+'/frames/_'+str(i)+'.jpg', optimize=True, quality=95)
            img.close()
            os.remove(self.path+'/frames/'+str(i)+'.jpg')
            os.rename(self.path+'/frames/_'+str(i)+'.jpg', self.path+'/frames/'+str(i)+'.jpg')

    def changeQuality(self):
        quality = 95
        while True:
            maxSize = max([os.stat(self.path+'/frames/'+str(i)+'.jpg').st_size for i in range(self.totalFrameNbr)])
            if maxSize < (1 << 16): # max size for a UDP datagram
                break

            quality -= 5
            for i in range(self.totalFrameNbr):
                img = Image.open(self.path+'/frames/'+str(i)+'.jpg')
                img.save(self.path+'/frames/_'+str(i)+'.jpg', optimize=True, quality=quality)
                img.close()
                os.remove(self.path+'/frames/'+str(i)+'.jpg')
                os.rename(self.path+'/frames/_'+str(i)+'.jpg', self.path+'/frames/'+str(i)+'.jpg')

    def makeMjpeg(self):
        mjpeg = b''
        for i in range(self.totalFrameNbr):
            with open(self.path+'/frames/'+str(i)+'.jpg', 'rb') as img:
                data = img.read()
                mjpeg += str(len(data)).rjust(5,'0').encode() + data
        with open('./movies/'+self.fileName+'.Mjpeg', 'wb') as file:
            file.write(mjpeg)

    def collectGarbage(self):
        for i in range(self.totalFrameNbr):
            os.remove(self.path+'/frames/'+str(i)+'.jpg')
        os.remove(self.path+'/'+self.fileName+'.mp4')
        os.rmdir(self.path+'/frames')
        os.rmdir(self.path)