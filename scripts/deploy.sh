#!/bin/bash
# LunatiX Deployment Script for Google Cloud
# This script sets up all required infrastructure and deploys the application

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
REGION="europe-west1"
SEARCH_LOCATION="eu"
SERVICE_NAME="lunatix-backend"
DATASTORE_ID="lunatix-insurance-docs"
ENGINE_ID="lunatix-search-engine"

# Check if PROJECT_ID is set
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}ERROR: PROJECT_ID environment variable is not set${NC}"
    echo "Please run: export PROJECT_ID=your-project-id"
    exit 1
fi

echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  LunatiX Deployment Script${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
echo -e "Project ID: ${YELLOW}$PROJECT_ID${NC}"
echo -e "Region: ${YELLOW}$REGION${NC}"
echo -e "Search Location: ${YELLOW}$SEARCH_LOCATION${NC}"
echo ""

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"
if ! command_exists gcloud; then
    echo -e "${RED}ERROR: gcloud CLI is not installed${NC}"
    exit 1
fi

if ! command_exists python3; then
    echo -e "${RED}ERROR: python3 is not installed${NC}"
    exit 1
fi

# Set the project
echo -e "${YELLOW}Setting project...${NC}"
gcloud config set project $PROJECT_ID

# Enable required APIs
echo -e "${YELLOW}Enabling required APIs...${NC}"
gcloud services enable \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    aiplatform.googleapis.com \
    storage.googleapis.com \
    discoveryengine.googleapis.com \
    secretmanager.googleapis.com

# Create Artifact Registry repository
echo -e "${YELLOW}Creating Artifact Registry repository...${NC}"
gcloud artifacts repositories create lunatix \
    --repository-format=docker \
    --location=$REGION \
    --description="LunatiX container images" \
    2>/dev/null || echo "Repository already exists"

# Create GCS bucket for documents (EU location)
echo -e "${YELLOW}Creating GCS bucket for documents...${NC}"
BUCKET_NAME="${PROJECT_ID}-lunatix-documents"
gsutil mb -l EU gs://$BUCKET_NAME 2>/dev/null || echo "Bucket already exists"

# Set bucket lifecycle (optional: auto-delete old files)
cat > /tmp/lifecycle.json << EOF
{
  "rule": [
    {
      "action": {"type": "Delete"},
      "condition": {"age": 365}
    }
  ]
}
EOF
gsutil lifecycle set /tmp/lifecycle.json gs://$BUCKET_NAME
rm /tmp/lifecycle.json

# Create service account
echo -e "${YELLOW}Creating service account...${NC}"
SA_NAME="lunatix-backend-sa"
SA_EMAIL="$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

gcloud iam service-accounts create $SA_NAME \
    --display-name="LunatiX Backend Service Account" \
    2>/dev/null || echo "Service account already exists"

# Grant required roles to service account
echo -e "${YELLOW}Granting IAM roles...${NC}"
ROLES=(
    "roles/aiplatform.user"
    "roles/storage.admin"
    "roles/discoveryengine.editor"
    "roles/secretmanager.secretAccessor"
)

for ROLE in "${ROLES[@]}"; do
    gcloud projects add-iam-policy-binding $PROJECT_ID \
        --member="serviceAccount:$SA_EMAIL" \
        --role="$ROLE" \
        --quiet
done

# Create secrets
echo -e "${YELLOW}Creating secrets...${NC}"

# Generate a random secret key if not provided
if [ -z "$SECRET_KEY" ]; then
    SECRET_KEY=$(openssl rand -base64 32)
fi

# Create secret-key secret
echo -n "$SECRET_KEY" | gcloud secrets create secret-key \
    --data-file=- \
    --replication-policy="user-managed" \
    --locations="europe-west1" \
    2>/dev/null || echo "Secret 'secret-key' already exists"

# Create database-url secret (SQLite for demo, replace with Cloud SQL in production)
echo -n "sqlite:///./insurance.db" | gcloud secrets create database-url \
    --data-file=- \
    --replication-policy="user-managed" \
    --locations="europe-west1" \
    2>/dev/null || echo "Secret 'database-url' already exists"

# Set up Vertex AI Search
echo -e "${YELLOW}Setting up Vertex AI Search infrastructure...${NC}"
python3 scripts/setup_vertex_search.py \
    --project-id $PROJECT_ID \
    --location $SEARCH_LOCATION \
    --datastore-id $DATASTORE_ID \
    --engine-id $ENGINE_ID

# Build and deploy
echo -e "${YELLOW}Building and deploying to Cloud Run...${NC}"
gcloud builds submit \
    --config cloudbuild.yaml \
    --substitutions=_REGION=$REGION

# Get the service URL
echo -e "${GREEN}======================================${NC}"
echo -e "${GREEN}  Deployment Complete!${NC}"
echo -e "${GREEN}======================================${NC}"
echo ""
SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')
echo -e "Service URL: ${YELLOW}$SERVICE_URL${NC}"
echo ""
echo "Next steps:"
echo "1. Update your frontend to use the service URL"
echo "2. Configure CORS origins in Cloud Run environment variables"
echo "3. Set up a custom domain (optional)"
echo "4. Enable Access Transparency for audit logging (recommended)"
echo ""
echo -e "${YELLOW}Important: For production, replace SQLite with Cloud SQL${NC}"
