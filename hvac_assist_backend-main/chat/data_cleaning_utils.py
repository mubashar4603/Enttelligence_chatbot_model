#!/usr/bin/env python3
"""
🧹 DATA CLEANING UTILITY FOR ENTELIGENCE PIPELINE
Handles dollar signs, commas, and other data quality issues
"""

import pandas as pd
import numpy as np
import re
from typing import Union, Any

def clean_price(price_value: Any) -> float:
    """
    Clean price data by removing dollar signs, commas, and converting to float
    
    Args:
        price_value: Raw price value (string, float, or other)
        
    Returns:
        float: Cleaned price value
    """
    if pd.isna(price_value) or price_value is None:
        return 0.0
    
    try:
        # Convert to string and clean
        price_str = str(price_value).strip()
        
        # Remove dollar signs, commas, and other currency symbols
        price_str = re.sub(r'[$,\s]', '', price_str)
        
        # Handle empty strings
        if not price_str:
            return 0.0
        
        # Convert to float
        price_float = float(price_str)
        
        # Validate reasonable range
        if price_float < 0 or price_float > 1000:
            return 0.0
            
        return price_float
        
    except (ValueError, TypeError, AttributeError):
        return 0.0

def clean_numeric(value: Any, default: Union[int, float] = 0) -> Union[int, float]:
    """
    Clean numeric data by converting to appropriate type
    
    Args:
        value: Raw numeric value
        default: Default value if conversion fails
        
    Returns:
        Cleaned numeric value
    """
    if pd.isna(value) or value is None:
        return default
    
    try:
        if isinstance(default, int):
            return int(float(str(value)))
        else:
            return float(str(value))
    except (ValueError, TypeError):
        return default

def clean_text(value: Any) -> str:
    """
    Clean text data by handling nulls and converting to string
    
    Args:
        value: Raw text value
        
    Returns:
        Cleaned string value
    """
    if pd.isna(value) or value is None:
        return "Unknown"
    
    return str(value).strip()

def calculate_derived_metrics(row: pd.Series) -> dict:
    """
    Calculate derived metrics for better RAG performance
    
    Args:
        row: Pandas Series containing row data
        
    Returns:
        dict: Calculated metrics
    """
    # Clean the data
    price = clean_price(row.get('price', 0))
    reserved = clean_numeric(row.get('reserved', 0), 0)
    total_seats = clean_numeric(row.get('total_seats', 0), 0)
    
    # Calculate metrics
    occupancy_rate = (reserved / total_seats * 100) if total_seats > 0 else 0.0
    sales_estimate = price * reserved
    available_seats = total_seats - reserved
    
    return {
        'price_clean': price,
        'reserved_clean': reserved,
        'total_seats_clean': total_seats,
        'available_seats': available_seats,
        'occupancy_rate': round(occupancy_rate, 2),
        'sales_estimate': round(sales_estimate, 2),
        'price_display': f"${price:.2f}" if price > 0 else "Free"
    }

def create_rag_friendly_text(row: pd.Series, metrics: dict) -> str:
    """
    Create RAG-friendly text with clean numerical data
    
    Args:
        row: Pandas Series containing row data
        metrics: Calculated metrics from calculate_derived_metrics
        
    Returns:
        str: Clean, structured text for RAG
    """
    # Clean text fields
    title = clean_text(row.get('title', ''))
    genre = clean_text(row.get('genre', ''))
    rating = clean_text(row.get('rating', ''))
    theater_name = clean_text(row.get('theater_name', ''))
    theater_city = clean_text(row.get('theater_city', ''))
    theater_state = clean_text(row.get('theater_state', ''))
    studio_name = clean_text(row.get('studio_name', ''))
    circuit_name = clean_text(row.get('circuit_name', ''))
    screen_format = clean_text(row.get('screen_format', ''))
    language_format = clean_text(row.get('language_format', ''))
    amenities = clean_text(row.get('amenities', ''))
    dma = clean_text(row.get('dma', ''))
    
    # Create structured text
    text_parts = [
        f"Film: {title} | {genre} | {rating}",
        f"Theater: {theater_name} | {theater_city}, {theater_state}",
        f"Date: {row.get('date_sh', '')} | Time: {row.get('time_sh', '')}",
        f"Format: {screen_format} | Language: {language_format}",
        f"Price: {metrics['price_display']} | Reserved: {metrics['reserved_clean']:,} | Total: {metrics['total_seats_clean']:,}",
        f"Occupancy: {metrics['occupancy_rate']:.1f}% | Sales: ${metrics['sales_estimate']:.2f}",
        f"Studio: {studio_name} | Circuit: {circuit_name}",
        f"Amenities: {amenities} | DMA: {dma}"
    ]
    
    return "\n".join(text_parts)

def create_rag_metadata(row: pd.Series, metrics: dict) -> dict:
    """
    Create RAG-friendly metadata with clean numerical data
    
    Args:
        row: Pandas Series containing row data
        metrics: Calculated metrics from calculate_derived_metrics
        
    Returns:
        dict: Clean metadata for RAG
    """
    return {
        'chunk_type': 'film_performance',
        'title': clean_text(row.get('title', '')),
        'genre': clean_text(row.get('genre', '')),
        'rating': clean_text(row.get('rating', '')),
        'theater_name': clean_text(row.get('theater_name', '')),
        'theater_city': clean_text(row.get('theater_city', '')),
        'theater_state': clean_text(row.get('theater_state', '')),
        'date_sh': clean_text(row.get('date_sh', '')),
        'time_sh': clean_text(row.get('time_sh', '')),
        'screen_format': clean_text(row.get('screen_format', '')),
        'language_format': clean_text(row.get('language_format', '')),
        'studio_name': clean_text(row.get('studio_name', '')),
        'circuit_name': clean_text(row.get('circuit_name', '')),
        'amenities': clean_text(row.get('amenities', '')),
        'dma': clean_text(row.get('dma', '')),
        
        # Clean numerical values
        'price': metrics['price_clean'],
        'reserved': metrics['reserved_clean'],
        'total_seats': metrics['total_seats_clean'],
        'available_seats': metrics['available_seats'],
        'occupancy_rate': metrics['occupancy_rate'],
        'sales_estimate': metrics['sales_estimate'],
        
        # Additional metadata
        'row_index': int(row.name) if row.name is not None else 0
    }

def process_row_for_rag(row: pd.Series) -> tuple:
    """
    Process a single row for RAG with clean data
    
    Args:
        row: Pandas Series containing row data
        
    Returns:
        tuple: (text, metadata) for RAG
    """
    # Calculate derived metrics
    metrics = calculate_derived_metrics(row)
    
    # Create RAG-friendly text and metadata
    text = create_rag_friendly_text(row, metrics)
    metadata = create_rag_metadata(row, metrics)
    
    return text, metadata

# Example usage
if __name__ == "__main__":
    # Test the cleaning functions
    test_data = {
        'title': 'Avatar 2',
        'genre': 'Action',
        'rating': 'PG-13',
        'price': '$14.25',
        'reserved': 150,
        'total_seats': 200,
        'theater_name': 'AMC Empire 25',
        'theater_city': 'New York',
        'theater_state': 'NY'
    }
    
    test_row = pd.Series(test_data)
    text, metadata = process_row_for_rag(test_row)
    
    print("🧹 CLEANED TEXT:")
    print(text)
    print("\n📊 CLEANED METADATA:")
    print(metadata)
