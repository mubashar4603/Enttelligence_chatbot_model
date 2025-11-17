#!/usr/bin/env python3
"""
Create Pinecone embeddings for AI_Data_Dump_All_Titles daily performance data.

Purpose
-------
The main Entelligence embedding pipelines work from the raw `Movie` table
and have already populated Pinecone for a small set of titles like:
Twisters, Dune: Part Two, Homestead, Joker, Monkey Man, and
Five Nights at Freddy's 2.

This command adds *additional* vectors for titles that only exist in the
AI_Data_Dump CSV, without touching or resetting the existing index.

Strategy
--------
* Read the aggregated CSV: AI_Data_Dump_All_Titles - AI_Data_Dump_All_Titles.csv
* Identify unique titles that are NOT already present in the `Movie` table.
* For each title, build a compact text summary from the CSV fields
  (studio, genre, rating, DBR/Running Date window, cumulative revenue).
* Embed that summary with the same SentenceTransformer model used elsewhere.
* Upsert one vector per title to the existing Pinecone index.

Notes
-----
* This does **not** delete any vectors or reset the index.
* Existing titles that already have rich showtime-level embeddings are skipped.
"""

from django.core.management.base import BaseCommand
from django.conf import settings

from pinecone import Pinecone
from sentence_transformers import SentenceTransformer

from movies.models import Movie

