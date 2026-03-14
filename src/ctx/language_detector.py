from pathlib import Path
from typing import Optional

# Mapping of file extensions to languages
EXTENSION_MAP = {
    ".py": "Python",
    ".rs": "Rust",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JavaScript (React)",
    ".tsx": "TypeScript (React)",
    ".go": "Go",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
    ".java": "Java",
    ".cs": "C#",
    ".rb": "Ruby",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
}

# Mapping of project configuration files to languages
CONFIG_FILE_MAP = {
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "Cargo.toml": "Rust",
    "package.json": "JavaScript/TypeScript",
    "go.mod": "Go",
    "pom.xml": "Java",
    "build.gradle": "Java/Kotlin",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
}

def detect_language(path: Path) -> Optional[str]:
    """
    Detects the primary programming language of a file or directory.

    Args:
        path: Path to the file or directory.

    Returns:
        The name of the detected language, or None if unknown.
    """
    if path.is_file():
        return EXTENSION_MAP.get(path.suffix.lower())
    
    if path.is_dir():
        # Check for common project configuration files
        for config_file, language in CONFIG_FILE_MAP.items():
            if (path / config_file).exists():
                return language
        
        # If no config file found, check extensions of files in the directory
        # (This is a bit more expensive, so we only do it if necessary)
        try:
            extensions = [f.suffix.lower() for f in path.iterdir() if f.is_file()]
            if extensions:
                from collections import Counter
                most_common_ext, _ = Counter(extensions).most_common(1)[0]
                return EXTENSION_MAP.get(most_common_ext)
        except (OSError, IndexError):
            pass

    return None
