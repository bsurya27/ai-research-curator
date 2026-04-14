#!/bin/bash
set -e

PROJECT_DIR="/home/ec2-user/ai-research-curator"
cd $PROJECT_DIR

# Load env vars
export $(grep -v '^#' .env | xargs)

# Compress and upload ChromaDB to S3
CHROMA_DIR="$PROJECT_DIR/rec_model/data/chroma"
if [ -d "$CHROMA_DIR" ]; then
    echo "Backing up ChromaDB to S3..."
    tar -czf /tmp/chroma.tar.gz -C $PROJECT_DIR/rec_model/data/ chroma/
    aws s3 cp /tmp/chroma.tar.gz s3://$S3_BUCKET/chroma.tar.gz --region $AWS_REGION
    echo "ChromaDB backup complete."
else
    echo "No ChromaDB found, skipping backup."
fi

# Stop rec model
echo "Stopping rec model..."
pkill -f "python rec_model/app.py" || true

# Stop EC2 instance
echo "Stopping instance..."
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
aws ec2 stop-instances --instance-ids $INSTANCE_ID --region $AWS_REGION

echo "Done."
