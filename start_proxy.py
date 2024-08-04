#!/usr/bin/env python3

import asyncio
import socket
import websockets
import json
import time
import requests
import logging
from threading import Thread

from http.server import BaseHTTPRequestHandler, HTTPServer
#import cgi

# Konfigurationsparameter
filter_uuid_import = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" # import
filter_uuid_export = "xxxxxxxx-xxxx-xxxx-xxxxxxxxxxxxxxxxx" # export
uri = "ws://volkszaehler:8082/socket"  # Ersetze dies mit der tatsächlichen URI des Volkszähler Push Servers
server_port = 8001

# Variablen zum Abfragen aller benötigten Leistungen
value_export = None
value_import = None
value_wp = 0

# Variablen zum Verfolgen des letzten Empfangs
last_received_export = None
last_received_import = None

data_import = None
data_export = None

sampling_time = 10

# Logging-Konfiguration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vzloggerProxy")

# Funktion zur Verarbeitung empfangener Nachrichten
async def handle_message(message):
    global value_export, value_import, last_received_export, last_received_import
    global data_export, data_import
    data = json.loads(message)
    logger.debug(f"Received message: {data}")

    if "data" in data:
        uuid = data["data"]["uuid"]
        value = data["data"]["tuples"][0][1]
        if uuid == filter_uuid_export:
            value_export = value
            data_export = data
            last_received_export = time.time()
            logger.debug(f"Received value for export UUID {filter_uuid_export}: {value_export}")
        elif uuid == filter_uuid_import:
            value_import = value
            data_import = data
            last_received_import = time.time()
            logger.debug(f"Received value for import UUID {filter_uuid_import}: {value_import}")

# Funktion zur Berechnung und Ausgabe der Differenz
async def calculate_difference():
    global value_export, value_import, last_received_export, last_received_import
    while True:
        await asyncio.sleep(sampling_time)
        current_time = time.time()
        logger.info(f"---")

        # Setze Werte auf Null, wenn keine Daten für 60 Sekunden empfangen wurden
        if last_received_export is not None and (current_time - last_received_export) > 60:
            value_export = 0
        if last_received_import is not None and (current_time - last_received_import) > 60:
            value_import = 0

        if value_export is not None and value_import is not None:
            difference = value_import - value_export + value_wp
            logger.info(f"import power: {difference} W")

# Funktion zur Wiederverbindung bei Verbindungsausfall
async def volkszaehler_client():
    global uri
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                # Starten der Aufgaben zur Berechnung der Differenz und Abfrage der Wärmepumpenleistung
                asyncio.create_task(calculate_difference())

                # Verarbeitung der empfangenen Nachrichten
                async for message in websocket:
                    await handle_message(message)
        except websockets.ConnectionClosed as e:
            logger.warning(f"Connection closed: {e}")
        except Exception as e:
            logger.error(f"An error occurred: {e}")

        logger.info("Reconnecting in 5 seconds...")
        await asyncio.sleep(5)

def start_volkszaehler_client():
    asyncio.run(volkszaehler_client())

def start_server():
    host = ''
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, server_port))
    s.listen(5)
    print(f'Server on port {server_port} started')

    while True:
        c, addr = s.accept()
        print(f"Connected to {addr}")
        dat="Hello socket"
        dat="{ \"version\": \"0.8.0\", \"generator\": \"vzlogger\", \"data\": [ " + str(data_export['data']) + "," + str(data_import['data']) + " ] }"
        dat2 = 'HTTP/1.0 200 OK\n\n' + dat.replace("'", '\"')
        logger.info("Sending " + dat2)
        c.sendall(dat2.encode())
        time.sleep(0.5)
        c.close()

class Server(BaseHTTPRequestHandler):
    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
    def do_HEAD(self):
        self._set_headers()
        
    # GET sends back a Hello world message
    def do_GET(self):
        self._set_headers()
        dat="{ \"version\": \"0.8.0\", \"generator\": \"vzlogger\", \"data\": [ " + str(data_export['data']) + "," + str(data_import['data']) + " ] }"
        dat2 = dat.replace("'", '\"')
        #dat2 = 'HTTP/1.0 200 OK\n\n' + dat.replace("'", '\"')
        logger.info("Sending " + dat2)
        #self.wfile.write(json.dumps(dat).encode())
        self.wfile.write(dat2.encode())
        
    # POST echoes the message adding a JSON field
    def do_POST(self):
        ctype, pdict = cgi.parse_header(self.headers.getheader('content-type'))
        
        # refuse to receive non-json content
        if ctype != 'application/json':
            self.send_response(400)
            self.end_headers()
            return
            
        # read the message and convert it into a python dictionary
        length = int(self.headers.getheader('content-length'))
        message = json.loads(self.rfile.read(length))
        
        # add a property to the object, just to mess with data
        message['received'] = 'ok'
        
        # send the message back
        self._set_headers()
        self.wfile.write(json.dumps(message))
        
def run(port=8001):
    server_address = ('', port)
    httpd = HTTPServer(server_address, Server)
    
    print(f'Starting httpd on port {port} ...')
    httpd.serve_forever()

# Ausführung des WebSocket-Clients
if __name__ == "__main__":
    #asyncio.run(volkszaehler_client())
    #start_server()
    threadvz = Thread(target = start_volkszaehler_client)
    print(f'start ws receiver')
    threadvz.start()
    #thread = Thread(target = start_server)
    print(f'start tcp server')
    #thread.start()
    run(server_port)
    threadvz.join()
