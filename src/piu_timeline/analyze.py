"""Analyze video into evidence-backed structured data without rendering a timeline."""
from .auto_timeline import main


if __name__ == "__main__":
    main(analysis_only=True)
