from pathlib import Path
from checklib import *
import requests
import random
import string

BASE_DIR = Path(__file__).absolute().resolve().parent

PORT = 6060
TIMEOUT = 20
LLM_TIMEOUT = 30

class CheckMachine:

    def __init__(self, checker):
        self.checker = checker

    def ping(self):
        username = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        headers = {"Content-Type": "application/json"}

        r = requests.post(f'http://{self.checker.host}:{PORT}/api/auth/register', timeout=TIMEOUT, headers=headers, json={"username": username, "password": password})
        if r.status_code != 200:
            print("ERR on register")
            print(r.text)
            return 'Check failed'

        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        caps_name = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        caps_code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

        r = requests.post(f'http://{self.checker.host}:{PORT}/api/chatbot/process', timeout=LLM_TIMEOUT, headers=headers, json={"message": f"зарегистрируй капсулу {caps_name} с кодом {caps_code}"})
        if r.status_code != 200:
            print("ERR on chatbot process")
            print(r.text)
            return 'Check failed'

        temp = random.uniform(15.0, 30.0)
        oxyl = random.uniform(80.0, 100.0)
        stat = "день" if random.randint(0, 1) == 0 else "ночь"

        r = requests.post(f'http://{self.checker.host}:{PORT}/api/chatbot/process', timeout=LLM_TIMEOUT, headers=headers, json={"message": f"измени параметры у капсулы с именем {caps_name}: температура {temp}, уровень кислорода {oxyl}, режим {stat}. Код доступа {caps_code}"})
        if r.status_code != 200:
            print("ERR on chatbot process")
            print(r.text)
            return 'Check failed'

        r = requests.get(f'http://{self.checker.host}:{PORT}/api/capsule', timeout=TIMEOUT, headers=headers)
        if r.status_code != 200:
            print("ERR on get capsule")
            print(r.text)
            return 'Check failed'

        capsules = r.json()
        checked = False

        for c in capsules:
            if c["name"] == caps_name:
                if c["temperature"] == temp and c["oxygen_level"] == oxyl:
                    checked = True
                break

        if not checked:
            return 'Check failed'

    def put_flag(self, flag):
        user_pass = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        headers = {"Content-Type": "application/json"}

        r = requests.post(f'http://{self.checker.host}:{PORT}/api/auth/register', timeout=TIMEOUT, headers=headers, json={"username": user_pass, "password": f"pass_{user_pass}_pass"})
        if r.status_code != 200:
            print("ERR on register")
            print(r.text)
            return 'Could not put flag'

        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        caps_name = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
        caps_code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

        r = requests.post(f'http://{self.checker.host}:{PORT}/api/capsule', timeout=TIMEOUT, headers=headers, json={"name": caps_name, "access_code": caps_code})
        if r.status_code != 200:
            print("ERR on post main capsule")
            print(r.text)
            return 'Could not put flag'

        main_caps_id = r.json()["id"]
        clus_name = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

        r = requests.post(f'http://{self.checker.host}:{PORT}/api/capsule/{main_caps_id}/cluster-key', timeout=TIMEOUT, headers=headers, json={"cluster_name": clus_name, "cluster_key": flag, "access_code": caps_code})
        if r.status_code != 200:
            print("ERR on post cluster")
            print(r.text)
            return 'Could not put flag'

        r = requests.get(f'http://{self.checker.host}:{PORT}/api/cluster', timeout=TIMEOUT, headers=headers)
        if r.status_code != 200:
            print("ERR on get cluster")
            print(r.text)
            return 'Could not put flag'

        clusters = r.json()
        is_checked = False

        for c in clusters:
            if c["name"] == clus_name:
                is_checked = True
                break

        if not is_checked:
            print("ERR on find cluster")
            print(r.text)
            return 'Could not put flag'

        r = requests.post(f'http://{self.checker.host}:{PORT}/api/capsule', timeout=TIMEOUT, headers=headers, json={"name": f"{caps_name}_2", "access_code": caps_code})
        if r.status_code != 200:
            print("ERR on post guest capsule")
            print(r.text)
            return 'Could not put flag'

        guest_caps_id = r.json()["id"]

        r = requests.post(f'http://{self.checker.host}:{PORT}/api/capsule/{guest_caps_id}/cluster/join', timeout=TIMEOUT, headers=headers, json={"cluster_name": clus_name, "access_code": caps_code})
        if r.status_code != 200:
            print("ERR on join cluster")
            print(r.text)
            return 'Could not put flag'

        r = requests.post(f'http://{self.checker.host}:{PORT}/api/cluster-requests/{caps_name}/approve/{caps_name}_2', timeout=TIMEOUT, headers=headers, json={"access_code": caps_code})
        if r.status_code != 200:
            print("ERR on approve")
            print(r.text)
            return 'Could not put flag'

        return f"{user_pass}:{main_caps_id}:{caps_code}"

    def get_flag(self, flag_id):
        flag_id = flag_id.split(':')
        user_pass, caps_id, caps_code = flag_id[0], flag_id[1], flag_id[2]
        headers = {"Content-Type": "application/json"}

        r = requests.post(f'http://{self.checker.host}:{PORT}/api/auth/login', timeout=TIMEOUT, headers=headers, json={"username": user_pass, "password": f"pass_{user_pass}_pass"})
        if r.status_code != 200:
            print("ERR on login")
            print(r.text)
            return 'Could not get flag'

        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        r = requests.get(f'http://{self.checker.host}:{PORT}/api/capsule/{caps_id}/cluster/requests', timeout=TIMEOUT, headers=headers)
        if r.status_code != 200:
            print("ERR on get requests")
            print(r.text)
            return 'Could not get flag'

        reqs = r.json()

        for req in reqs:
            r = requests.post(f'http://{self.checker.host}:{PORT}/api/cluster-requests/{req["receiver_capsule_name"]}/reject/{req["sender_capsule_name"]}', timeout=TIMEOUT, headers=headers, json={"access_code": caps_code})
            if r.status_code != 200 and r.status_code != 404:
                print("ERR on reject")
                print(r.text)
                return 'Could not get flag'

        r = requests.get(f'http://{self.checker.host}:{PORT}/api/capsule/{caps_id}/cluster', timeout=TIMEOUT, headers=headers)
        if r.status_code != 200:
            print("ERR on get cluster")
            print(r.text)
            return 'Could not get flag'

        jr = r.json()

        if "cluster_key" in jr:
            return jr["cluster_key"]
                        
        return 'Could not get flag'