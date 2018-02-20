# Import SDK packages
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
from time import sleep
import time, datetime
import json
import Adafruit_DHT
import multiprocessing
from signal import pause
from gpiozero import LED
import MFRC522
import re
import boto3
import botocore
import RPi.GPIO as GPIO
from picamera import PiCamera
import os
import pymysql

# Returns tuple: (Humidity, Temperature)
def gethumiditytemp():
	return Adafruit_DHT.read_retry(11, 4)

def getdatetime():
	return time.strftime('%Y-%m-%d %H:%M:%S')

s3 = boto3.resource('s3')

def prepareImage():
	camera = PiCamera()
	datetime = time.strftime('%Y-%m-%d_%H-%M-%S') #Get the current date and time
	full_path = os.getcwd() + "/"+datetime+".jpg"
	file_name = datetime+'.jpg'
	camera.capture(full_path)
	camera.close()
	return datetime, full_path, file_name

def setS3():
	bucket_name = 'accesssmarthome' # replace with your own unique bucket name
	exists = True
	try:
		s3.meta.client.head_bucket(Bucket=bucket_name)
	except botocore.exceptions.ClientError as e:
		error_code = int(e.response['Error']['Code'])
		if error_code == 404:
	        	exists = False
	if exists == False:
		s3.create_bucket(Bucket=bucket_name,CreateBucketConfiguration={'LocationConstraint': 'us-west-2'})
	return bucket_name

def rfid():
	mfrc522 = MFRC522.MFRC522()
	try:
		while True:
			(status,TagType)= mfrc522.MFRC522_Request(mfrc522.PICC_REQIDL)
			if status == mfrc522.MI_OK:
				(status,uid) = mfrc522.MFRC522_Anticoll()
				datetime, full_path, file_name = prepareImage()
				bucket_name = setS3()
				db = pymysql.connect(host = "iotca2.cmwnxcwvcz4v.us-west-2.rds.amazonaws.com", user="admin",passwd="!QWER4321", port=3306, db="iotca2")
				s3.Object(bucket_name, file_name).put(Body=open(full_path, 'rb'))
				try:
				    with db.cursor() as cur:
				            cur.execute("INSERT into rfid_accesslog (date_time, rfid_uid) VALUES ('{0}', '{1}')".format(datetime,uid))
				            db.commit()
				except Exception, e:
				        print (e)
				db.close()
				os.remove(full_path)
				sleep(5)
	except:
		GPIO.cleanup()

LEDS = [LED(18), LED(21), LED(19), LED(13)]

def light_controller(client, userdata, message):
	data = json.loads(message.payload)

	print(data)

	if data is not None:
		led = int(data["led"])
		print led
		if led <= len(LEDS):
			if data["status"] == "ON":
				LEDS[led].on()
			elif data["status"] == "OFF":
				LEDS[led].off()
			else:
				print("INVALID COMMAND")

def light_status():
	led_status = {}
	for led in LEDS:	
		led_status.update({LEDS.index(led):led.is_lit})
	return led_status

def mqtt_connect():

	host = "a7gx67jy14o4h.iot.us-west-2.amazonaws.com"
	rootCAPath = "rootca.pem"
	certificatePath = "certificate.pem.crt"
	privateKeyPath = "private.pem.key"

	my_rpi = AWSIoTMQTTClient("publisher")
	my_rpi.configureEndpoint(host, 8883)
	my_rpi.configureCredentials(rootCAPath, privateKeyPath, certificatePath)

	my_rpi.configureOfflinePublishQueueing(-1)
	my_rpi.configureDrainingFrequency(2)
	my_rpi.configureConnectDisconnectTimeout(10)
	my_rpi.configureMQTTOperationTimeout(5)

	my_rpi.connect()

	#Subscribe
	my_rpi.subscribe("led/control", 1, light_controller)

	while True:
		HT = gethumiditytemp()
		iot_data = {"datetime":str(getdatetime()), "temperature":str(HT[1]), "humidity":str(HT[0])}
		my_rpi.publish("sensors/temp_humid", json.dumps(iot_data), 1)
		print("published ", iot_data)
		light_stat = light_status()
		my_rpi.publish("led/status", json.dumps(light_stat), 1)
		print("published ", light_stat)
		sleep(5)

if __name__ == '__main__':
	multiprocessing.Process(target=mqtt_connect).start()
	multiprocessing.Process(target=rfid).start()
	pause()