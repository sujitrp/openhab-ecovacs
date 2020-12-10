from deebotozmo import *
import configparser
from deebotozmo.cli import *
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt
import json
import os
import time

from ObservableVacBot import *

# reading config from env
config = {
    'email' : os.environ.get('email',''),
    'password' : os.environ.get('password',''),
    'device_id' : os.environ.get('device_id',''),
    'country' : os.environ.get('country','').lower(),
    'continent' : os.environ.get('continent','').lower(),
    'verify_ssl' : os.environ.get('verify_ssl',''),
    'mqtt_client_id' : os.environ.get('mqtt_client_id',''),
    'mqtt_client_host' : os.environ.get('mqtt_client_host',''),
    'mqtt_client_port' : os.environ.get('mqtt_client_port',''),
    'mqtt_client_keepalive' : os.environ.get('mqtt_client_keepalive',''),
    'mqtt_client_bind_address' : os.environ.get('mqtt_client_bind_address',''),
    'mqtt_client_root_topic' : os.environ.get('mqtt_client_root_topic','')
}

# init the api
api = EcoVacsAPI(config['device_id'], config['email'], EcoVacsAPI.md5(config['password']),  config['country'], config['continent'])

# first device in list
my_vac = api.devices()[0]
# Device ID for a future multi device version
did=str(my_vac['did'])
print("Device ID: "+did)


vacbot = ObservableVacBot(api.uid, api.REALM, api.resource, api.user_access_token, my_vac, config['continent'])
vacbot.connect_and_wait_until_ready()

# MQTT INIT
mqttclient = mqtt.Client(config['mqtt_client_id'])
mqttclient.connect(host=config['mqtt_client_host'], port=int(config['mqtt_client_port']), keepalive=int(config['mqtt_client_keepalive']),bind_address=config['mqtt_client_bind_address'])



## ECOVACS ---> MQTT
## Callback functions. Triggered when sucks receives a status change from Ecovacs.
# Callback function for battery events
def battery_report(level):    
    mqttpublish(did,"battery_level",str(level))

# Callback function for status events
def status_report(status):
    mqttpublish(did,"status",status)
    
# Callback function for lifespan (components) events
def lifespan_report(event):
    response = event['body']['data'][0]

    type = COMPONENT_FROM_ECOVACS[response['type']]
        
    left = int(response['left'])
    total = int(response['total'])        
    lifespan = (left/total) * 100

    mqttpublish(did, "components/" + type, lifespan)

def fan_speed_report(speed):
    mqttpublish(did, "fanspeed", speed)

def clean_log_report(event):
    (logs, image) = event
    #mqttpublish(did,"lastCleanLogs", logs)
    mqttpublish(did,"last_clean_image", image)

def water_level_report(event):
    (water_level,mop_attached) = event
    mqttpublish(did, "water_level", water_level)
    mqttpublish(did, "mop_attached", mop_attached)

def stats_events_report(event):
    response = event['body']

    if response['code'] == 0:
        if 'area' in  response['data']:
            stats_area = response['data']['area']
            mqttpublish(did,"stats_area", stats_area)

        if 'cid' in  response['data']:
            stats_cid = response['data']['cid']
            mqttpublish(did,"stats_cid", stats_cid)
        
        if 'time' in  response['data']:
            stats_time = response['data']['time'] / 60
            mqttpublish(did,"stats_time", stats_time)

        if 'type' in response['data']:
            stats_type = response['data']['type']
            mqttpublish(did,"stats_type", stats_type)

# Callback function for error events
# THIS NEEDS A LOT OF WORK
def error_report(event):
    error_str=str(event)
    mqttpublish(did,"error",error_str)
    print("Error: "+error_str)


# Publish to MQTT. Root topic should be in a config file or at least defined at the top.
def mqttpublish(did,subtopic,message):
    topic=config['mqtt_client_root_topic']+"/"+did+"/"+subtopic
    print(topic, message)
    mqttclient.publish(topic, message)

vacbot.errorEvents.subscribe(error_report)
vacbot.lifespanEvents.subscribe(lifespan_report)

vacbot.fanspeedEvents.subscribe(fan_speed_report)
vacbot.cleanLogsEvents.subscribe(clean_log_report)
vacbot.waterEvents.subscribe(water_level_report)          
vacbot.batteryEvents.subscribe(battery_report)
vacbot.statusEvents.subscribe(status_report)
vacbot.statsEvents.subscribe(stats_events_report)


# For the first run, try to get & report all statuses
vacbot.setScheduleUpdates()
vacbot.refresh_statuses()
vacbot.refresh_components()


## MQTT ----> Ecovacs
# Subscribe to this ecovac topics, translate mqtt commands into sucks commands to robot
subscribe_topic=config['mqtt_client_root_topic']+"/"+did+"/command"
print("Subscribe topic: "+subscribe_topic)
mqttclient.subscribe(subscribe_topic)

def on_message(client, userdata, message):
    received_command=str(message.payload.decode("utf-8")).lstrip()
    print("message received=-"+received_command+"-")
    print("message topic=",message.topic)
    print("message qos=",message.qos)
    print("message retain flag=",message.retain)
    if received_command == "Clean":  
        vacbot.Clean()
    elif received_command == "CleanPause":
        vacbot.CleanPause()
    elif received_command == "CleanResume":
        vacbot.CleanResume()
    elif received_command == "Charge":
        vacbot.Charge()
    elif received_command == "PlaySound":
        vacbot.PlaySound()
    elif received_command == "Relocate":
        vacbot.Relocate()
    elif received_command == "GetCleanLogs":
        vacbot.GetCleanLogs()
    elif received_command == "CustomArea":
        pass
        #vacbot.CustomArea()
    elif received_command == "SpotArea":
        pass
        #vacbot.SpotArea()
    elif received_command == "SetFanSpeed":
        vacbot.SetFanSpeed(speed=0)
    elif received_command == "SetWaterLevel":
        pass
        #vacbot.SetWaterLevel()
    else:
        print("Unknown command")
        
mqttclient.on_message=on_message

mqttclient.loop_forever()