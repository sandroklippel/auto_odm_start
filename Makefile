APP=auto_odm_start_service
APP_DIR=dist
BUILD_FILES=__main__.py
BUILD_DIR=build
INSTALL_DIR=/usr/local/bin

app: $(BUILD_FILES)
	mkdir -p $(APP_DIR)
	rm -f "$(APP_DIR)/$(APP)"
	cp -p $(BUILD_FILES) build
	python3 -m zipapp -p "/usr/bin/env python3" -o "$(APP_DIR)/$(APP)" $(BUILD_DIR)

requirements: requirements.txt
	mkdir -p $(BUILD_DIR)
	python3 -m pip install -r requirements.txt --target $(BUILD_DIR)

install: $(APP_DIR)/$(APP)
	install -p "$(APP_DIR)/$(APP)" $(INSTALL_DIR)

uninstall: $(INSTALL_DIR)/$(APP)
	rm -f "$(INSTALL_DIR)/$(APP)"

service: auto_odm_start.service auto_odm_start.sh auto_odm_stop.sh
	install -p auto_odm_start.sh auto_odm_stop.sh $(INSTALL_DIR)
	cp auto_odm_start.service /etc/systemd/system
	systemctl daemon-reload
	systemctl enable auto_odm_start.service
	systemctl start auto_odm_start.service

rmservice:
	systemctl stop auto_odm_start.service
	systemctl disable auto_odm_start.service
	rm -rf /etc/systemd/system/auto_odm_start.service
	rm -rf "$(INSTALL_DIR)/auto_odm_start.sh"
	rm -rf "$(INSTALL_DIR)/auto_odm_stop.sh"
	systemctl daemon-reload