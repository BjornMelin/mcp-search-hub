#!/bin/bash
# Script to validate Docker setup for MCP Search Hub

# Text colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print header
echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}MCP Search Hub Docker Validator${NC}"
echo -e "${BLUE}================================${NC}"
echo ""

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if a file exists
file_exists() {
    [ -f "$1" ]
}

# Check if Docker is installed
echo -e "${BLUE}Checking Docker installation...${NC}"
if command_exists docker; then
    DOCKER_VERSION=$(docker --version)
    echo -e "${GREEN}✓ Docker is installed: ${DOCKER_VERSION}${NC}"
else
    echo -e "${RED}✗ Docker is not installed. Please install Docker first.${NC}"
    echo "Visit https://docs.docker.com/get-docker/ for installation instructions."
    exit 1
fi

# Check if Docker Compose is installed
echo -e "\n${BLUE}Checking Docker Compose installation...${NC}"
if command_exists docker-compose; then
    COMPOSE_VERSION=$(docker-compose --version)
    echo -e "${GREEN}✓ Docker Compose is installed: ${COMPOSE_VERSION}${NC}"
elif docker compose version >/dev/null 2>&1; then
    COMPOSE_VERSION=$(docker compose version)
    echo -e "${GREEN}✓ Docker Compose V2 is installed: ${COMPOSE_VERSION}${NC}"
else
    echo -e "${RED}✗ Docker Compose is not installed. Please install Docker Compose first.${NC}"
    echo "Visit https://docs.docker.com/compose/install/ for installation instructions."
    exit 1
fi

# Check if we're in the right directory
echo -e "\n${BLUE}Checking project files...${NC}"
if file_exists "Dockerfile" && file_exists "docker-compose.yml"; then
    echo -e "${GREEN}✓ Project files found${NC}"
else
    echo -e "${RED}✗ Dockerfile or docker-compose.yml not found.${NC}"
    echo "Make sure you're running this script from the project root directory."
    exit 1
fi

# Check environment files
echo -e "\n${BLUE}Checking environment configuration...${NC}"
if file_exists ".env"; then
    echo -e "${GREEN}✓ .env file found${NC}"
else
    echo -e "${YELLOW}! .env file not found. Creating from example...${NC}"
    if file_exists ".env.example"; then
        cp .env.example .env
        echo -e "${GREEN}✓ Created .env from example file${NC}"
        echo -e "${YELLOW}! Please edit .env to set your API keys and other configuration${NC}"
    else
        echo -e "${RED}✗ .env.example file not found. Cannot create .env file.${NC}"
        exit 1
    fi
fi

# Check required API keys
echo -e "\n${BLUE}Checking API keys in .env file...${NC}"
MISSING_KEYS=0
for KEY in FIRECRAWL_API_KEY EXA_API_KEY PERPLEXITY_API_KEY LINKUP_API_KEY TAVILY_API_KEY; do
    VALUE=$(grep -E "^$KEY=" .env | cut -d= -f2)
    if [ -z "$VALUE" ] || [ "$VALUE" == "fc_api_key_xxxxx" ] || [ "$VALUE" == "exa_api_key_xxxxx" ] || [ "$VALUE" == "pplx-xxxxxx" ] || [ "$VALUE" == "lp_xxxxxxxx" ] || [ "$VALUE" == "tvly-xxxxxxxx" ]; then
        echo -e "${YELLOW}! $KEY is not set or contains example value${NC}"
        MISSING_KEYS=$((MISSING_KEYS+1))
    else
        echo -e "${GREEN}✓ $KEY is set${NC}"
    fi
done

if [ $MISSING_KEYS -gt 0 ]; then
    echo -e "${YELLOW}! Some API keys are missing or using example values.${NC}"
    echo -e "${YELLOW}! You should update these in your .env file before proceeding.${NC}"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Attempt to build the Docker image
echo -e "\n${BLUE}Building Docker image...${NC}"
if docker build --target builder -t mcp-search-hub:builder . --pull; then
    echo -e "${GREEN}✓ Successfully built builder image${NC}"
else
    echo -e "${RED}✗ Failed to build Docker image${NC}"
    exit 1
fi

if docker build --target runtime -t mcp-search-hub:runtime . --pull; then
    echo -e "${GREEN}✓ Successfully built runtime image${NC}"
else
    echo -e "${RED}✗ Failed to build runtime Docker image${NC}"
    exit 1
fi

