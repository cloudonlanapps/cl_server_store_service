#!/bin/bash

################################################################################
#                    CL Server - Start Store Service
################################################################################
#
# This script starts the Store service.
#
# Usage:
#   ./start.sh            # Start with authentication enabled
#   ./start.sh --no-auth  # Start with AUTH_DISABLED=true 
#
# Environment Variables (Required):
#   CL_VENV_DIR - Path to directory containing virtual environments
#   CL_SERVER_DIR - Path to data directory
#
# Service:
#   -  Store Service on port 8001
#
################################################################################

set -e

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="$SCRIPT_DIR"

# Source common utilities (local to this service)
source "$SCRIPT_DIR/common.sh"

# Service configuration
SERVICE_NAME="Store"
SERVICE_ENV_NAME="store"
PORT=8001
AUTH_DISABLED="false"

# Parse command line arguments
if [[ "$1" == "--no-auth" ]]; then
    AUTH_DISABLED="true"
    echo -e "${BLUE}Starting Store service with AUTH_DISABLED=true (no authentication required)${NC}"
else
    echo -e "${BLUE}Starting Store service WITH authentication enabled${NC}"
fi

echo ""

################################################################################
# Validate environment variables
################################################################################

echo "Validating environment variables..."
echo ""

if ! validate_venv_dir; then
    exit 1
fi

echo ""

if ! validate_cl_server_dir; then
    exit 1
fi

echo ""

# Ensure logs directory exists
LOGS_DIR=$(ensure_logs_dir)
if [ $? -ne 0 ]; then
    echo -e "${RED}[✗] Failed to create logs directory${NC}"
    exit 1
fi

echo ""

################################################################################
# Run Database Migrations
################################################################################

if ! run_migrations "$SERVICE_NAME" "$SERVICE_DIR" "$SERVICE_ENV_NAME"; then
    echo -e "${RED}[✗] Failed to run migrations${NC}"
    exit 1
fi

echo ""

################################################################################
# Start Media Store Service
################################################################################

print_header "Starting Store Service"

if start_service "$SERVICE_NAME" "$SERVICE_DIR" "$PORT" "$AUTH_DISABLED" "$SERVICE_ENV_NAME"; then
    # Service stopped normally
    echo ""
    echo -e "${YELLOW}[*] Store service stopped${NC}"
else
    # Service failed to start
    echo ""
    echo -e "${RED}[✗] Failed to start Store service${NC}"
    exit 1
fi

echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
