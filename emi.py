import imutils
import time
import cv2
from rtlsdr import RtlSdr
import scipy.signal
import numpy as np
import matplotlib.pyplot as plt
from scipy.ndimage.filters import gaussian_filter
import argparse

scale=10

def gaussian_with_nan(U, sigma=7):
	"""Computes the gaussian blur of a nupy array with NaNs.
	"""
	np.seterr(divide='ignore', invalid='ignore')
	V=U.copy()
	V[np.isnan(U)]=0
	VV=gaussian_filter(V,sigma=sigma)

	W=0*U.copy()+1
	W[np.isnan(U)]=0
	WW=gaussian_filter(W,sigma=sigma)
	o=VV/WW
	mi,ma=np.nanmin(o),np.nanmax(o)
	os=((o-mi)*255/(ma-mi))
	os[np.isnan(U)]=0
	return np.uint8(os)

def print_sdr_config(sdr):
	"""Prints the RTL-SDR configuration in the console.
	"""
	print("RTL-SDR config:")
	print("    * Using device",sdr.get_device_serial_addresses())
	print("    * Device opened:", sdr.device_opened)
	print("    * Center frequency:",sdr.get_center_freq(),"Hz")
	print("    * Sample frequency:",sdr.get_sample_rate(),"Hz")
	print("    * Gain:",sdr.get_gain(),"dB")
	print("    * Available gains:",sdr.get_gains())
	
def get_RMS_power(sdr):
	"""Measures the RMS power with a RTL-SDR.
	"""
	samples = sdr.read_samples(1024*4)
	freq,psd = scipy.signal.welch(samples,sdr.sample_rate/1e6,nperseg=512,return_onesided=0)
	return 10*np.log10(np.sqrt(np.mean(psd**2))),samples

# mouse callback function
def showSpectrum(event,x,y,flags,param):
    if event == cv2.EVENT_LBUTTONDBLCLK:
        print(x,y)
        if specmap is not None:
        	xb,yb=int(y/scale),int(x/scale)
        	re=specmap[xb,yb]
        	if re is not None:
        		
	        	plt.close() 
	        	plt.psd(re, NFFT=1024, Fs=sdr.sample_rate/1e6, Fc=sdr.center_freq/1e6)
	        	plt.title("spectrum "+str(xb)+" "+str(yb))
	        	plt.show()

# Thanks to https://www.pyimagesearch.com/2015/05/25/basic-motion-detection-and-tracking-with-python-and-opencv/
# for the tracking tutorial.

print("Usage:")
print("    * Press s to select the probe.")
print("    * Press r to reset.")
print("    * Press q to display the EMI map and exit.")
print("Call with -h for help on the args.")
		
# parse args
parser = argparse.ArgumentParser(description='EMI mapping with camera and RTL-SDR.')
parser.add_argument('-c', '--camera', type=int, help='camera id (default=0)',default=0)
parser.add_argument('-f', '--frequency', type=float, help='sets the center frequency on the SDR, in MHz (default: 300).',default=300)
parser.add_argument('-g', '--gain', type=int, help='sets the SDR gain (default: 496).',default=496)
parser.add_argument('-d', '--device', type=int, help='sets the SDR device (default: 0).',default=0)
args = parser.parse_args()

# configure SDR device
sdr = RtlSdr(args.device)
sdr.sample_rate = 2.4e6
sdr.center_freq = args.frequency * 1e6
sdr.gain = args.gain
sdr.set_agc_mode(0)
#print_sdr_config(sdr)

# read from specified webcam
cap = cv2.VideoCapture(args.camera)
if cap is None or not cap.isOpened():
	   print('Error: unable to open video source: ', args.camera)
else:
	# wait some time for the camera to be ready
	time.sleep(2.0)

# initialize variables
powermap = None
firstFrame = None

# Init OpenCV object tracker objects
tracker = cv2.TrackerCSRT_create()
init_tracking_BB = None

cv2.namedWindow('Preview')
cv2.setMouseCallback('Preview',showSpectrum)
# loop while exit button wasn't pressed
while True:
	# grab the current frame
	ret, frame = cap.read()

	# if the frame could not be grabbed, then we have reached the end
	# of the video
	if ret == False or frame is None:
		break

	# resize the frame, convert it to grayscale, and blur it
	frame = imutils.resize(frame, width=500)

	# if the first frame is None, initialize it
	if firstFrame is None:
		firstFrame = frame
		powermap = np.empty((len(frame),len(frame[0])))
		powermap.fill(np.nan)
		specmap = np.empty((len(frame),len(frame[0])),dtype=np.object)
		specmap.fill(None)
		continue

	
	# tracking and reading SDR
	if init_tracking_BB is not None:
		# grab the new bounding box coordinates of the object
		(success, box) = tracker.update(frame)

		# check to see if the tracking was a success
		power,samples = get_RMS_power(sdr)
		
		if success:
			(x, y, w, h) = [int(v) for v in box]
			# print bounding box
			cv2.rectangle(frame, (x, y), (x + w, y + h),
				(0, 255, 0), 2)
			# fill map
			print("RMS power",power,"dBm at",x+w/2,";",y+h/2)
			powermap[int(y+h/4):int(y+h/4*3),int(x+w/4):int(x+w/4*3)] = power
			specmap[int((y+h/2)/scale),int((x+w/2)/scale)] =samples

			cv2.putText(frame,"RMS power{:.2f}".format(power), (10, 40),cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
		else:
			print("RMS power",power,"dBm at unknown location")	
	# show the frame (adding scanned zone overlay)
	frame[:,:,2] = np.where(np.isnan(powermap),frame[:,:,2],255/2)
	cv2.imshow("Frame", frame)
	if init_tracking_BB is not None and powermap is not None and firstFrame is not None:
		blurred = gaussian_with_nan(powermap, sigma=7)
		blurredC = cv2.applyColorMap(blurred,cv2.COLORMAP_HOT)
		cv2.imshow("Preview",cv2.addWeighted(firstFrame, 0.4, blurredC, 0.6,0.0 	))
	# handle keypresses
	key = cv2.waitKey(1) & 0xFF
	if key == ord("s") and init_tracking_BB is None:
		# select the bounding box
		init_tracking_BB = cv2.selectROI("Frame", frame, fromCenter=False,
			showCrosshair=True)

		# start OpenCV object tracker
		tracker.init(frame, init_tracking_BB)
	elif key == ord("q"):
		break
	elif key == ord("r"):
		firstFrame = None

# gracefully free the resources
sdr.close()
cap.release()
cv2.destroyAllWindows()

# generate picture
if init_tracking_BB is not None and powermap is not None and firstFrame is not None:
	blurred = gaussian_with_nan(powermap, sigma=7)
	plt.imshow(cv2.cvtColor(firstFrame, cv2.COLOR_BGR2RGB))
	plt.imshow(blurred, cmap='hot', interpolation='nearest',alpha=0.55)
	plt.axis('off')
	plt.title("EMI map (min. "+"%.2f" % np.nanmin(powermap)+" dBm, max. "+"%.2f" % np.nanmax(powermap)+" dBm)")
	plt.show()
	# TODO : add distribution plot
else:
	print("Warning: nothing captured, nothing to do")
