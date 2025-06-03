"""Utilities for CSV file processing."""

import csv
from pathlib import Path
from typing import Optional


def find_most_recent_csv(directory: str) -> Optional[Path]:
    """Find the most recently modified CSV file in a directory.
    
    Args:
        directory: Path to the directory to search
        
    Returns:
        Path to the most recent CSV file, or None if no CSV files found
    """
    dir_path = Path(directory)
    
    if not dir_path.exists():
        raise FileNotFoundError(f"Directory does not exist: {directory}")
    
    if not dir_path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {directory}")
    
    csv_files = list(dir_path.glob("*.csv"))
    
    if not csv_files:
        return None
    
    # Find the most recently modified CSV file
    most_recent = max(csv_files, key=lambda f: f.stat().st_mtime)
    return most_recent


def extract_upcs_from_csv(csv_path: Path) -> list[str]:
    """Extract UPCs from the first column of a CSV file.
    
    Args:
        csv_path: Path to the CSV file
        
    Returns:
        List of UPCs (as strings) from the first column
    """
    upcs = []
    
    try:
        with open(csv_path, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            
            for row in reader:
                if row and row[0].strip():  # Check if row exists and first cell is not empty
                    upcs.append(row[0].strip())
                    
    except FileNotFoundError:
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    except Exception as e:
        raise RuntimeError(f"Error reading CSV file {csv_path}: {e}") from e
    
    return upcs