import pandas as pd
import numpy as np
from pathlib import Path
import logging
import time
import re
import unicodedata


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Embed AI_Data_Dump_All_Titles CSV titles into Pinecone as lightweight "
        "daily-performance vectors, without touching existing vectors."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv-path",
            type=str,
            default="/home/ec2-user/Enttelligence_chatbot_model/hvac_assist_backend-main/AI_Data_Dump_All_Titles - AI_Data_Dump_All_Titles.csv",
            help="Path to AI_Data_Dump_All_Titles CSV",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=256,
            help="Embedding batch size (default: 256)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Optional limit on number of new titles to embed (for testing)",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        batch_size = int(options["batch_size"])
        limit = options["limit"]

        self.stdout.write(self.style.SUCCESS("🚀 Starting AI daily-performance embedding pipeline"))
        self.stdout.write(f"   CSV path: {csv_path}")

        if not csv_path.exists():
            self.stdout.write(self.style.ERROR(f"   ✗ CSV file not found: {csv_path}"))
            return

        # 1) Load unique titles from CSV
        self.stdout.write("📖 Loading titles from CSV...")
        df = pd.read_csv(
            csv_path,
            usecols=[
                "Title",
                "studio_name",
                "genre",
                "rating",
                "release_date",
                "Running Date",
                "DBR",
                "Sales Estimate",
                "cumulative_revenue",
            ],
            low_memory=False,
        )

        # Basic cleaning / type coercion so groupby aggregations don't fail
        df["Title"] = df["Title"].astype(str).str.strip()
        df = df[df["Title"].notna() & (df["Title"] != "")]

        # Dates: coerce invalid values to NaT so min/max work correctly
        df["Running Date"] = pd.to_datetime(df["Running Date"], errors="coerce")

        # DBR: ensure numeric so min/max don't operate on object dtype
        df["DBR"] = pd.to_numeric(df["DBR"], errors="coerce")

        csv_titles = set(df["Title"].unique())
        self.stdout.write(f"   Found {len(csv_titles):,} unique titles in CSV")

        # 2) Fetch titles already represented in Movie table (these are already embedded)
        existing_titles = set(
            Movie.objects.values_list("title", flat=True).distinct()
        )
        self.stdout.write(f"   Titles already present in Movie table (and thus embedded): {sorted(existing_titles)}")

        # 3) Determine titles that need embeddings
        new_titles = sorted(csv_titles - existing_titles)
        if limit is not None:
            new_titles = new_titles[:limit]

        if not new_titles:
            self.stdout.write(self.style.WARNING("⚠️  No new titles to embed – all CSV titles already in Movie table"))
            return

        self.stdout.write(self.style.SUCCESS(f"   ➕ New titles to embed: {len(new_titles):,}"))

        # 4) Initialize Pinecone and embedding model (same config as main RAG system)
        index_name = "customer-database-vectors"
        embedding_model_name = "BAAI/bge-base-en-v1.5"

        self.stdout.write("🔌 Connecting to Pinecone and loading embedding model...")
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        index = pc.Index(index_name)
        model = SentenceTransformer(embedding_model_name)

        stats = index.describe_index_stats()
        existing_vector_count = stats.get("total_vector_count", 0)
        self.stdout.write(f"   Current Pinecone vector count: {existing_vector_count:,}")

        # 5) Build one representative row per title for summarization
        #    We'll aggregate by title and release_date, and take simple stats.
        self.stdout.write("📊 Aggregating daily performance per title...")

        # Convert numeric columns
        def to_float(series):
            return pd.to_numeric(series, errors="coerce").fillna(0.0)

        df["Sales Estimate"] = to_float(df["Sales Estimate"])
        df["cumulative_revenue"] = to_float(df.get("cumulative_revenue", 0.0))

        # Aggregate per title
        group_cols = ["Title", "studio_name", "genre", "rating", "release_date"]
        agg_df = (
            df.groupby(group_cols)
            .agg(
                first_running_date=("Running Date", "min"),
                last_running_date=("Running Date", "max"),
                min_dbr=("DBR", "min"),
                max_dbr=("DBR", "max"),
                total_revenue=("Sales Estimate", "sum"),
                final_cumulative=("cumulative_revenue", "max"),
            )
            .reset_index()
        )

        agg_df = agg_df[agg_df["Title"].isin(new_titles)]
        self.stdout.write(f"   Aggregated daily metrics for {len(agg_df):,} titles")

        # 6) Build embedding texts and metadata
        records = []
        for _, row in agg_df.iterrows():
            title = str(row["Title"])
            studio = str(row.get("studio_name") or "Unknown Studio")
            genre = str(row.get("genre") or "Unknown Genre")
            rating = str(row.get("rating") or "NR")
            release_date = str(row.get("release_date") or "Unknown Release Date")
            first_running = str(row.get("first_running_date") or "")
            last_running = str(row.get("last_running_date") or "")
            min_dbr = row.get("min_dbr")
            max_dbr = row.get("max_dbr")
            total_rev = float(row.get("total_revenue") or 0.0)
            final_cum = float(row.get("final_cumulative") or 0.0)

            dbr_window = ""
            if pd.notna(min_dbr) and pd.notna(max_dbr):
                dbr_window = f"Presales DBR window from {int(min_dbr)} to {int(max_dbr)}."

            text_parts = [
                f"Movie: {title}",
                f"Studio: {studio}",
                f"Genre: {genre}",
                f"Rating: {rating}",
                f"Release Date: {release_date}",
            ]
            if first_running and last_running:
                text_parts.append(
                    f"Daily performance available from {first_running} to {last_running}."
                )
            if dbr_window:
                text_parts.append(dbr_window)
            text_parts.append(
                f"Total sales estimate across all days: ${total_rev:,.2f}."
            )
            text_parts.append(
                f"Final cumulative presales / revenue before release: ${final_cum:,.2f}."
            )
            text_parts.append(
                "This record summarizes daily box office performance used for comparative analytics and comp-title selection."
            )

            full_text = "\n".join(text_parts)

            metadata = {
                "chunk_type": "ai_daily_performance",
                "title": title,
                "studio_name": studio,
                "genre": genre,
                "rating": rating,
                "release_date": release_date,
                "first_running_date": first_running,
                "last_running_date": last_running,
                "min_dbr": int(min_dbr) if pd.notna(min_dbr) else None,
                "max_dbr": int(max_dbr) if pd.notna(max_dbr) else None,
                "total_revenue": round(total_rev, 2),
                "final_cumulative_revenue": round(final_cum, 2),
                "data_source": "AI_Data_Dump_All_Titles",
            }

            records.append((title, full_text, metadata))

        if not records:
            self.stdout.write(self.style.WARNING("⚠️  No records built for new titles; nothing to embed"))
            return

        self.stdout.write(f"   Built summary texts for {len(records):,} titles")

        # 7) Embed and upsert in batches
        total_vectors = 0
        start_time = time.time()

        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]
            titles_batch, texts_batch, metadata_batch = zip(*batch)

            embeddings = model.encode(
                list(texts_batch),
                batch_size=batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )

            vectors = []
            for i, (title, embedding, metadata) in enumerate(zip(titles_batch, embeddings, metadata_batch)):
                base_id = f"ai_daily_{title}"
                safe_base_id = _sanitize_vector_id(base_id)[:80]
                vector_id = f"{safe_base_id}_{start + i}"
                vectors.append(
                    {
                        "id": vector_id,
                        "values": embedding.tolist(),
                        "metadata": metadata,
                    }
                )

            index.upsert(vectors=vectors, timeout=60)
            total_vectors += len(vectors)

            self.stdout.write(
                f"   ✅ Upserted batch {start // batch_size + 1} "
                f"({len(vectors)} vectors, total {total_vectors:,})"
            )
            time.sleep(0.2)  # gentle rate limiting

        elapsed = time.time() - start_time
        stats = index.describe_index_stats()
        final_count = stats.get("total_vector_count", 0)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("✅ AI daily-performance embedding pipeline complete"))
        self.stdout.write(f"   New vectors created: {total_vectors:,}")
        self.stdout.write(f"   Final Pinecone vector count: {final_count:,}")
        self.stdout.write(f"   Elapsed time: {elapsed:.1f}s")


def _sanitize_vector_id(raw_id: str) -> str:
    """
    Make sure vector IDs are ASCII-only and safe for Pinecone.
    
    Steps:
    - Normalize unicode and strip accents
    - Remove characters outside [A-Za-z0-9_-]
    - Collapse multiple separators
    - Fallback to a simple default if everything is stripped
    """
    if not isinstance(raw_id, str):
        raw_id = str(raw_id or "")
    
    # Normalize and strip accents
    normalized = unicodedata.normalize("NFKD", raw_id)
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii")
    
    # Replace whitespace with underscore
    ascii_str = re.sub(r"\s+", "_", ascii_str)
    
    # Keep only allowed characters
    ascii_str = re.sub(r"[^A-Za-z0-9_-]", "", ascii_str)
    
    # Collapse multiple underscores
    ascii_str = re.sub(r"_+", "_", ascii_str).strip("_")
    
    if not ascii_str:
        ascii_str = "vector"
    
    return ascii_str


