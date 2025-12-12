#!/bin/bash

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

################################################################################
# No venv validation needed — Poetry manages virtualenvs
################################################################################
validate_poetry_env() {
    if ! command -v poetry &> /dev/null; then
        echo -e "${RED}[✗] Poetry is not installed${NC}"
        return 1
    fi

    echo -e "${GREEN}[✓] Poetry detected${NC}"
    return 0
}

################################################################################
# Check port usage
################################################################################
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 ; then
        return 0
    else
        return 1
    fi
}

################################################################################
# Validate CL_SERVER_DIR
################################################################################
validate_cl_server_dir() {
    if [ -z "$CL_SERVER_DIR" ]; then
        echo -e "${RED}[✗] Error: CL_SERVER_DIR must be set${NC}"
        return 1
    fi

    mkdir -p "$CL_SERVER_DIR"

    if [ ! -w "$CL_SERVER_DIR" ]; then
        echo -e "${RED}[✗] No write permission for $CL_SERVER_DIR${NC}"
        return 1
    fi

    echo -e "${GREEN}[✓] CL_SERVER_DIR valid: $CL_SERVER_DIR${NC}"
    return 0
}

################################################################################
# Logs directory
################################################################################
ensure_logs_dir() {
    local logs_dir="$CL_SERVER_DIR/run_logs"
    mkdir -p "$logs_dir"
    echo "$logs_dir"
}

################################################################################
# Run Alembic migrations using Poetry
################################################################################
run_migrations() {
    local service_name=$1
    local service_path=$2

    echo -e "${BLUE}[*] Running migrations for ${service_name}...${NC}"

    if [ ! -f "$service_path/alembic.ini" ]; then
        echo -e "${YELLOW}[!] No alembic.ini found — skipping migrations${NC}"
        return 0
    fi

    if ! poetry run alembic upgrade head; then
        echo -e "${YELLOW}[!] Alembic migration warning${NC}"
        return 0
    fi

    echo -e "${GREEN}[✓] Migrations completed${NC}"
}

################################################################################
# Start service using Poetry virtualenv
################################################################################
start_service() {
    local service_name=$1
    local service_path=$2
    local port=$3
    local auth_disabled=$4

    echo -e "${BLUE}[*] Starting ${service_name}...${NC}"

    if check_port $port; then
        echo -e "${RED}[✗] Port $port is already in use${NC}"
        return 1
    fi

    echo -e "${GREEN}[✓] Starting on port $port${NC}"

    if [ "$auth_disabled" == "true" ]; then
        AUTH_DISABLED=true CL_SERVER_DIR="$CL_SERVER_DIR" \
            poetry run python -m store.main
    else
        CL_SERVER_DIR="$CL_SERVER_DIR" \
            poetry run python -m store.main
    fi

    return 0
}

################################################################################
# Pretty printing
################################################################################
print_header() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE} $1 ${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
}
