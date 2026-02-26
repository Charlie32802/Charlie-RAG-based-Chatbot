#!/usr/bin/env python3
"""
Clean File Structure Viewer
Shows only your project files, excluding venv and package directories
"""

import os
import sys

def print_tree(start_path, prefix="", max_depth=3, exclude_patterns=None):
    """Print directory tree structure with depth limit and exclusions"""
    if exclude_patterns is None:
        exclude_patterns = [
            'venv', '.venv', 'env', '.env',
            '__pycache__', '.pytest_cache',
            '.git', '.idea', '.vscode',
            'node_modules',
            '.DS_Store', '.env.local',
            '*.pyc', '*.pyo', '*.pyd',
            '.coverage', '.tox',
            'dist', 'build', '*.egg-info'
        ]
    
    try:
        items = os.listdir(start_path)
    except PermissionError:
        print(f"{prefix}└── [Permission Denied]")
        return
    
    # Filter out excluded items
    filtered_items = []
    for item in items:
        skip = False
        for pattern in exclude_patterns:
            if pattern.startswith('*'):
                if item.endswith(pattern[1:]):
                    skip = True
                    break
            elif item == pattern:
                skip = True
                break
        if not skip:
            filtered_items.append(item)
    
    # Sort items
    filtered_items.sort(key=lambda x: (not os.path.isdir(os.path.join(start_path, x)), x.lower()))
    
    for index, item in enumerate(filtered_items):
        is_last = index == len(filtered_items) - 1
        item_path = os.path.join(start_path, item)
        
        # Print current item
        connector = "└── " if is_last else "├── "
        
        # Add marker for directories
        if os.path.isdir(item_path):
            item_display = f"{item}/"
        else:
            item_display = item
        
        print(f"{prefix}{connector}{item_display}")
        
        # Recursively print subdirectories if not too deep
        if os.path.isdir(item_path):
            current_depth = prefix.count("│   ") + prefix.count("    ")
            if current_depth < max_depth:
                extension = "    " if is_last else "│   "
                print_tree(item_path, prefix + extension, max_depth, exclude_patterns)

def count_files_and_dirs(path, exclude_patterns):
    """Count files and directories"""
    file_count = 0
    dir_count = 0
    
    for root, dirs, files in os.walk(path):
        # Filter out excluded directories
        dirs[:] = [d for d in dirs if not any(
            pattern == d or (pattern.startswith('*') and d.endswith(pattern[1:]))
            for pattern in exclude_patterns
        )]
        
        # Filter out excluded files
        files = [f for f in files if not any(
            pattern == f or (pattern.startswith('*') and f.endswith(pattern[1:]))
            for pattern in exclude_patterns
        )]
        
        dir_count += len(dirs)
        file_count += len(files)
    
    return file_count, dir_count

def main():
    """Main function"""
    print("\n" + "="*60)
    print("CLEAN FILE STRUCTURE VIEWER")
    print("="*60)
    
    # Get current directory
    current_dir = os.getcwd()
    dir_name = os.path.basename(current_dir)
    
    exclude_patterns = [
        'venv', '.venv', 'env',
        '__pycache__', '.pytest_cache',
        '.git', '.idea', '.vscode',
        'node_modules',
        '*.pyc', '*.pyo'
    ]
    
    print(f"\nDirectory: {current_dir}")
    
    # Count files
    file_count, dir_count = count_files_and_dirs(current_dir, exclude_patterns)
    print(f"Items: {file_count} files, {dir_count} directories (excluding packages)")
    
    print("\nStructure (max depth: 3):")
    print(f"{dir_name}/")
    
    # Print the tree
    print_tree(current_dir, max_depth=3, exclude_patterns=exclude_patterns)
    
    # Show your actual Django project files
    print("\n" + "="*60)
    print("YOUR DJANGO PROJECT FILES:")
    print("="*60)
    
    # Look for Django-specific files
    django_files = []
    for item in os.listdir(current_dir):
        if item in ['manage.py', 'requirements.txt', 'db.sqlite3', 'pyproject.toml', 'setup.py']:
            django_files.append(item)
        elif os.path.isdir(item) and item not in ['venv', '.venv', '__pycache__']:
            # Check if it might be a Django app
            if os.path.exists(os.path.join(item, 'models.py')) or os.path.exists(os.path.join(item, 'views.py')):
                django_files.append(f"{item}/ (Django app)")
            else:
                django_files.append(f"{item}/")
    
    if django_files:
        for item in sorted(django_files):
            print(f"• {item}")
    else:
        print("No Django project files found in root directory.")
    
    print("\n" + "="*60)
    print("Note: Virtual environment and package files are excluded")
    print("To see everything, remove the venv/ directory from exclusions")
    print("="*60)

if __name__ == "__main__":
    main()