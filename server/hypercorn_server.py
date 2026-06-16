# SPDX-License-Identifier: GPL-3.0-or-later
# MATGen - Mobile Application Traffic Generator
# Copyright (C) 2022  RomARS (Mattia Quadrini) — original FWTG framework
# Copyright (C) 2026  Md Tariqul Islam
# See LICENSE for full terms
import os
import random
import trio
import string
import sys
import time
import logging
from hypercorn.trio import serve
from hypercorn.config import Config
from quart_trio import QuartTrio
from quart import request, Response
from starlette.exceptions import HTTPException

# get current directory
current_dir = os.getcwd()
print(current_dir)

# check if the server IP, port number and connection type are provided
if len(sys.argv) != 5:
    print("Missing Server IP, Port Number, Connection Type (HTTP/HTTPS), and Output Path")
    sys.exit()

# get the server IP, port number and connection type
server_ip = str(sys.argv[1])
server_port = int(sys.argv[2])
connection_type = str(sys.argv[3])
output_path = str(sys.argv[4])

os.makedirs(output_path, exist_ok=True)

logging.basicConfig(filename=os.path.join(output_path, "server.log"),
                    level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


# create a new Quart app instance
app = QuartTrio(__name__)


# define a route for the GET method
@app.route('/', methods=['GET'])
# define a function to handle the GET request
async def get_data():
    # get the size query parameter
    data_size = request.args.get('size', 0)

    # if the size query parameter is not provided, raise an error
    try:
        data_size = int(data_size)
    except ValueError:
        logging.error("Bad Request")
        raise HTTPException(status_code=400, detail="Bad Request")

    # if the size query parameter is less than or equal to 0, raise an error
    if data_size <= 0:
        logging.error("Bad Request")  #
        raise HTTPException(status_code=400, detail="Bad Request")

    # generate a random string of 1000 characters
    random_string = ''.join(
        random.choice(string.ascii_lowercase + string.punctuation +
                      string.digits) for _ in range(1000))

    #  generate a message of the given size by repeating the random string
    message = ''.join(random_string for _ in range(int(data_size)))
    # message = ''.join(
    #     random.choice(string.ascii_lowercase + string.punctuation +
    #                   string.digits) for _ in range(data_size))

    # encode the message to utf-8
    body = message.encode("utf-8")
    # print(f"data send by server = {len(message)} KB")

    # return response including status code, content length and content type headers
    return Response(body,
                    status=200,
                    headers={
                        'content-type': 'text/plain',
                        'content-length': str(len(message))
                    })


# define a route for the POST method
@app.route('/', methods=['POST'])
# define a function to handle the POST request
async def post_data():
    # get the content text file which send after encoding to utf-8
    # decode the content to utf-8
    content = (await request.data).decode('utf-8')
    response = content.encode('utf-8')  # encode the content to utf-8
    # the there is no content, raise an error
    if not content:
        logging.error("Bad Request")
        raise HTTPException(status_code=400, detail="Bad Request")

    # return response including status code, content length and content type headers
    return Response(response,
                    status=200,
                    headers={
                        'content-type': 'text/plain',
                        'content-length': str(len(content))
                    })


# Error handler for HTTPException
@app.errorhandler(HTTPException)
# define a function to handle the HTTPException
async def handle_http_exception(error):
    return error.detail, error.status_code

# create a new Config instance
config = Config()

try:
    if connection_type == "HTTP" or connection_type == "HTTPS":
        config.bind = [f"{server_ip}:{server_port}"]
        config.http_version = "2" if connection_type == "HTTPS" else "1.1"

    elif connection_type == "QUIC":
        config.quic_bind = [f"{server_ip}:{server_port}"]
except Exception as error:
    logging.exception(f"Error in configuring server: {error}")

try:
    # enable ssl if the connection type is HTTPS or QUIC
    if connection_type == "HTTPS" or connection_type == "QUIC":
        config.certfile = f"{current_dir}/cert/tcp/cert.pem"
        config.keyfile = f"{current_dir}/cert/tcp/key.pem"


except Exception as error:
    logging.exception(f"Error in configuring ssl: {error}")

# run the server and print server start time and closing time
try:
    logging.info(time.asctime() +
                 f" Server Starts - {server_ip}, {server_port}")
    trio.run(serve, app, config)  # run the server
    logging.info(time.asctime() +
                 f"Server Closes - {server_ip}, {server_port}")
except Exception as error:
    logging.exception(f"Error in Server: {error}")
