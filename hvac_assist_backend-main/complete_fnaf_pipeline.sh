#!/bin/bash
# ============================================================================
# COMPLETE PIPELINE FOR NEW CSV DATA
# ============================================================================
# This script performs the complete data pipeline for NEW CSV data:
# - Imports CSV data into Movie table (appends to existing data)
# - Populates analytics tables (FilmPerformanceSummary, TheaterPerformance, etc.)
# - Calculates performance metrics (DIR, DBR, DoD, etc.)
# - Creates embeddings ONLY from the new CSV data (not existing database records)
# - Uploads embeddings to Pinecone
#
# USAGE:
# To use with a different CSV file, simply change the CSV_PATH variable below.
# The pipeline will:
# 1. Import the CSV data into the database (appending to existing data)
# 2. Process ONLY the movies from this CSV for embeddings (ignoring existing data)
# 3. Upload embeddings to Pinecone
#
# This ensures that existing database records are not reprocessed.
# ============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CSV_PATH="/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/five_nights_at_freddy_data.csv"
PROJECT_DIR="/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main"
CHUNK_SIZE=50000
BULK_SIZE=1000
CHECKPOINT_INTERVAL=2
PARALLEL_THREADS=8
EMBEDDING_BATCH_SIZE=512

echo -e "${BLUE}============================================================================${NC}"
echo -e "${BLUE}🚀 COMPLETE PIPELINE FOR NEW CSV DATA${NC}"
echo -e "${BLUE}============================================================================${NC}"
echo ""
echo -e "${GREEN}📁 CSV File:${NC} $CSV_PATH"
echo -e "${GREEN}📂 Project Directory:${NC} $PROJECT_DIR"
echo ""

# Navigate to project directory
cd "$PROJECT_DIR" || exit 1

# ============================================================================
# STEP 1: Import CSV Data into Movie Table and Analytics Tables
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}📋 STEP 1: Importing CSV data into Movie table and analytics tables...${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if [ ! -f "$CSV_PATH" ]; then
    echo -e "${RED}❌ ERROR: CSV file not found: $CSV_PATH${NC}"
    exit 1
fi

echo -e "${GREEN}📊 This will populate:${NC}"
echo "   • Movie table (all showtime records)"
echo "   • FilmPerformanceSummary (movie performance metrics)"
echo "   • TheaterPerformance (theater-level metrics)"
echo "   • MarketAnalysis (market analysis data)"
echo "   • ComparativeAnalysis (comparative analysis)"
echo ""

python3 manage.py bulk_import_movies \
    --csv-path "$CSV_PATH" \
    --analytics-tables \
    --chunk-size "$CHUNK_SIZE" \
    --bulk-size "$BULK_SIZE" \
    --checkpoint-interval "$CHECKPOINT_INTERVAL" \
    --clear-checkpoints

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ STEP 1 FAILED: CSV import failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ STEP 1 COMPLETE: Data imported successfully${NC}"
echo ""

# ============================================================================
# STEP 2: Calculate Performance Metrics
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}📋 STEP 2: Calculating performance metrics (DIR, DBR, DoD, etc.)...${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${GREEN}📊 This will pre-calculate:${NC}"
echo "   • DIR (Days In Release) values"
echo "   • DBR (Days Before Release) values"
echo "   • DoD (Day-over-Day) growth metrics"
echo "   • Performance metrics for fast analytics queries"
echo ""

python3 manage.py calculate_performance_metrics \
    --all \
    --batch-size 10000

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ STEP 2 FAILED: Performance metrics calculation failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ STEP 2 COMPLETE: Performance metrics calculated${NC}"
echo ""

# ============================================================================
# STEP 3: Create Embeddings and Upload to Pinecone
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}📋 STEP 3: Creating embeddings and uploading to Pinecone...${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo -e "${GREEN}📊 This will:${NC}"
echo "   • Process ONLY movies from the CSV file (not existing database records)"
echo "   • Generate embeddings from new CSV movie data using sentence transformers"
echo "   • Create vector representations for RAG (Retrieval Augmented Generation)"
echo "   • Upload embeddings to Pinecone vector database"
echo "   • Enable chatbot to answer questions about the new data"
echo ""

echo -e "${YELLOW}⏳ This step may take a while depending on data size...${NC}"
echo ""

python3 manage.py run_entelligence_pipeline \
    --parallel \
    --chunk-size "$CHUNK_SIZE" \
    --threads "$PARALLEL_THREADS" \
    --batch-size "$EMBEDDING_BATCH_SIZE" \
    --csv-path "$CSV_PATH"

if [ $? -ne 0 ]; then
    echo -e "${RED}❌ STEP 3 FAILED: Embedding pipeline failed${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ STEP 3 COMPLETE: Embeddings created and uploaded to Pinecone${NC}"
echo ""

# ============================================================================
# FINAL SUMMARY
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}🎉 PIPELINE COMPLETE!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${GREEN}✅ All steps completed successfully:${NC}"
echo "   1. ✅ CSV data imported into Movie table"
echo "   2. ✅ Analytics tables populated"
echo "   3. ✅ Performance metrics calculated"
echo "   4. ✅ Embeddings created and uploaded to Pinecone"
echo ""
echo -e "${GREEN}🚀 Your chatbot is now ready to handle queries about the new CSV data!${NC}"
echo ""
echo -e "${YELLOW}💡 You can now:${NC}"
echo "   • Query the chatbot about movies from the CSV"
echo "   • Ask for comp titles, performance analysis, etc."
echo "   • Use all chatbot features with the new data"
echo ""
echo -e "${YELLOW}📝 To process a different CSV file:${NC}"
echo "   • Edit this script and change the CSV_PATH variable at the top"
echo "   • Run the script again - it will process only the new CSV data"
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}📊 VERIFICATION (Optional)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${GREEN}To verify the import, you can run:${NC}"
echo ""
echo "  python3 manage.py shell"
echo "  >>> from movies.models import Movie"
echo "  >>> Movie.objects.filter(title__icontains='<your_movie_title>').count()"
echo ""
echo -e "${GREEN}🎉 All done! Pipeline completed successfully.${NC}"
echo ""

