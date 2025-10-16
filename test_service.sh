#!/bin/bash
# Test script for Example Receiver Service

echo "=== Example Receiver Service Test Script ==="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}1. Testing Health Endpoint${NC}"
curl -s http://localhost:8200/health | python3 -m json.tool
echo ""

echo -e "${BLUE}2. Testing UI Endpoint${NC}"
curl -s http://localhost:8200/ui
echo ""
echo ""

echo -e "${BLUE}3. Testing Files List Endpoint${NC}"
curl -s http://localhost:8200/api/files | python3 -m json.tool
echo ""

echo -e "${BLUE}4. Testing Single File Endpoint (File 1)${NC}"
curl -s http://localhost:8200/api/files/1 | python3 -m json.tool
echo ""

echo -e "${BLUE}5. Testing Non-existent File (should return 404)${NC}"
curl -s -w "\nHTTP Status: %{http_code}\n" http://localhost:8200/api/files/999
echo ""

echo -e "${BLUE}6. Checking Message Files on Disk${NC}"
ls -lh test_data/example_receiver/messages/
echo ""

echo -e "${BLUE}7. Showing Content of Batch 1${NC}"
cat test_data/example_receiver/messages/messages_batch_0001.txt
echo ""

echo -e "${GREEN}=== All Tests Complete ===${NC}"
