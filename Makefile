# Bibuntu — host theme + snap content package
THEME      := Bibuntu
SNAP_NAME  := icon-theme-bibuntu
BUILD_DIR  := build/$(THEME)

.PHONY: all build install install-system snap pack connect test test-sudo install-snap clean help

all: build

help:
	@echo "Targets:"
	@echo "  make build            Build theme into $(BUILD_DIR)"
	@echo "  make install          Build + install to ~/.local/share/icons + apply"
	@echo "  make install-system   Build + install to /usr/share/icons (sudo)"
	@echo "  make pack             Pack content snap via snap pack (no snapcraft)"
	@echo "  make snap             Prefer snapcraft; falls back to make pack"
	@echo "  make connect          Connect all snap apps to icon-theme-bibuntu"
	@echo "  make install-snap     Pack snap, install --dangerous, connect apps"
	@echo "  make test             Host + pack tests (no root)"
	@echo "  make test-sudo        Full test including snap install (password)"
	@echo "  make clean            Remove build artifacts and local snap tree"

build:
	python3 build_theme.py --no-install

install:
	./scripts/install.sh

install-system:
	./scripts/install.sh --system

pack: $(BUILD_DIR)
	./scripts/pack-snap.sh --no-build

snap: $(BUILD_DIR)
	@if command -v snapcraft >/dev/null 2>&1; then \
	  echo "Using snapcraft…"; \
	  snapcraft pack --destructive-mode || snapcraft pack || snapcraft; \
	else \
	  echo "snapcraft not installed; packing with snap pack"; \
	  ./scripts/pack-snap.sh --no-build; \
	fi

$(BUILD_DIR):
	python3 build_theme.py --no-install

connect:
	./scripts/connect-snap-apps.sh $(SNAP_NAME)

test:
	./scripts/test-local.sh

test-sudo:
	./scripts/test-local.sh --sudo

install-snap: pack
	@snap_file=$$(ls -1t $(SNAP_NAME)_*.snap | head -1); \
	echo "Installing $$snap_file"; \
	sudo snap install --dangerous "$$snap_file"; \
	./scripts/connect-snap-apps.sh $(SNAP_NAME)

clean:
	rm -rf build prime stage parts $(SNAP_NAME)_*.snap
	rm -rf .snapcraft snap/.snapcraft
