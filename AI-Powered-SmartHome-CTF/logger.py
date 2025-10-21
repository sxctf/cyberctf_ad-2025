import logging as log
import json 

# pip install python-json-logger

log.basicConfig(filename='./logs/app.log', level=log.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Event Code 
# 1100 - Request
# 1101 - Request Error
# 1102 - Multirow request
# 1103 - Append Ship
# 1104 - Exception


global loga
loga = '''{{"event_code" : "{event}", 
            "agent" : 
            {{"ip" : "0.0.0.0", "name": "SmartHome", "id" : "000"}}, 
            "data": {{"app_proto": "http", 
            "src_ip": "{ip}", 
            "src_port": "{port}", 
            "dest_port": "5500", 
            "event_timestamp" : "{time}"}}, 
            "http": {{"hostname": "{hostname}", 
            "protocol": "{protocol}", 
            "http_method": "{http_method}", 
            "payload" : ["{payload}"], 
            "url": "{url}", 
            "http_user_agent": "{http_user_agent}", 
            "status": "{status}"}}, 
            "err_message" : "{error}", 
            "ex_text" : "{ex_text}"}}'''

def start_page(flag, params):
    output = loga.format(event=params[0], ip=params[1], port=params[2], time=params[3], hostname=params[4], protocol=params[5],
                           http_method=params[6], payload=params[8], url=params[7], http_user_agent=params[9], status=params[10], error=params[11], ex_text = params[12])
    if flag:
        log.info(output)
    else:
        log.error(output)