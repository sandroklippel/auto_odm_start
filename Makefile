APP=auto_odm_start
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