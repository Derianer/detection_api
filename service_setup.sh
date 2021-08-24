#!/bin/bash

sudo chmod u+x tasks_manager.py start_worker.py
sudo cp ./systemd_services/{detection_server.service,detection_worker.service} /etc/systemd/system
sudo systemctl daemon-reload
sudo systemctl enable detection_server.service && sudo systemctl start detection_server.service
sudo systemctl enable detection_worker.service && sudo systemctl start detection_worker.service
