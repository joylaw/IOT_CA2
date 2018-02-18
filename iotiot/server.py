#Import all the libraries here
import gevent
import gevent.monkey
from gevent.pywsgi import WSGIServer
import datetime
import pymysql
import signal
import multiprocessing
from time import sleep
import os
import time
import json
from flask import jsonify
from gpiozero import LED
import sys
import threading
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
from flask import Flask, request, Response, render_template
import RPi.GPIO as GPIO
import MFRC522
from flask import Flask,redirect
import picamera
import os

gevent.monkey.patch_all()

def getdatetime():
	return time.strftime('%Y-%m-%d %H:%M:%S')

led_status = None
def light_status(client, userdata, message):
	global led_status
	led_status = json.loads(message.payload)
	print led_status

def mqtt_connect():
	my_rpi = AWSIoTMQTTClient("subscriber_led")

	host = "a2jaqhb8rc300f.iot.us-west-2.amazonaws.com"
	rootCAPath = "rootca.pem"
	certificatePath = "certificate.pem.crt"
	privateKeyPath = "private.pem.key"

	my_rpi.configureEndpoint(host, 8883)
	my_rpi.configureCredentials(rootCAPath, privateKeyPath, certificatePath)

	my_rpi.configureOfflinePublishQueueing(-1)
	my_rpi.configureDrainingFrequency(2)
	my_rpi.configureConnectDisconnectTimeout(10)
	my_rpi.configureMQTTOperationTimeout(5)

	my_rpi.connect()

	#Subscribe
	my_rpi.subscribe("led/status", 1, light_status)

def dbconnect():
	try:
		db = pymysql.connect(host = "iot.cyygylyw5wux.us-west-2.rds.amazonaws.com", user="admin",passwd="!QWER4321", port=3306, db="iot")
		print("Successfully connected to database")
		return db
	except:
		print("Error connecting to mySQL database")

def getRFID():
	#Create an object of the class MFRC522
	mfrc522 = MFRC522.MFRC522()
	
	#This loop keeps checking for chips.
	#If one is near it will get the UID
	try:
		while True:
			#Scan for cards
			(status,TagType)= mfrc522.MFRC522_Request(mfrc522.PICC_REQIDL)
			
			#If a card is found
			if status == mfrc522.MI_OK:
			
				#Get the UID of the card
				(status,uid) = mfrc522.MFRC522_Anticoll()
				print uid
				return uid
	except:
		GPIO.cleanup()

def createNewUser():
	uid = getRFID()

def showRFID():
	db = dbconnect()
	curs = db.cursor()

	try:
		results = []
		curs.execute("SELECT id, date_time, name from rfid_accesslog L, rfid_access A WHERE L.rfid_uid=A.rfid_uid order by L.id desc limit 8")
		data = curs.fetchall() #get all the results in database
		for row in data:
			results.append(row)
		curs.close()
		db.close()
		return results
	except MySQLdb.Error as e:
		print e
	except KeyboardInterrupt:
		curs.close()
		db.close()

app = Flask(__name__)

#Start: Declaring app route here [after app=Flask(__name__)]
@app.route("/")
def index():
	results = showRFID()
	templateData = {
		'results' : results
	}
	return render_template('index.html', **templateData)

@app.route("/readRFID")
def readRFID():
	uid = getRFID()
	return jsonify(uid=uid)

@app.route("/addUser", methods=['POST'])
def addUser():
	if request.method == 'POST':
		uid = request.form['uid']
                name = request.form['name']
		uid = uid.replace(',', ', ')
		uid = '['+uid+']'

		print uid
		print name

		db = dbconnect()
		curs = db.cursor()

		sql = "INSERT INTO rfid_access (rfid_uid, name) VALUES (\'{0}\', \'{1}\')".format(uid, name)

		curs.execute(sql)
		db.commit()
		curs.close()
		db.close()

	return redirect('/')

@app.route("/newUser")
def newUser():
	return render_template('newUser.html')

# [LED(18), LED(21), LED(19), LED(13)] 0-3
@app.route("/readLED/<LED>")
def readLED(LED):
	return jsonify(response=led_status[LED])

@app.route("/writeLED/<LED>/<status>")
def writeLED(LED, status):
	led_data = {"led":LED, "status":status}

	my_rpi = AWSIoTMQTTClient("publisher_led")

	host = "a2jaqhb8rc300f.iot.us-west-2.amazonaws.com"
	rootCAPath = "rootca.pem"
	certificatePath = "certificate.pem.crt"
	privateKeyPath = "private.pem.key"

	my_rpi.configureEndpoint(host, 8883)
	my_rpi.configureCredentials(rootCAPath, privateKeyPath, certificatePath)

	my_rpi.configureOfflinePublishQueueing(-1)
	my_rpi.configureDrainingFrequency(2)
	my_rpi.configureConnectDisconnectTimeout(10)
	my_rpi.configureMQTTOperationTimeout(5)

	my_rpi.connect()

	my_rpi.publish("led/control", json.dumps(led_data), 1)

	return "Error removals R' US"

@app.route("/showImage/<access_id>")
def showImage(access_id):
	sql = "SELECT date_time, name from rfid_accesslog L, rfid_access A WHERE L.rfid_uid=A.rfid_uid AND L.id = {}".format(access_id)

	db = dbconnect()
	curs = db.cursor()
	curs.execute(sql)

	result = curs.fetchone()
	
	curs.close()
	db.close()

	templateData = {
		'datetime' : result[0],
		'name': result[1]
	}
	return render_template('image.html', **templateData)

@app.route("/MQTTGraphValues")
def MQTTGraphValues():
	graphValues = [[],[],[]]
	sql = "SELECT date_time, temperature, humidity FROM temp_humidity ORDER BY date_time DESC LIMIT 10"

	db = dbconnect()
	curs = db.cursor()
	curs.execute(sql)

	curs.close()
	db.close()

	for (datetime, temperature, humidity) in curs:
		#graphValues[0].append(datetime)
		graphValues[0].insert(0, datetime)
		#graphValues[1].append(temperature)
		graphValues[1].insert(0, temperature)
		#graphValues[2].append(humidity)
		graphValues[2].insert(0, humidity)

	return jsonify(graphdata=graphValues)

if __name__ == '__main__':
	mqtt_connect()
	try:
		print "Starting Server"
		http_server = WSGIServer(('0.0.0.0', 8010), app)
		app.debug = True
		http_server.serve_forever()
	except Exception as e:
		print(e)
	except KeyboardInterrupt:
		print "Terminate Server"
