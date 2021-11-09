from PIL import Image
from io import BytesIO

#NOTE: file is not closed
class VideoStream: #Mjpeg only
	def __init__(self, filename):
		self.filename = filename
		try:
			self.file = open(filename, 'rb')
		except:
			raise IOError
		self.frameNum = 0
	
	def getSize(self):
		"""Get next frame."""
		data = self.file.read(5) # Get the framelength from the first 5 bytes
		if data:
			framelength = int(data)
							
			# Read the current frame
			data = self.file.read(framelength)
			self.frameNum += 1

			# Read the size
			size = Image.open(BytesIO(data)).size
		return size, data

	def nextFrame(self):
		"""Get next frame."""
		data = self.file.read(5) # Get the framelength from the first 5 bytes
		if data:
			framelength = int(data)
							
			# Read the current frame
			data = self.file.read(framelength)
			self.frameNum += 1
		return data

	def getFrame(self, pos, num):
		"""Get a frame at pos."""
		self.file.seek(pos)
		self.frameNum = num
		data = self.file.read(5) # Get the framelength from the first 5 bytes
		if data:
			framelength = int(data)
							
			# Read the current frame
			data = self.file.read(framelength)
		return data
		
	def frameNbr(self):
		"""Get frame number."""
		return self.frameNum
	
	