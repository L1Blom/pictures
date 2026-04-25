docker exec -it -u root 88 bash -c "curl -sS https://bootstrap.pypa.io/get-pip.py | python3 --break-system-pacdocker exec -it -u root ef bash -c "curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py && python3 /tmp/get-pip.py --break-system-packages"ages"
docker exec -it -u root 88 bash -c "curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py && python3 /tmp/get-pip.py --break-system-packages"
docker exec -it -u root 88 bash -c "cd /projects/pictures && pip3 install -r requirements.txt --break-system-packages"
docker exec -it 88 bash -c "pip install PyYAML --break-system-packages 2>&1" 2>&1 
docker exec -it 88 bash -c "cd /projects/pictures && pip install -e . --break-system-packages 2>&1" 2>&1