# Let user pick an environment
echo -e "\n${BLUE}Select environment to start:${NC}"
echo "1) Development (docker-compose.dev.yml)"
echo "2) Production (docker-compose.prod.yml)"
echo "3) Default (docker-compose.yml)"
read -p "Enter choice [3]: " choice
choice=${choice:-3}

case $choice in
    1)
        COMPOSE_FILE="docker-compose.dev.yml"
        ENV_TYPE="development"
        ;;
    2)
        COMPOSE_FILE="docker-compose.prod.yml"
        ENV_TYPE="production"
        ;;
    3)
        COMPOSE_FILE="docker-compose.yml"
        ENV_TYPE="default"
        ;;
    *)
        echo -e "${RED}Invalid choice. Using default.${NC}"
        COMPOSE_FILE="docker-compose.yml"
        ENV_TYPE="default"
        ;;
esac

# Start the containers
echo -e "\n${BLUE}Starting containers with $ENV_TYPE environment...${NC}"
if [ "$choice" -eq 3 ]; then
    if docker-compose up -d; then
        echo -e "${GREEN}✓ Containers started successfully${NC}"
    else
        echo -e "${RED}✗ Failed to start containers${NC}"
        exit 1
    fi
else
    if docker-compose -f $COMPOSE_FILE up -d; then
        echo -e "${GREEN}✓ Containers started successfully${NC}"
    else
        echo -e "${RED}✗ Failed to start containers${NC}"
        exit 1
    fi
fi

# Wait for the container to be healthy
echo -e "\n${BLUE}Waiting for containers to be healthy...${NC}"
CONTAINER_NAME=$(docker-compose ps -q mcp-search-hub)
MAX_ATTEMPTS=12
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    HEALTH=$(docker inspect --format='{{.State.Health.Status}}' $CONTAINER_NAME 2>/dev/null)
    
    if [ "$HEALTH" = "healthy" ]; then
        echo -e "${GREEN}✓ Container is healthy${NC}"
        break
    elif [ "$HEALTH" = "unhealthy" ]; then
        echo -e "${RED}✗ Container is unhealthy${NC}"
        docker logs $CONTAINER_NAME
        echo -e "${RED}Container failed health check. See logs above for details.${NC}"
        exit 1
    fi
    
    ATTEMPT=$((ATTEMPT+1))
    echo -e "${YELLOW}! Waiting for container to be healthy (attempt $ATTEMPT/$MAX_ATTEMPTS)...${NC}"
    sleep 5
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo -e "${RED}✗ Container did not become healthy in time${NC}"
    docker logs $CONTAINER_NAME
    echo -e "${RED}Container failed to start properly. See logs above for details.${NC}"
    exit 1
fi

# Test the API
echo -e "\n${BLUE}Testing the API...${NC}"
if curl -s http://localhost:8000/health > /dev/null; then
    echo -e "${GREEN}✓ Health endpoint is responding${NC}"
    
    # Get health status
    HEALTH_STATUS=$(curl -s http://localhost:8000/health)
    echo -e "${BLUE}Health status:${NC}"
    echo $HEALTH_STATUS | python -m json.tool
else
    echo -e "${RED}✗ Health endpoint is not responding${NC}"
    docker logs $CONTAINER_NAME
    echo -e "${RED}API is not responding. See logs above for details.${NC}"
    exit 1
fi

# Display container info
echo -e "\n${BLUE}Container information:${NC}"
docker ps --filter "name=mcp-search-hub"

# Success message
echo -e "\n${GREEN}===============================================${NC}"
echo -e "${GREEN}Docker setup validated and containers running!${NC}"
echo -e "${GREEN}===============================================${NC}"
echo -e "${BLUE}API URL: http://localhost:8000${NC}"
echo -e "${BLUE}Health check: http://localhost:8000/health${NC}"
echo -e "${BLUE}Metrics: http://localhost:8000/metrics${NC}"

# Optional cleanup
echo -e "\n${BLUE}Do you want to stop the containers now?${NC}"
read -p "Stop containers? (y/n) [n]: " stop_choice
stop_choice=${stop_choice:-n}

if [[ $stop_choice =~ ^[Yy]$ ]]; then
    if [ "$choice" -eq 3 ]; then
        docker-compose down
    else
        docker-compose -f $COMPOSE_FILE down
    fi
    echo -e "${GREEN}✓ Containers stopped${NC}"
else
    echo -e "${GREEN}✓ Containers left running${NC}"
fi

echo -e "\n${BLUE}Done!${NC}"

