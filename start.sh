#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$SCRIPT_DIR"

source "$SCRIPT_DIR/common.sh"

SERVICE_NAME="Store"
PORT=8001
AUTH_DISABLED="false"

if [[ "$1" == "--no-auth" ]]; then
    AUTH_DISABLED="true"
    echo -e "${BLUE}Starting Store with AUTH_DISABLED=true${NC}"
else
    echo -e "${BLUE}Starting Store with authentication enabled${NC}"
fi

echo ""

################################################################################
# Validate environment
################################################################################

validate_poetry_env || exit 1
validate_cl_server_dir || exit 1

LOGS_DIR=$(ensure_logs_dir)

################################################################################
# Run DB migrations
################################################################################

run_migrations "$SERVICE_NAME" "$SERVICE_DIR"

################################################################################
# Start the service
################################################################################

print_header "Starting Store Service"

start_service "$SERVICE_NAME" "$SERVICE_DIR" "$PORT" "$AUTH_DISABLED"
echo -e "${YELLOW}[*] Store service stopped${NC}"
