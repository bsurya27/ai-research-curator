#!/bin/bash
set -e

PROJECT_DIR="/home/ec2-user/ai-research-curator"
cd $PROJECT_DIR
chmod +x "$PROJECT_DIR/startup.sh" "$PROJECT_DIR/shutdown.sh"

# Load env vars
export $(grep -v '^#' .env | xargs)

# Restore ChromaDB from S3 if local copy doesn't exist
CHROMA_DIR="$PROJECT_DIR/rec_model/data/chroma"
if [ ! -d "$CHROMA_DIR" ]; then
    echo "ChromaDB not found locally, checking S3..."
    if aws s3 ls s3://$S3_BUCKET/chroma.tar.gz --region $AWS_REGION > /dev/null 2>&1; then
        echo "Restoring ChromaDB from S3..."
        aws s3 cp s3://$S3_BUCKET/chroma.tar.gz /tmp/chroma.tar.gz --region $AWS_REGION
        mkdir -p $PROJECT_DIR/rec_model/data
        tar -xzf /tmp/chroma.tar.gz -C $PROJECT_DIR/rec_model/data/
        echo "ChromaDB restored."
    else
        echo "No ChromaDB backup found in S3, starting fresh."
        mkdir -p $PROJECT_DIR/rec_model/data
    fi
fi

# Start rec model
source venv/bin/activate
echo "Starting rec model..."
nohup python rec_model/app.py > /tmp/rec_model.log 2>&1 &
REC_MODEL_PID=$!
echo "Rec model PID: $REC_MODEL_PID"

# Wait for rec model to be ready
echo "Waiting for rec model to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "Rec model is ready."
        break
    fi
    sleep 2
done

# Run curator
echo "Running curator..."
cd $PROJECT_DIR/curation_agent
python curator.py

echo "Curator run complete."

bash "$PROJECT_DIR/shutdown.sh"
